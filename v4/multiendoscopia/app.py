""" app-endoscopia-v1
Interface Streamlit para Sistema de Controle de Procedimentos de Endoscopia

Instalar:
    pip install streamlit crewai python-dotenv pypdf openpyxl

Executar:
    streamlit run app_endoscopia.py
"""

import os
import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import io
import re

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from docx import Document
from pypdf import PdfReader

# CrewAI
from crewai import Agent, Task, Crew, Process, LLM

# =============================================================================
# CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE E LOG
# =============================================================================

load_dotenv()

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "crew_logs.log"),
        logging.StreamHandler(),
    ],
    force=True,
)
logger = logging.getLogger(__name__)


# =============================================================================
# HANDLER DE LOG EM TEMPO REAL PARA O STREAMLIT
# =============================================================================

class StreamlitLogHandler(logging.Handler):
    """
    Handler de logging que empurra cada registro para uma fila thread-safe.
    A thread principal do Streamlit consome essa fila e renderiza os logs
    na interface em tempo real enquanto o CrewAI processa em background.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


def render_log_line(line: str, container) -> None:
    """Renderiza uma linha de log com ícone e cor de acordo com o conteúdo."""
    line_lower = line.lower()

    if any(k in line_lower for k in ("error", "erro", "exception", "traceback")):
        container.error(f"🔴 {line}")
    elif any(k in line_lower for k in ("warning", "warn", "aviso")):
        container.warning(f"🟡 {line}")
    elif any(k in line_lower for k in ("task", "tarefa", "iniciando", "starting")):
        container.info(f"📋 {line}")
    elif any(k in line_lower for k in ("agent", "agente", "thinking", "pensando")):
        container.info(f"🤖 {line}")
    elif any(k in line_lower for k in ("action", "ação", "tool", "ferramenta")):
        container.info(f"⚙️ {line}")
    elif any(k in line_lower for k in ("final answer", "resposta final", "finished", "concluído", "complete")):
        container.success(f"✅ {line}")
    else:
        container.text(f"   {line}")


# =============================================================================
# FUNÇÕES DE LEITURA DE ARQUIVOS
# =============================================================================

def read_word_file(file) -> str:
    """Lê arquivo Word (.docx)."""
    try:
        doc = Document(file)
        text = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(text)
    except Exception as e:
        st.error(f"Erro ao ler arquivo Word: {e}")
        return None


def read_pdf_file(file) -> str:
    """Lê arquivo PDF."""
    try:
        pdf_reader = PdfReader(file)
        text = [
            page.extract_text()
            for page in pdf_reader.pages
            if page.extract_text() and page.extract_text().strip()
        ]
        return "\n\n".join(text)
    except Exception as e:
        st.error(f"Erro ao ler arquivo PDF: {e}")
        return None


def read_text_file(file) -> str:
    """Lê arquivo de texto (.txt e .csv)."""
    try:
        file.seek(0)
        raw = file.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="ignore")
        return str(raw)
    except Exception as e:
        st.error(f"Erro ao ler arquivo de texto: {e}")
        return None


def read_excel_file(file) -> str:
    """
    Lê arquivo Excel (.xlsx ou .xls) e converte para texto CSV.
    Cada aba do workbook é convertida em um bloco separado.
    Retorna o conteúdo como string CSV multi-aba.
    """
    try:
        file.seek(0)
        xls = pd.ExcelFile(file, engine="openpyxl")
        blocos = []
        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name, dtype=str)
            df.fillna("", inplace=True)
            # Remove colunas e linhas totalmente vazias
            df.dropna(axis=1, how="all", inplace=True)
            df.dropna(axis=0, how="all", inplace=True)
            if df.empty:
                continue
            csv_str = df.to_csv(index=False, sep=",", encoding="utf-8")
            blocos.append(f"=== ABA: {sheet_name} ===\n{csv_str}")
        if not blocos:
            st.warning("O arquivo Excel não contém dados nas abas.")
            return None
        return "\n\n".join(blocos)
    except Exception as e:
        st.error(f"Erro ao ler arquivo Excel: {e}")
        return None


def extract_text_from_file(uploaded_file) -> str:
    """Extrai texto de diferentes tipos de arquivo, incluindo Excel."""
    if uploaded_file is None:
        return None

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    uploaded_file.seek(0)

    readers = {
        "docx": read_word_file,
        "pdf": read_pdf_file,
        "txt": read_text_file,
        "csv": read_text_file,
        "xlsx": read_excel_file,
        "xls": read_excel_file,
    }

    reader = readers.get(extension)
    if reader:
        return reader(uploaded_file)

    st.error(f"Formato de arquivo não suportado: .{extension}")
    return None


# =============================================================================
# CONFIGURAÇÃO DO LLM (compatível CrewAI / LiteLLM)
# =============================================================================

@st.cache_resource
def get_llm(model_choice: str, custom_model: str, temperature: float, api_key: str) -> LLM:
    """Cria instância do LLM nativo do CrewAI."""
    if not api_key:
        st.error("⚠️ API Key não configurada!")
        st.stop()

    model_name = custom_model.strip() if custom_model and custom_model.strip() else model_choice

    if "gemini" in model_name.lower() and not model_name.startswith("gemini/"):
        model_name = f"gemini/{model_name}"

    try:
        return LLM(model=model_name, api_key=api_key, temperature=temperature)
    except Exception as e:
        st.error(f"Erro ao inicializar o modelo '{model_name}': {e}")
        st.info("Confira se o nome do modelo está correto para sua conta Google Vertex/GenAI.")
        st.stop()


# =============================================================================
# CRIAÇÃO DOS AGENTES
# =============================================================================

def create_agents(llm) -> list:
    """Cria o agente analista de endoscopia."""
    multiendoscopia_analista = Agent(
        role="Analista de Controle dos procedimentos de Endoscopia",
        goal="""Identificar o tipo do arquivo recebido (PRODUCAO ou REPASSE) e extrair
