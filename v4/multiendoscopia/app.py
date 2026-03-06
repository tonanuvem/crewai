""" app-endoscopia-v3
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

def _resolve_log_path() -> Path:
    candidates = [Path("logs"), Path("/tmp/endoscopia_logs")]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            return candidate
        except OSError:
            continue
    return Path("/tmp")

log_dir = _resolve_log_path()

_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    _log_handlers.insert(0, logging.FileHandler(log_dir / "crew_logs.log", encoding="utf-8"))
except OSError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
    force=True,
)
logger = logging.getLogger(__name__)


# =============================================================================
# VALORES PADRÃO DOS AGENTES E TASKS
# =============================================================================

ANALISTA_DEFAULTS = {
    "role": "Analista de Controle dos procedimentos de Endoscopia",
    "goal": """
- Retornar APENAS o CSV puro, sem markdown, sem explicações.
- Primeira linha obrigatoriamente o cabeçalho:
- Padronizar Data para DD/MM/AAAA.
- Padronizar nomes de paciente em MAIÚSCULAS sem espaços extras.
- Identificar o tipo pelo nome da planilha: PRODUCAO ou REPASSE

- Cada exame realizado gera UMA linha no CSV de saída.
- Se houver PROCEDIMENTOS ADICIONAIS preenchidos na planilha PRODUCAO, gerar uma linha EXTRA para cada procedimento adicional listado (ex: "TESTE DE UREASE" vira linha separada).
- Coluna TipoArquivo = "PRODUCAO" ou "REPASSE".
""",
    "backstory": """
Expert em análise de faturamento hospitalar e auditoria de convênios médicos.
Especializado na Terminologia Unificada da Saúde Suplementar (TUSS) e nas regras de
faturamento dos principais convênios do Brasil.
Conhece em profundidade os campos das planilhas de produtividade de equipes de enfermagem
e os arquivos de repasse hospitalares (formato Hospital São Camilo e similares).
Sabe que o número de atendimento pode divergir entre os dois arquivos para o mesmo
paciente/procedimento, portanto não usa esse campo como chave única.
Seu principal objetivo é estruturar os dados com máxima fidelidade para que o agente
correlacionador consiga fazer o batimento correto.
    """,
    "task_description_template": """
Retorne APENAS o CSV puro, sem markdown, sem explicações.
Cabeçalho obrigatório na primeira linha
Não omita nenhuma linha — cada procedimento registrado deve constar no CSV gerado.
=== CONTEÚDO DO ARQUIVO ===
{conteudo_arquivo}
    """,
    "task_expected_output": (
        "CSV puro com cabeçalho na primeira linha, todas as linhas do arquivo estruturadas e coluna TipoArquivo preenchida com PRODUCAO ou REPASSE."
    ),
}

CORRELACIONADOR_DEFAULTS = {
    "role": "Correlacionador dos registros de endoscopia",
    "goal": """
Receber os CSVs padronizados gerados pelo Analista — um do tipo PRODUCAO e outro do tipo REPASSE — e realizar o Batimento Automático linha a linha, considerando as seguintes regras:

- A primeira linha deve ser obrigatoriamente o cabeçalho, indicando de qual planilha veio aquela coluna (acrescentar sufixo _PRODUCAO ou _REPASSE)
- NÃO remover nenhuma linha da PRODUCAO; Ordenar por Data crescente; Padronizar Data para DD/MM/AAAA.
- Padronizar ValorLiberado: ponto decimal, sem símbolo de moeda. 

- A saída do CSV_CORRELACAO deve conter todas as linhas do CSV de PRODUÇÃO como a base da sua resposta, onde devem ser incluídas as novas colunas com o relacionamento do CSV de REPASSE, sendo que para cada linha da PRODUCAO, deve tentar encontrar correspondência no REPASSE usando a chave composta com 3 campos (data + paciente + procedimento). Devem ser incluídas em cada linha somente as colunas do CSV de REPASSE que ainda não exista no CSV de PRODUÇÃO, e também deve ser incluída uma nova coluna de StatusCorrelacao, considerando a seguinte regra:
   a. Se ValorLiberado coincidir (ou REPASSE não tiver valor): StatusCorrelacao = "CORRELACIONADO"
   b. Se ValorLiberado for menor no REPASSE: StatusCorrelacao = "CORRELACIONADO_COM_DIVERGENCIA_VALOR"
   c. Se ValorLiberado = 0 no REPASSE: StatusCorrelacao = "CORRELACIONADO_COM_GLOSA_TOTAL"
   d. Se ValorLiberado > 0 mas menor que esperado: StatusCorrelacao = "CORRELACIONADO_COM_GLOSA_PARCIAL"
   e. Se NÃO encontrar correspondência no REPASSE: StatusCorrelacao = "NAO_FATURADO_NO_REPASSE"