TODAS as linhas de dados, estruturando-as em CSV padronizado para confronto posterior.

== ARQUIVO PRODUCAO (planilha da equipe de enfermagem) ==
Colunas originais esperadas:
  DATA, NOME DO PACIENTE, Nº ATENDIMENTO, CONVÊNIO, ORIGEM,
  EXAME REALIZADO, PROCEDIMENTOS ADICIONAIS, MÉDICO EXECUTOR,
  LOCAL / SETOR, SALA, CARATER, OBSERVAÇÃO + PROCEDIMENTOS ADICIONAIS

Regras de extração:
- Cada exame realizado gera UMA linha no CSV de saída.
- Se houver PROCEDIMENTOS ADICIONAIS preenchidos, gerar uma linha EXTRA para cada
  procedimento adicional listado (ex: "TESTE DE UREASE" vira linha separada).
- A coluna CONVÊNIO pode conter abreviações (ex: "PROMOVE") — manter como está.
- Não há código TUSS nem valor neste arquivo; deixar CodigoTUSS e ValorLiberado vazios.
- Coluna TipoArquivo = "PRODUCAO".

Colunas de saída para PRODUCAO:
  Data, NrAtendimento, Paciente, Convenio, Procedimento, CodigoTUSS,
  MedicoExecutor, ValorLiberado, QtProcedimento, TipoArquivo, Observacao

== ARQUIVO REPASSE (planilha emitida pelo hospital) ==
Colunas originais esperadas:
  Ds estabelecimento, Ds terceiro, Nr repasse terceiro, Nr atendimento,
  Paciente, Convenio, Ds categoria, Cód Item TUSS, Ds procedimento,
  Nm medico executor, Porcentagem, Ds funcao, Ds especialidade,
  Qt procedimento, Dt procedimento, Vl liberado

Regras de extração:
- Cada linha do arquivo = uma linha no CSV de saída.
- Manter o código TUSS original (campo "Cód Item TUSS").
- Manter o valor liberado (campo "Vl liberado") como ValorLiberado.
- Coluna TipoArquivo = "REPASSE".

Colunas de saída para REPASSE:
  Data, NrAtendimento, Paciente, Convenio, Procedimento, CodigoTUSS,
  MedicoExecutor, ValorLiberado, QtProcedimento, TipoArquivo, Observacao

== REGRAS GERAIS ==
- Padronizar Data para DD/MM/AAAA.
- Padronizar nomes de paciente em MAIÚSCULAS sem espaços extras.
- Retornar APENAS o CSV puro, sem markdown, sem explicações.
- Primeira linha obrigatoriamente o cabeçalho:
  Data,NrAtendimento,Paciente,Convenio,Procedimento,CodigoTUSS,MedicoExecutor,ValorLiberado,QtProcedimento,TipoArquivo,Observacao""",
        backstory="""Expert em análise de faturamento hospitalar e auditoria de convênios médicos.