- Para linhas do REPASSE sem correspondência na PRODUCAO, inserir no final do arquivo CSV_CORRELACAO as linhas como valores zerados do PRODUCAO e os valores existentes da PRODUÇÃO, e com nova coluna StatusCorrelacao = "REPASSE_NAO_IDENTIFICADO_NA_PRODUCAO"

- Para fazer esse relacionamento, deve-se usar a chave de correlação COMPOSTA pelos 3 campos a seguir:
  1. Data (DD/MM/AAAA) — tolerância de ± 1 dia para o mesmo episódio
  2. Paciente (nome normalizado em maiúsculas)
  3. Procedimento (correspondência semântica: "COLONOSCOPIA" bate com "Colonoscopia (Inclui A Retossigmoidoscopia)", "TESTE DE UREASE" bate com "Pesquisa de H. pylori - Teste da Urease", etc.)
    """,
    "backstory": """
Especialista em auditoria de faturamento médico, ETL e reconciliação de dados hospitalares.
Usa correspondência semântica para não perder correlações válidas.
Nunca inventa procedimentos — apenas padroniza, correlaciona e sinaliza divergências.
Seu trabalho alimenta diretamente a cobrança estruturada junto ao hospital e convênios.
    """,
    "task_description_template": """
Você recebeu os seguintes blocos CSV padronizados pelo Analista de Endoscopia, identificados como PRODUCAO e REPASSE. Execute o batimento automático conforme as regras do seu objetivo (goal), usando chave composta de Data + Paciente + Procedimento.
- Retorne APENAS o CSV correlacionado
- A primeira linha deve ser obrigatoriamente o cabeçalho
=== CONTEÚDO ===
{blocos}
    """,
    "task_expected_output": (
        "CSV puro com cabeçalho na primeira linha, todas as linhas da PRODUCAO como base, colunas complementares do REPASSE adicionadas e coluna StatusCorrelacao preenchida em cada linha."
    ),
}


def _init_agent_session_state():
    """
    Inicializa o session_state com os valores padrão dos agentes,
    caso ainda não existam (chamado uma vez no início do main).
    """
    if "analista_cfg" not in st.session_state:
        st.session_state["analista_cfg"] = dict(ANALISTA_DEFAULTS)
    if "correlacionador_cfg" not in st.session_state:
        st.session_state["correlacionador_cfg"] = dict(CORRELACIONADOR_DEFAULTS)


def _get_analista_cfg() -> dict:
    return st.session_state.get("analista_cfg", ANALISTA_DEFAULTS)


def _get_correlacionador_cfg() -> dict:
    return st.session_state.get("correlacionador_cfg", CORRELACIONADOR_DEFAULTS)


# =============================================================================
# HANDLER DE LOG EM TEMPO REAL PARA O STREAMLIT
# =============================================================================

class StreamlitLogHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        try:
            self.log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


def render_log_line(line: str, container) -> None:
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
    try:
        doc = Document(file)
        text = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(text)
    except Exception as e:
        st.error(f"Erro ao ler arquivo Word: {e}")
        return None


def read_pdf_file(file) -> str:
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
    try:
        file.seek(0)
        xls = pd.ExcelFile(file, engine="openpyxl")
        blocos = []
        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name, dtype=str)
            df.fillna("", inplace=True)
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
# CONFIGURAÇÃO DO LLM
# =============================================================================

@st.cache_resource
def get_llm(model_choice: str, custom_model: str, temperature: float, api_key: str) -> LLM:
    if not api_key:
        st.error("⚠️ API Key não configurada!")
        st.stop()

    model_name = custom_model.strip() if custom_model and custom_model.strip() else model_choice

    if "gemini" in model_name.lower() and not model_name.startswith("google/"):
        bare = model_name.split("/")[-1]
        model_name = f"google/{bare}"

    try:
        return LLM(model=model_name, api_key=api_key, temperature=temperature)
    except Exception as e:
        st.error(f"Erro ao inicializar o modelo '{model_name}': {e}")
        st.info("Confira se o nome do modelo está correto. Exemplo: gemini-2.5-flash-lite")
        st.stop()


# =============================================================================
# CRIAÇÃO DOS AGENTES  ← usam session_state quando disponível
# =============================================================================

def create_agents(llm, verbose_mode: bool = False) -> list:
    cfg = _get_analista_cfg()
    multiendoscopia_analista = Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"],
        llm=llm,
        verbose=verbose_mode,
        allow_delegation=False,
    )
    return [multiendoscopia_analista]


def create_correlator_agent(llm, verbose_mode: bool = False) -> Agent:
    cfg = _get_correlacionador_cfg()
    return Agent(
        role=cfg["role"],
        goal=cfg["goal"],
        backstory=cfg["backstory"],
        llm=llm,
        verbose=verbose_mode,
        allow_delegation=False,
    )


def create_correlation_task(correlator_agent: Agent, csvs_por_arquivo: dict) -> Task:
    cfg = _get_correlacionador_cfg()
    blocos = "\n\n".join(
        f"=== ARQUIVO: {fname} ===\n{csv_text}"
        for fname, csv_text in csvs_por_arquivo.items()
    )
    description = cfg["task_description_template"].replace("{blocos}", blocos)
    return Task(
        description=description,
        expected_output=cfg["task_expected_output"],
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
    match = re.search(r"```(?:csv)?\s*\n(.*?)```", texto, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    linhas_csv = [
        linha for linha in texto.splitlines()
        if linha.count(",") >= 4 or linha.startswith("Data,")
    ]
    return "\n".join(linhas_csv).strip()


def separar_resumo_do_csv(texto_csv: str) -> tuple[str, str]:
    marcador = "# RESUMO_DIVERGENCIAS_POR_CONVENIO"
    if marcador in texto_csv:
        partes = texto_csv.split(marcador, 1)
        return partes[0].strip(), partes[1].strip()
    return texto_csv.strip(), ""


def texto_para_dataframe(csv_texto: str) -> pd.DataFrame | None:
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
# CRIAÇÃO DAS TASKS  ← usa session_state quando disponível
# =============================================================================

def create_tasks(agents: list, conteudo_arquivo: str) -> list:
    cfg = _get_analista_cfg()
    description = cfg["task_description_template"].replace("{conteudo_arquivo}", conteudo_arquivo)
    task_analise = Task(
        description=description,
        expected_output=cfg["task_expected_output"],
        agent=agents[0],
    )
    return [task_analise]


# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

def render_agent_form(agent_key: str, defaults: dict, title: str, icon: str):
    """
    Renderiza o formulário de edição de um agente.
    Salva os valores em st.session_state[agent_key].
    """
    cfg = st.session_state.get(agent_key, dict(defaults))

    st.markdown(f"### {icon} {title}")

    with st.container(border=True):
        col_info, col_reset = st.columns([5, 1])
        with col_info:
            st.caption("Edite os campos abaixo e clique em **Salvar Alterações** para aplicar.")
        with col_reset:
            if st.button("↩️ Restaurar", key=f"reset_{agent_key}", help="Volta aos valores padrão originais"):
                st.session_state[agent_key] = dict(defaults)
                st.rerun()

        new_role = st.text_input(
            "🏷️ Role (papel do agente)",
            value=cfg.get("role", ""),
            key=f"{agent_key}_role",
            help="Define o papel/função do agente dentro do crew.",
        )

        new_goal = st.text_area(
            "🎯 Goal (objetivo)",
            value=cfg.get("goal", ""),
            height=320,
            key=f"{agent_key}_goal",
            help="Descreve o objetivo principal do agente — instruções detalhadas de comportamento.",
        )

        new_backstory = st.text_area(
            "📖 Backstory (contexto/experiência)",
            value=cfg.get("backstory", ""),
            height=180,
            key=f"{agent_key}_backstory",
            help="Contexto e experiência do agente — usado para orientar o tom e o raciocínio.",
        )

        st.divider()
        st.markdown("#### 📋 Task associada")

        new_task_desc = st.text_area(
            "📝 Task Description (template)",
            value=cfg.get("task_description_template", ""),
            height=280,
            key=f"{agent_key}_task_desc",
            help=(
                "Template da instrução enviada ao agente em cada execução. "
                "Use {conteudo_arquivo} (Analista) ou {blocos} (Correlacionador) "
                "como placeholder do conteúdo dinâmico."
            ),
        )

        new_task_output = st.text_area(
            "✅ Task Expected Output (saída esperada)",
            value=cfg.get("task_expected_output", ""),
            height=100,
            key=f"{agent_key}_task_output",
            help="Descreve o formato/conteúdo esperado na saída da task.",
        )

        col_save, col_status = st.columns([2, 5])
        with col_save:
            if st.button(f"💾 Salvar Alterações — {title}", key=f"save_{agent_key}", type="primary"):
                st.session_state[agent_key] = {
                    "role": new_role,
                    "goal": new_goal,
                    "backstory": new_backstory,
                    "task_description_template": new_task_desc,
                    "task_expected_output": new_task_output,
                }
                with col_status:
                    st.success(f"✅ Configuração do **{title}** salva com sucesso!")


def main():
    st.set_page_config(
        page_title="Endoscopia | Controle de Procedimentos",
        page_icon="🔬",
        layout="wide",
    )

    # Inicializa os defaults dos agentes no session_state (executado uma vez por sessão)
    _init_agent_session_state()

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
            "🤖 Modelo Gemini",
            value="gemini-2.5-flash-lite",
            help="Digite só o nome do modelo. Exemplos: gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro",
        )
        temperature = st.slider(
            "🌡️ Temperatura",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.1,
            help="0 = determinístico | 1 = criativo",
        )

        verbose_mode = st.toggle(
            "🔊 Modo Verbose",
            value=False,
            help="Ativado: exibe o raciocínio detalhado dos agentes (mais tokens). "
                 "Desativado: apenas o resultado final (mais econômico).",
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
    tab1, tab2, tab3, tab4, tab_agents = st.tabs([
        "📄 Input",
        "🚀 Execução",
        "📊 Resultados",
        "🔀 Correlação",
        "🤖 Agentes",
    ])

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
            llm = get_llm("gemini-2.5-flash-lite", custom_model, temperature, api_key)
            agents = create_agents(llm, verbose_mode)
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
                                verbose=verbose_mode,
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
                                "gemini-2.5-flash-lite", custom_model, temperature, api_key
                            )
                            correlator = create_correlator_agent(llm_corr, verbose_mode)
                            task_corr = create_correlation_task(correlator, csvs_brutos)
                            crew_corr = Crew(
                                agents=[correlator],
                                tasks=[task_corr],
                                process=Process.sequential,
                                verbose=verbose_mode,
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
                    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                    total_linhas = len(df_final)

                    status_col = df_final.get("StatusCorrelacao", pd.Series(dtype=str))
                    n_correlacionado = (status_col.str.upper() == "CORRELACIONADO").sum()
                    n_divergencia    = status_col.str.upper().str.contains("DIVERGENCIA_VALOR").sum()
                    n_glosa          = status_col.str.upper().str.contains("GLOSA").sum()
                    n_nao_faturado   = (status_col.str.upper() == "NAO_FATURADO_NO_REPASSE").sum()

                    col_m1.metric("📄 Total de Linhas",       total_linhas)
                    col_m2.metric("✅ Correlacionados",        n_correlacionado)
                    col_m3.metric("⚠️ Divergências de Valor",  int(n_divergencia))
                    col_m4.metric("🚫 Glosas",                 int(n_glosa))
                    col_m5.metric("❌ Não Faturados",           int(n_nao_faturado))

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

                    df_filtrado = df_final.copy()
                    if "Convenio" in df_filtrado.columns and filtro_convenio:
                        df_filtrado = df_filtrado[df_filtrado["Convenio"].isin(filtro_convenio)]
                    if "StatusCorrelacao" in df_filtrado.columns and filtro_status:
                        df_filtrado = df_filtrado[df_filtrado["StatusCorrelacao"].isin(filtro_status)]
                    if "CodigoTUSS" in df_filtrado.columns and filtro_tuss:
                        df_filtrado = df_filtrado[df_filtrado["CodigoTUSS"].isin(filtro_tuss)]

                    def highlight_status(row):
                        status = str(row.get("StatusCorrelacao", "")).upper()
                        if status == "CORRELACIONADO":
                            return ["background-color: #d4edda"] * len(row)
                        elif "DIVERGENCIA" in status:
                            return ["background-color: #fff3cd"] * len(row)
                        elif "GLOSA" in status:
                            return ["background-color: #f8d7da"] * len(row)
                        elif "NAO_FATURADO" in status:
                            return ["background-color: #f8d7da"] * len(row)
                        elif "NAO_IDENTIFICADO" in status:
                            return ["background-color: #e2e3e5"] * len(row)
                        return [""] * len(row)

                    st.dataframe(
                        df_filtrado.style.apply(highlight_status, axis=1),
                        use_container_width=True,
                        height=460,
                    )

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

                if resumo_str:
                    st.divider()
                    st.subheader("📋 Resumo — Divergências por Convênio")
                    st.markdown(resumo_str)

    # ── TAB 5: AGENTES ────────────────────────────────────────────────────────
    with tab_agents:
        st.header("🤖 Configuração dos Agentes")
        st.markdown(
            "Visualize e edite os prompts de cada agente e suas tasks. "
            "As alterações ficam ativas **durante esta sessão** e são aplicadas "
            "imediatamente nas próximas execuções.\n\n"
            "> 💡 Use o botão **↩️ Restaurar** para voltar ao texto original a qualquer momento."
        )

        # Indicador de estado atual
        analista_modificado = st.session_state.get("analista_cfg") != ANALISTA_DEFAULTS
        correlacionador_modificado = st.session_state.get("correlacionador_cfg") != CORRELACIONADOR_DEFAULTS

        col_ind1, col_ind2, col_ind3 = st.columns([2, 2, 3])
        with col_ind1:
            if analista_modificado:
                st.warning("✏️ Analista: configuração **personalizada**")
            else:
                st.success("✅ Analista: configuração **padrão**")
        with col_ind2:
            if correlacionador_modificado:
                st.warning("✏️ Correlacionador: configuração **personalizada**")
            else:
                st.success("✅ Correlacionador: configuração **padrão**")
        with col_ind3:
            if analista_modificado or correlacionador_modificado:
                if st.button("↩️ Restaurar TODOS os agentes ao padrão", type="secondary"):
                    st.session_state["analista_cfg"] = dict(ANALISTA_DEFAULTS)
                    st.session_state["correlacionador_cfg"] = dict(CORRELACIONADOR_DEFAULTS)
                    st.rerun()

        st.divider()

        agent_tab1, agent_tab2 = st.tabs([
            "🔍 Analista de Endoscopia",
            "🔀 Correlacionador",
        ])

        with agent_tab1:
            render_agent_form(
                agent_key="analista_cfg",
                defaults=ANALISTA_DEFAULTS,
                title="Analista de Endoscopia",
                icon="🔍",
            )
            st.divider()
            with st.expander("ℹ️ Sobre o placeholder `{conteudo_arquivo}`", expanded=False):
                st.markdown("""
O campo **Task Description** do Analista usa o placeholder `{conteudo_arquivo}`.

Durante a execução, ele é substituído automaticamente pelo conteúdo extraído de cada arquivo enviado na aba **📄 Input**.

**Não remova este placeholder** — sem ele, o agente não receberá os dados do arquivo.
                """)

        with agent_tab2:
            render_agent_form(
                agent_key="correlacionador_cfg",
                defaults=CORRELACIONADOR_DEFAULTS,
                title="Correlacionador",
                icon="🔀",
            )
            st.divider()
            with st.expander("ℹ️ Sobre o placeholder `{blocos}`", expanded=False):
                st.markdown("""
O campo **Task Description** do Correlacionador usa o placeholder `{blocos}`.

Durante a execução da correlação, ele é substituído automaticamente pelos CSVs gerados pelo Analista para cada arquivo processado.

**Não remova este placeholder** — sem ele, o agente não receberá os dados para o batimento.
                """)


if __name__ == "__main__":
    main()