Especializado na Terminologia Unificada da Saúde Suplementar (TUSS) e nas regras de
faturamento dos principais convênios do Brasil.
Conhece em profundidade os campos das planilhas de produtividade de equipes de enfermagem
e os arquivos de repasse hospitalares (formato Hospital São Camilo e similares).
Sabe que o número de atendimento pode divergir entre os dois arquivos para o mesmo
paciente/procedimento, portanto não usa esse campo como chave única.
Seu principal objetivo é estruturar os dados com máxima fidelidade para que o agente
correlacionador consiga fazer o batimento correto.""",
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )
    return [multiendoscopia_analista]


def create_correlator_agent(llm) -> Agent:
    """Cria o agente correlacionador dos registros de endoscopia."""
    return Agent(
        role="Correlacionador dos registros de endoscopia",
        goal="""Receber os CSVs padronizados gerados pelo Analista — um do tipo PRODUCAO
e outro do tipo REPASSE — e realizar o Batimento Automático linha a linha.

== CHAVE DE CORRELAÇÃO ==
ATENÇÃO: o número de atendimento (NrAtendimento) pode ser DIFERENTE entre os dois
arquivos para o mesmo episódio. Portanto, a chave de correlação deve ser COMPOSTA por:
  1. Data (DD/MM/AAAA) — tolerância de ± 1 dia para o mesmo episódio
  2. Paciente (nome normalizado em maiúsculas)
  3. Procedimento (correspondência semântica: "COLONOSCOPIA" bate com
     "Colonoscopia (Inclui A Retossigmoidoscopia)", "TESTE DE UREASE" bate com
     "Pesquisa de H. pylori - Teste da Urease", etc.)

NÃO usar médico executor como chave, pois o nome pode ser abreviado na PRODUCAO
(ex: "DRA. PAULA") e completo no REPASSE ("CHARLIANA UCHOA CRISTOVAO").

== FLUXO DE BATIMENTO ==
1. Para cada linha da PRODUCAO, tentar encontrar correspondência no REPASSE
   usando a chave composta acima.
2. Se encontrar correspondência:
   a. Se ValorLiberado coincidir (ou REPASSE não tiver valor): StatusCorrelacao = "CORRELACIONADO"
   b. Se ValorLiberado for menor no REPASSE: StatusCorrelacao = "CORRELACIONADO_COM_DIVERGENCIA_VALOR"
   c. Se ValorLiberado = 0 no REPASSE: StatusCorrelacao = "CORRELACIONADO_COM_GLOSA_TOTAL"
   d. Se ValorLiberado > 0 mas menor que esperado: StatusCorrelacao = "CORRELACIONADO_COM_GLOSA_PARCIAL"
3. Se NÃO encontrar correspondência no REPASSE: StatusCorrelacao = "NAO_FATURADO_NO_REPASSE"
4. Para linhas do REPASSE sem correspondência na PRODUCAO: StatusCorrelacao = "REPASSE_NAO_IDENTIFICADO_NA_PRODUCAO"

== COLUNAS DO CSV DE SAÍDA ==
Data, NrAtendProducao, NrAtendRepasse, Paciente, Convenio, Procedimento, CodigoTUSS,
MedicoExecutor, QtProcedimento, ValorLiberado, StatusCorrelacao, Observacao

== REGRAS OBRIGATÓRIAS ==
1. NÃO remover nenhuma linha da PRODUCAO.
2. Padronizar Data para DD/MM/AAAA.
3. Padronizar ValorLiberado: ponto decimal, sem símbolo de moeda.
4. Ordenar por Data crescente.
5. Ao final, adicionar seção separada por linha em branco:
   # RESUMO_DIVERGENCIAS_POR_CONVENIO
   com colunas: Convenio, TotalProcedimentos, Correlacionados, Divergencias,
   GlosasTotal, GlosasParcial, NaoFaturados, NaoIdentificados, ValorTotalLiberado""",
        backstory="""Especialista em auditoria de faturamento médico, ETL e reconciliação de dados hospitalares.
Domina as particularidades dos arquivos de repasse do Hospital São Camilo e similares.
Sabe que divergências de nomenclatura entre planilhas internas e sistemas hospitalares são
comuns e usa correspondência semântica para não perder correlações válidas.
Nunca inventa procedimentos — apenas padroniza, correlaciona e sinaliza divergências.
Seu trabalho alimenta diretamente a cobrança estruturada junto ao hospital e convênios.""",
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


def create_correlation_task(correlator_agent: Agent, csvs_por_arquivo: dict) -> Task:
    """Cria a task de correlação recebendo o dicionário {filename: csv_bruto}."""
    blocos = "\n\n".join(
        f"=== ARQUIVO: {fname} ===\n{csv_text}"
        for fname, csv_text in csvs_por_arquivo.items()
    )
    return Task(
        description=f"""Você recebeu os seguintes blocos CSV padronizados pelo Analista de Endoscopia,
identificados como PRODUCAO e REPASSE. Execute o batimento automático conforme as regras
do seu objetivo (goal), usando chave composta de Data + Paciente + Procedimento.

{blocos}

IMPORTANTE:
- Retorne APENAS o CSV correlacionado (mais a seção de resumo ao final).
- Não inclua explicações, markdown, nem blocos de código — apenas o conteúdo puro do CSV.
- A primeira linha deve ser obrigatoriamente o cabeçalho:
  Data,NrAtendProducao,NrAtendRepasse,Paciente,Convenio,Procedimento,CodigoTUSS,MedicoExecutor,QtProcedimento,ValorLiberado,StatusCorrelacao,Observacao""",
        expected_output=(
            "CSV puro com cabeçalho "
            "'Data,NrAtendProducao,NrAtendRepasse,Paciente,Convenio,Procedimento,CodigoTUSS,"
            "MedicoExecutor,QtProcedimento,ValorLiberado,StatusCorrelacao,Observacao', "
            "seguido de todas as linhas ordenadas por Data, "
            "e ao final a seção '# RESUMO_DIVERGENCIAS_POR_CONVENIO' com colunas: "
            "Convenio, TotalProcedimentos, Correlacionados, Divergencias, GlosasTotal, "
            "GlosasParcial, NaoFaturados, NaoIdentificados, ValorTotalLiberado."
        ),
        agent=correlator_agent,
    )


# =============================================================================
# UTILITÁRIOS DE CSV
# =============================================================================

COLUNAS_ESPERADAS = [
    "Data", "NrAtendProducao", "NrAtendRepasse", "Paciente", "Convenio",
    "Procedimento", "CodigoTUSS", "MedicoExecutor",
    "QtProcedimento", "ValorLiberado", "StatusCorrelacao", "Observacao",
]


def extrair_csv_do_texto(texto: str) -> str:
    """
    Extrai o bloco CSV de dentro de uma resposta que pode conter texto livre,
    blocos markdown ou conteúdo puro.
    """
    match = re.search(r"```(?:csv)?\s*\n(.*?)```", texto, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    linhas_csv = [
        linha for linha in texto.splitlines()
        if linha.count(",") >= 4 or linha.startswith("Data,")
    ]
    return "\n".join(linhas_csv).strip()


def separar_resumo_do_csv(texto_csv: str) -> tuple[str, str]:
    """Separa o bloco de dados do bloco de resumo."""
    marcador = "# RESUMO_DIVERGENCIAS_POR_CONVENIO"
    if marcador in texto_csv:
        partes = texto_csv.split(marcador, 1)
        return partes[0].strip(), partes[1].strip()
    return texto_csv.strip(), ""


def texto_para_dataframe(csv_texto: str) -> pd.DataFrame | None:
    """Converte texto CSV em DataFrame pandas. Retorna None em caso de falha."""
    try:
        csv_limpo = extrair_csv_do_texto(csv_texto)
        csv_dados, _ = separar_resumo_do_csv(csv_limpo)
        df = pd.read_csv(io.StringIO(csv_dados), sep=",", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"Falha ao converter CSV para DataFrame: {e}")
        return None


# =============================================================================
# CRIAÇÃO DAS TASKS
# =============================================================================

def create_tasks(agents: list, conteudo_arquivo: str) -> list:
    """Cria as tasks encadeadas para análise de um arquivo de endoscopia."""
    task_analise = Task(
        description=f"""Analise o arquivo de endoscopia abaixo e identifique se é do tipo
PRODUCAO (planilha da equipe de enfermagem) ou REPASSE (emitido pelo hospital).

=== CONTEÚDO DO ARQUIVO ===
{conteudo_arquivo}

=== INSTRUÇÕES ESPECÍFICAS ===

Se for PRODUCAO, as colunas originais são:
  DATA | NOME DO PACIENTE | Nº ATENDIMENTO | CONVÊNIO | ORIGEM |
  EXAME REALIZADO | PROCEDIMENTOS ADICIONAIS | MÉDICO EXECUTOR |
  LOCAL / SETOR | SALA | CARATER | OBSERVAÇÃO + PROCEDIMENTOS ADICIONAIS

  - Gerar uma linha para cada EXAME REALIZADO.
  - Se PROCEDIMENTOS ADICIONAIS estiver preenchido, gerar uma linha ADICIONAL para
    cada procedimento listado (separados por vírgula ou quebra de linha).
  - Deixar CodigoTUSS e ValorLiberado vazios (não há na PRODUCAO).
  - TipoArquivo = "PRODUCAO"

Se for REPASSE, as colunas originais são:
  Ds estabelecimento | Ds terceiro | Nr repasse terceiro | Nr atendimento |
  Paciente | Convenio | Ds categoria | Cód Item TUSS | Ds procedimento |
  Nm medico executor | Porcentagem | Ds funcao | Ds especialidade |
  Qt procedimento | Dt procedimento | Vl liberado

  - Mapear: "Cód Item TUSS" → CodigoTUSS, "Vl liberado" → ValorLiberado,
    "Dt procedimento" → Data, "Nr atendimento" → NrAtendimento,
    "Nm medico executor" → MedicoExecutor, "Qt procedimento" → QtProcedimento.
  - TipoArquivo = "REPASSE"

=== SAÍDA OBRIGATÓRIA ===
Retorne APENAS o CSV puro, sem markdown, sem explicações.
Cabeçalho obrigatório na primeira linha:
Data,NrAtendimento,Paciente,Convenio,Procedimento,CodigoTUSS,MedicoExecutor,ValorLiberado,QtProcedimento,TipoArquivo,Observacao

Não omita nenhuma linha — cada procedimento registrado deve constar no CSV gerado.""",
        expected_output=(
            "CSV puro com cabeçalho "
            "'Data,NrAtendimento,Paciente,Convenio,Procedimento,CodigoTUSS,MedicoExecutor,"
            "ValorLiberado,QtProcedimento,TipoArquivo,Observacao', "
            "com todas as linhas do arquivo estruturadas e TipoArquivo preenchido."
        ),
        agent=agents[0],
    )
    return [task_analise]


# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

def main():
    st.set_page_config(
        page_title="Endoscopia | Controle de Procedimentos",
        page_icon="🔬",
        layout="wide",
    )

    st.markdown(
        '<h1 style="text-align: center;">🔬 Sistema de Controle de Procedimentos de Endoscopia</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align: center;">'
        'Confronto automático entre Produtividade da Equipe e Repasse do Hospital<br>'
        'Identificação de Glosas, Divergências de Valor e Procedimentos Não Faturados<br>'
        'Apoio à cobrança estruturada junto ao hospital e convênios médicos'
        '</p>',
        unsafe_allow_html=True,
    )

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.info("💡 Sistema exclusivo para controle de procedimentos endoscópicos e faturamento junto a convênios.")
        st.divider()
        st.header("⚙️ Configurações")

        env_api_key = os.getenv("GOOGLE_API_KEY", "")
        api_key = st.text_input(
            "🔑 Google API Key",
            value=env_api_key,
            type="password",
            help="Sua chave da API do Google Gemini",
        )

        if api_key:
            st.success("✅ API Key configurada")
        else:
            st.error("❌ API Key não encontrada")

        st.divider()

        custom_model = st.text_input(
            "Modelo custom (opcional)",
            value="gemini/gemini-2.5-flash",
            help="Exemplos: gemini/gemini-2.5-flash-lite ou gemini/gemini-2.5-pro",
        )
        temperature = st.slider(
            "🌡️ Temperatura",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.1,
            help="0 = determinístico | 1 = criativo",
        )

        st.divider()
        st.header("👥 Agentes Disponíveis")

        agents_info = [
            ("🔍", "Analista de Endoscopia", "Lê e estrutura os arquivos PRODUCAO e REPASSE"),
            ("🔀", "Correlacionador", "Confronta registros e identifica divergências"),
        ]
        for icon, name, desc in agents_info:
            st.markdown(f"{icon} **{name}**")
            st.caption(desc)

        st.divider()
        st.header("📌 Tipos de Arquivo")
        st.markdown("""
- **PRODUCAO**: planilha da equipe de enfermagem com os procedimentos realizados (código TUSS)
- **REPASSE**: planilha emitida pelo hospital com valores faturados e pagos pelos convênios
        """)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["📄 Input", "🚀 Execução", "📊 Resultados", "🔀 Correlação"])

    # ── TAB 1: INPUT ──────────────────────────────────────────────────────────
    with tab1:
        st.header("📂 Upload de Arquivos")
        st.markdown(
            "Envie os arquivos **PRODUCAO** (equipe de enfermagem) e **REPASSE** (hospital). "
            "Formatos aceitos: **Excel (.xlsx, .xls)**, PDF, Word (.docx), TXT e CSV."
        )

        col1, col2 = st.columns([2, 1])
        extratos_texto = []

        with col1:
            uploaded_files = st.file_uploader(
                "Upload de Arquivos de Endoscopia",
                type=["xlsx", "xls", "pdf", "docx", "txt", "csv"],
                accept_multiple_files=True,
                help="Envie os arquivos PRODUCAO e REPASSE",
            )

        with col2:
            if uploaded_files:
                st.subheader("Arquivos")
                for file in uploaded_files:
                    ext = file.name.rsplit(".", 1)[-1].lower()
                    icon = "📊" if ext in ("xlsx", "xls") else "📄"
                    st.success(f"{icon} {file.name}")
                    try:
                        file.seek(0, os.SEEK_END)
                        size = file.tell() / 1024
                        file.seek(0)
                        st.caption(f"{size:.1f} KB")
                    except Exception:
                        pass

        if uploaded_files:
            st.divider()
            with st.spinner("📖 Extraindo dados dos arquivos..."):
                for file in uploaded_files:
                    text = extract_text_from_file(file)
                    if text:
                        extratos_texto.append({"filename": file.name, "content": text})

            st.success(f"✅ {len(extratos_texto)} arquivo(s) processado(s)")
            st.session_state["extratos"] = extratos_texto

        if extratos_texto:
            st.divider()
            st.subheader("👁️ Preview dos Dados")
            for doc in extratos_texto:
                with st.expander(doc["filename"]):
                    text = doc["content"]
                    st.text(text[:2000])
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Caracteres", len(text))
                    c2.metric("Palavras", len(text.split()))
                    c3.metric("Linhas", len(text.splitlines()))

    # ── TAB 2: EXECUÇÃO ───────────────────────────────────────────────────────
    with tab2:
        st.header("🚀 Executar Análise dos Arquivos")
        st.markdown(
            "O **Analista de Endoscopia** irá ler cada arquivo, identificar se é "
            "PRODUCAO ou REPASSE, e estruturar os dados em CSV para o confronto posterior."
        )

        if not api_key:
            st.warning("⚠️ Por favor, configure a API Key na sidebar")

        extratos = st.session_state.get("extratos", [])
        if not extratos:
            st.warning("Envie os arquivos na aba Input")

        if st.button("🚀 Iniciar Análise", type="primary"):
            llm = get_llm("gemini/gemini-2.5-flash", custom_model, temperature, api_key)
            agents = create_agents(llm)
            resultados = {}

            progress_bar = st.progress(0, text="Aguardando início...")

            for i, doc in enumerate(extratos):
                filename = doc["filename"]
                text = doc["content"]
                total = len(extratos)

                progress_bar.progress(
                    i / total,
                    text=f"📂 Processando arquivo {i + 1} de {total}: **{filename}**",
                )

                with st.status(
                    f"🤖 Agente trabalhando em: {filename}", expanded=True
                ) as status_box:

                    st.markdown("##### 📡 Log de Execução em Tempo Real")
                    log_container = st.container(height=380, border=False)

                    log_queue: queue.Queue = queue.Queue(maxsize=500)
                    handler = StreamlitLogHandler(log_queue)
                    handler.setFormatter(
                        logging.Formatter("%(asctime)s | %(name)s | %(message)s",
                                          datefmt="%H:%M:%S")
                    )
                    root_logger = logging.getLogger()
                    root_logger.addHandler(handler)

                    thread_result: dict = {"value": None, "error": None}

                    def _run_crew(result_holder: dict, _text=text):
                        try:
                            tasks = create_tasks(agents, _text)
                            crew = Crew(
                                agents=agents,
                                tasks=tasks,
                                process=Process.sequential,
                                verbose=True,
                            )
                            result_holder["value"] = str(crew.kickoff())
                        except Exception as exc:
                            result_holder["error"] = exc
                            logger.error(f"Erro durante kickoff: {exc}", exc_info=True)

                    crew_thread = threading.Thread(
                        target=_run_crew,
                        args=(thread_result,),
                        daemon=True,
                    )
                    crew_thread.start()

                    while crew_thread.is_alive():
                        drained = False
                        while not log_queue.empty():
                            line = log_queue.get_nowait()
                            render_log_line(line, log_container)
                            drained = True
                        if not drained:
                            time.sleep(0.15)

                    while not log_queue.empty():
                        render_log_line(log_queue.get_nowait(), log_container)

                    crew_thread.join()
                    root_logger.removeHandler(handler)

                    if thread_result["error"]:
                        status_box.update(
                            label=f"❌ Erro em {filename}", state="error", expanded=True
                        )
                        st.error(f"Erro: {thread_result['error']}")
                    else:
                        resultados[filename] = thread_result["value"]
                        status_box.update(
                            label=f"✅ Concluído: {filename}", state="complete", expanded=False
                        )

                progress_bar.progress(
                    (i + 1) / total,
                    text=f"✅ {i + 1} de {total} arquivos concluídos",
                )

            st.session_state["results"] = resultados
            st.session_state["csvs_brutos"] = {
                fname: extrair_csv_do_texto(txt)
                for fname, txt in resultados.items()
            }
            st.success("🎉 Análise concluída! Veja os resultados na aba **📊 Resultados** ou inicie a correlação na aba **🔀 Correlação**.")

    # ── TAB 3: RESULTADOS ─────────────────────────────────────────────────────
    with tab3:
        st.header("📊 Resultados por Arquivo")
        results = st.session_state.get("results", None)

        if not results:
            st.info("Execute a análise na aba Execução")
        else:
            combined_output = ""
            for file, result in results.items():
                st.subheader(file)
                st.markdown(result)
                combined_output += f"# Resultado: {file}\n\n{result}\n\n{'-' * 36}\n\n"

            st.divider()
            st.subheader("📄 Resultado Consolidado")
            st.text_area("Relatório completo", value=combined_output, height=400)

    # ── TAB 4: CORRELAÇÃO ─────────────────────────────────────────────────────
    with tab4:
        st.header("🔀 Correlação — PRODUCAO × REPASSE")
        st.markdown(
            "Gera um **único CSV correlacionado** a partir de todos os arquivos processados, "
            "confrontando a produtividade da equipe com os repasses do hospital. "
            "Identifica glosas, divergências de valor e procedimentos não faturados."
        )

        csvs_brutos = st.session_state.get("csvs_brutos", {})

        if not csvs_brutos:
            st.info("⬅️ Primeiro processe os arquivos na aba **🚀 Execução**.")
        else:
            with st.expander(f"📋 CSVs individuais disponíveis ({len(csvs_brutos)} arquivo(s))", expanded=False):
                for fname, csv_txt in csvs_brutos.items():
                    st.markdown(f"**{fname}**")
                    df_prev = texto_para_dataframe(csv_txt)
                    if df_prev is not None and not df_prev.empty:
                        st.dataframe(df_prev, use_container_width=True, height=200)
                    else:
                        st.text(csv_txt[:500] + ("..." if len(csv_txt) > 500 else ""))
                    st.divider()

            if st.button("🔀 Gerar Correlação", type="primary"):

                with st.status("🤖 Agente Correlacionador trabalhando...", expanded=True) as status_corr:
                    st.markdown("##### 📡 Log de Correlação em Tempo Real")
                    log_container_corr = st.container(height=320, border=False)

                    log_queue_corr: queue.Queue = queue.Queue(maxsize=500)
                    handler_corr = StreamlitLogHandler(log_queue_corr)
                    handler_corr.setFormatter(
                        logging.Formatter("%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")
                    )
                    root_logger = logging.getLogger()
                    root_logger.addHandler(handler_corr)

                    thread_result_corr: dict = {"value": None, "error": None}

                    def _run_correlation(result_holder: dict):
                        try:
                            llm_corr = get_llm(
                                "gemini/gemini-2.5-flash", custom_model, temperature, api_key
                            )
                            correlator = create_correlator_agent(llm_corr)
                            task_corr = create_correlation_task(correlator, csvs_brutos)
                            crew_corr = Crew(
                                agents=[correlator],
                                tasks=[task_corr],
                                process=Process.sequential,
                                verbose=True,
                            )
                            result_holder["value"] = str(crew_corr.kickoff())
                        except Exception as exc:
                            result_holder["error"] = exc
                            logger.error(f"Erro na correlação: {exc}", exc_info=True)

                    thread_corr = threading.Thread(
                        target=_run_correlation,
                        args=(thread_result_corr,),
                        daemon=True,
                    )
                    thread_corr.start()

                    while thread_corr.is_alive():
                        drained = False
                        while not log_queue_corr.empty():
                            render_log_line(log_queue_corr.get_nowait(), log_container_corr)
                            drained = True
                        if not drained:
                            time.sleep(0.15)

                    while not log_queue_corr.empty():
                        render_log_line(log_queue_corr.get_nowait(), log_container_corr)

                    thread_corr.join()
                    root_logger.removeHandler(handler_corr)

                    if thread_result_corr["error"]:
                        status_corr.update(
                            label="❌ Erro na correlação", state="error", expanded=True
                        )
                        st.error(f"Erro: {thread_result_corr['error']}")
                    else:
                        status_corr.update(
                            label="✅ Correlação concluída!", state="complete", expanded=False
                        )
                        st.session_state["csv_correlacionado"] = thread_result_corr["value"]

            # ── Exibe resultado correlacionado ────────────────────────────────
            csv_correlacionado_raw = st.session_state.get("csv_correlacionado")

            if csv_correlacionado_raw:
                st.divider()

                csv_limpo = extrair_csv_do_texto(csv_correlacionado_raw)
                csv_dados_str, resumo_str = separar_resumo_do_csv(csv_limpo)

                st.subheader("📊 Tabela Correlacionada")
                df_final = texto_para_dataframe(csv_dados_str)

                if df_final is not None and not df_final.empty:
                    # Métricas rápidas
                    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                    total_linhas = len(df_final)

                    status_col = df_final.get("StatusCorrelacao", pd.Series(dtype=str))
                    n_correlacionado = (status_col.str.upper() == "CORRELACIONADO").sum()
                    n_divergencia = status_col.str.upper().str.startswith("DIVERGENCIA").sum()
                    n_glosa = status_col.str.upper().str.startswith("GLOSA").sum()
                    n_nao_faturado = (status_col.str.upper() == "NAO_FATURADO").sum()

                    col_m1.metric("📄 Total de Linhas", total_linhas)
                    col_m2.metric("✅ Correlacionados", n_correlacionado)
                    col_m3.metric("⚠️ Divergências de Valor", int(n_divergencia))
                    col_m4.metric("🚫 Glosas", int(n_glosa))
                    col_m5.metric("❌ Não Faturados", int(n_nao_faturado))

                    # Filtros interativos
                    with st.expander("🔍 Filtros", expanded=False):
                        fcol1, fcol2, fcol3 = st.columns(3)

                        convenios_disp = sorted(df_final.get("Convenio", pd.Series()).dropna().unique().tolist())
                        filtro_convenio = fcol1.multiselect(
                            "Convênio", convenios_disp, default=convenios_disp
                        )

                        status_disp = sorted(df_final.get("StatusCorrelacao", pd.Series()).dropna().unique().tolist())
                        filtro_status = fcol2.multiselect(
                            "Status Correlação", status_disp, default=status_disp
                        )

                        tuss_disp = sorted(df_final.get("CodigoTUSS", pd.Series()).dropna().unique().tolist())
                        filtro_tuss = fcol3.multiselect(
                            "Código TUSS", tuss_disp, default=tuss_disp
                        )

                    # Aplica filtros
                    df_filtrado = df_final.copy()
                    if "Convenio" in df_filtrado.columns and filtro_convenio:
                        df_filtrado = df_filtrado[df_filtrado["Convenio"].isin(filtro_convenio)]
                    if "StatusCorrelacao" in df_filtrado.columns and filtro_status:
                        df_filtrado = df_filtrado[df_filtrado["StatusCorrelacao"].isin(filtro_status)]
                    if "CodigoTUSS" in df_filtrado.columns and filtro_tuss:
                        df_filtrado = df_filtrado[df_filtrado["CodigoTUSS"].isin(filtro_tuss)]

                    # Destaque visual por status
                    def highlight_status(row):
                        status = str(row.get("StatusCorrelacao", "")).upper()
                        if status == "CORRELACIONADO":
                            return ["background-color: #d4edda"] * len(row)
                        elif status.startswith("DIVERGENCIA"):
                            return ["background-color: #fff3cd"] * len(row)
                        elif status.startswith("GLOSA"):
                            return ["background-color: #f8d7da"] * len(row)
                        elif status == "NAO_FATURADO":
                            return ["background-color: #f8d7da"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        df_filtrado.style.apply(highlight_status, axis=1),
                        use_container_width=True,
                        height=460,
                    )

                    # Download CSV filtrado
                    csv_download = df_filtrado.to_csv(index=False, sep=",", encoding="utf-8-sig")
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="⬇️ Baixar CSV Correlacionado",
                        data=csv_download.encode("utf-8-sig"),
                        file_name=f"correlacao_endoscopia_{ts}.csv",
                        mime="text/csv",
                        type="primary",
                    )

                else:
                    st.warning("⚠️ Não foi possível renderizar o DataFrame. Exibindo CSV bruto.")
                    st.text_area("CSV bruto", value=csv_dados_str, height=300)
                    st.download_button(
                        label="⬇️ Baixar CSV Bruto",
                        data=csv_dados_str.encode("utf-8-sig"),
                        file_name=f"correlacao_bruta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                    )

                # Resumo de divergências por convênio
                if resumo_str:
                    st.divider()
                    st.subheader("📋 Resumo — Divergências por Convênio")
                    st.markdown(resumo_str)


if __name__ == "__main__":
    main()
