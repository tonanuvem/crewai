""" app-v5
Interface Streamlit para Sistema Open Finance Multi-Agente

Instalar:
    pip install streamlit crewai python-dotenv pypdf

Executar:
    streamlit run app_streamlit.py
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
            pass  # Descarta silenciosamente se a fila estiver cheia


def render_log_line(line: str, container) -> None:
    """
    Renderiza uma linha de log com ícone e cor de acordo com o conteúdo.
    Chamada apenas pela thread principal do Streamlit.
    """
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
        # uploaded_file.read() retorna bytes no Streamlit
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="ignore")
        return str(raw)
    except Exception as e:
        st.error(f"Erro ao ler arquivo de texto: {e}")
        return None


def extract_text_from_file(uploaded_file) -> str:
    """Extrai texto de diferentes tipos de arquivo."""
    if uploaded_file is None:
        return None

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    uploaded_file.seek(0)

    readers = {
        "docx": read_word_file,
        "pdf": read_pdf_file,
        "txt": read_text_file,
        "csv": read_text_file,
    }

    reader = readers.get(extension)
    if reader:
        return reader(uploaded_file)

    st.error(f"Formato de arquivo não suportado: .{extension}")
    return None


def save_agent_outputs(individual_results: dict, timestamp: datetime):
    """Salva os resultados de cada agente em arquivos específicos."""
    output_dir = Path("outputs") / timestamp.strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    file_mappings = {
        "Analista de Domínio Especialista": ("domain_storytelling.md", "md"),
        "Product Owner Ágil": ("user_stories.md", "md"),
        "QA Engineer BDD": ("scenarios.feature", "feature"),
        "Senior Developer": ("implementation.py", "py"),
        "Code Reviewer": ("review_report.md", "md"),
    }

    saved_files = []
    for role, result in individual_results.items():
        if role not in file_mappings:
            continue
        filename, _ = file_mappings[role]
        file_path = output_dir / filename
        try:
            file_path.write_text(result, encoding="utf-8")
            saved_files.append(str(file_path))
            logger.info(f"Arquivo salvo: {file_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar {file_path}: {e}")

    return saved_files, str(output_dir)


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

    # Garante prefixo gemini/ para modelos Gemini
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
    """Cria os agentes especializados do Open Finance."""
    multibank_analyst = Agent(
        role="Analista de Controle Multibanco",
        goal="""Compreender as receitas e despesas detalhadamente de cada mês e categorizar
considerando que existem diversas fontes de receitas:
- ENDOPRIME: recebimento de PIX TRANSF SOCIEDA no extrato PJ-ITAU
- PRO-LABORE-ENDOPRIME: recebimento de SISPAG ENDOPRIME SERVICOS no extrato PF-ITAU
- PROFESSORA-UNIVERSIDADE-ANHEMBI: recebimento de REMUNERACAO/SALARIO no extrato PF-ITAU
- CONSULTORIO-GASTROPREV: recebimento de Pix Recebido de Pacientes no extrato PJ-BB
- PRO-LABORE-GASTROPREV: recebimento de GOMES E UCHOA no extrato PF-BB
- PREFEITURA-GASTRO: recebimento de SECRETARIA MUNICIPAL no extrato PF-BB
- CONSULTORIO-GASTROPREV: recebimento de MEDICINA EM no extrato PF-BB
- OUTROS-RECEBIMENTOS: propor categorias com base no tipo do recebimento

E diversas categorias de despesas:
- PAGAMENTOS-MEDICOS-ENDOPRIME: pagamento de Sispag Fornecedores no extrato PJ-ITAU
  e pagamento PIX TRANSF Michele no extrato PF-ITAU
- TRIBUTOS-GOV: pagamento de tributos e contribuições ao INSS nas contas PJ-ITAU e PJ-BB
- DESPESAS-DEDUTIVEIS-ENDOPRIME: pagamentos no contexto da LC 214/25 e do Art. 57
  (Aluguel, Alimentação, Telefone, Marketing, Material Escritório, Combustível,
  Curso/Capacitação, Estacionamento, Contabilidade) no extrato PJ-ITAU
- DESPESAS-DEDUTIVEIS-GASTROPREV: pagamentos no contexto da LC 214/25 e do Art. 57
  nas demais contas (Aluguel via PIX TRANSF MEDICIN em PF-ITAU, Marketing via PIX TRANSF
  EMANUEL em PF-ITAU, Médico Fornecedor via PIX TRANSF AMANDA em PF-ITAU, Contabilidade
  via PIX TRANSF LIZANDR em PF-ITAU)
- OUTROS-PAGAMENTOS: propor categorias com base no tipo do pagamento
  (ex: PIX TRANSF ANDRE em PF-ITAU = despesas residenciais)""",
        backstory="""Expert em análise financeira, contabilidade e planejamento tributário.
Identifica categorias de receita e despesas para categorização.
O foco das despesas dedutíveis é somente para Pessoa Jurídica.
Principal objetivo: evidenciar as principais receitas, despesas e lucro das entidades:
ENDOPRIME, GASTROPREV (antiga GOMES e UCHOA), PROFESSORA,
PROFESSORA-UNIVERSIDADE-ANHEMBI e PREFEITURA-GASTRO.""",
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )
    return [multibank_analyst]


def create_consolidator_agent(llm) -> Agent:
    """Cria o agente consolidador de CSVs de múltiplos extratos."""
    return Agent(
        role="Consolidador Financeiro Multi-Extrato",
        goal="""Receber os dados CSV brutos gerados pela análise de múltiplos extratos bancários
e produzir um único CSV consolidado, limpo e padronizado, com as colunas obrigatórias:
Data, Conta, Descrição, Valor, Tipo, Categoria, Entidade.

Regras obrigatórias:
1. Remover linhas duplicadas exatas.
2. Padronizar a coluna Data para o formato DD/MM/AAAA.
3. Padronizar a coluna Valor: usar ponto como separador decimal, sem símbolo de moeda.
4. Padronizar Tipo para exatamente "RECEITA" ou "DESPESA" (maiúsculas).
5. Garantir que todas as colunas obrigatórias estejam presentes em cada linha.
6. Ordenar o resultado por Data (crescente) e depois por Entidade.
7. Ao final do CSV, adicionar uma seção de resumo com o Lucro por Entidade por Mês,
   separada do corpo por uma linha em branco e o cabeçalho: # RESUMO_LUCRO_POR_ENTIDADE.""",
        backstory="""Especialista em ETL financeiro e qualidade de dados.
Transforma saídas textuais heterogêneas de múltiplos agentes em um único dataset
estruturado, pronto para importação em Excel, Power BI ou Google Sheets.
Nunca inventa transações — apenas padroniza e organiza o que foi recebido.""",
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )


def create_consolidation_task(consolidator_agent: Agent, csvs_por_arquivo: dict) -> Task:
    """Cria a task de consolidação recebendo o dicionário {filename: csv_bruto}."""
    blocos = "\n\n".join(
        f"=== EXTRATO: {fname} ===\n{csv_text}"
        for fname, csv_text in csvs_por_arquivo.items()
    )
    return Task(
        description=f"""Você recebeu os seguintes blocos CSV, cada um gerado pela análise
de um extrato bancário diferente. Consolide-os em um único CSV seguindo rigorosamente
as regras definidas no seu objetivo (goal).

{blocos}

IMPORTANTE:
- Retorne APENAS o CSV consolidado (mais a seção de resumo ao final).
- Não inclua explicações, markdown, nem blocos de código — apenas o conteúdo puro do CSV.
- A primeira linha deve ser obrigatoriamente o cabeçalho:
  Data,Conta,Descrição,Valor,Tipo,Categoria,Entidade""",
        expected_output=(
            "CSV puro com cabeçalho 'Data,Conta,Descrição,Valor,Tipo,Categoria,Entidade', "
            "seguido de todas as linhas de transação ordenadas por Data e Entidade, "
            "e ao final a seção '# RESUMO_LUCRO_POR_ENTIDADE' com o lucro por entidade por mês."
        ),
        agent=consolidator_agent,
    )


# =============================================================================
# UTILITÁRIOS DE CSV
# =============================================================================

COLUNAS_ESPERADAS = ["Data", "Conta", "Descrição", "Valor", "Tipo", "Categoria", "Entidade"]


def extrair_csv_do_texto(texto: str) -> str:
    """
    Extrai o bloco CSV de dentro de uma resposta que pode conter texto livre,
    blocos markdown (```csv ... ```) ou conteúdo puro.
    Retorna apenas as linhas CSV válidas (com vírgulas).
    """
    # Tenta extrair bloco ```csv ... ``` ou ``` ... ```
    match = re.search(r"```(?:csv)?\s*\n(.*?)```", texto, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Fallback: pega todas as linhas que parecem CSV (contêm pelo menos 6 vírgulas → 7 colunas)
    linhas_csv = [
        linha for linha in texto.splitlines()
        if linha.count(",") >= 6 or linha.startswith("Data,")
    ]
    return "\n".join(linhas_csv).strip()


def separar_resumo_do_csv(texto_csv: str) -> tuple[str, str]:
    """
    Separa o bloco de dados do bloco de resumo (marcado por # RESUMO_LUCRO_POR_ENTIDADE).
    Retorna (csv_puro, resumo_texto).
    """
    if "# RESUMO_LUCRO_POR_ENTIDADE" in texto_csv:
        partes = texto_csv.split("# RESUMO_LUCRO_POR_ENTIDADE", 1)
        return partes[0].strip(), partes[1].strip()
    return texto_csv.strip(), ""


def texto_para_dataframe(csv_texto: str) -> pd.DataFrame | None:
    """
    Converte texto CSV em DataFrame pandas.
    Retorna None em caso de falha.
    """
    try:
        csv_limpo = extrair_csv_do_texto(csv_texto)
        csv_dados, _ = separar_resumo_do_csv(csv_limpo)
        df = pd.read_csv(io.StringIO(csv_dados), sep=",", dtype=str)
        # Normaliza nomes de colunas (remove espaços extras)
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"Falha ao converter CSV para DataFrame: {e}")
        return None


# =============================================================================
# CRIAÇÃO DAS TASKS
# =============================================================================

def create_tasks(agents: list, extratos_consolidados: str) -> list:
    """Cria as tasks encadeadas."""
    task_analise = Task(
        description=f"""Realize uma análise financeira rigorosa com base no seu objetivo (goal)
utilizando EXCLUSIVAMENTE os dados dos seguintes extratos bancários consolidados do mês:

{extratos_consolidados}

Extraia todas as transações, classifique-as conforme as regras fornecidas nas suas diretrizes
e prepare os dados em formato CSV para facilitar a posterior geração de relatórios e controles gerenciais.""",
        expected_output=(
            "Dados estruturados contendo as colunas: Data, Conta, Descrição, Valor, Tipo, "
            "Categoria e Entidade, seguidos de um breve resumo do Lucro por Entidade."
        ),
        agent=agents[0],  # CORREÇÃO: era `agents` (lista), deve ser agents[0] (Agent)
    )
    return [task_analise]


# =============================================================================
# INTERFACE STREAMLIT
# =============================================================================

def main():
    st.set_page_config(
        page_title="Open Finance | AI",
        page_icon="🏦",
        layout="wide",
    )

    st.markdown(
        '<h1 style="text-align: center;">🏦 Sistema Multi-Agente SISPRIME</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align: center;">Gestão de Operações e Dados Analíticos de Múltiplos Bancos <br> Correlação de Dados para Recebimentos/Pagamentos dos Hospitais e Pacientes <br> Apoio na gestão para eficiência operacional com controles e relatórios personalizados</p>',
        unsafe_allow_html=True,
    )

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.info("💡 Criado para uso exclusivo das empresas: ENDOPRIME e GASTROPREV.")
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
        st.header("👥 Agentes em DEV : 1/5")

        agents_info = [
            ("🔍", "Analista de Dados Multi Bancos", "Ler e categorizar os extratos"),
            ("📋", "Verificador de Correlação", "Correlação entre Planilha_Hospital e Produtividade_Procedimentos"),
            ("🧪", "Controlador de Pagamentos", "Avaliar as transferências aos Médicos Parceiros"),
            ("💻", "Controlador de Recebimentos", "Verificar se foram recebidos das consultas"),
            ("🔎", "Elaborador de Relatórios", "Montar relatórios que apoiam a tomada de decisão"),
        ]
        for icon, name, desc in agents_info:
            st.markdown(f"{icon} **{name}**")
            st.caption(desc)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["📄 Input", "🚀 Execução", "📊 Resultados", "🗂️ Consolidado"])

    # ── TAB 1: INPUT ──────────────────────────────────────────────────────────
    with tab1:
        st.header("📂 Upload de Extratos")
        col1, col2 = st.columns([2, 1])
        extratos_texto = []

        with col1:
            uploaded_files = st.file_uploader(
                "Upload de Extratos Bancários",
                type=["pdf", "docx", "txt", "csv"],
                accept_multiple_files=True,
                help="Envie múltiplos extratos",
            )

        with col2:
            if uploaded_files:
                st.subheader("Arquivos")
                for file in uploaded_files:
                    st.success(f"✅ {file.name}")
                    try:
                        file.seek(0, os.SEEK_END)
                        size = file.tell() / 1024
                        file.seek(0)
                        st.caption(f"{size:.1f} KB")
                    except Exception:
                        pass

        if uploaded_files:
            st.divider()
            with st.spinner("📖 Extraindo textos..."):
                for file in uploaded_files:
                    text = extract_text_from_file(file)
                    if text:
                        extratos_texto.append({"filename": file.name, "content": text})

            st.success(f"{len(extratos_texto)} extratos processados")
            st.session_state["extratos"] = extratos_texto

        if extratos_texto:
            st.divider()
            st.subheader("👁️ Preview")
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
        st.header("🚀 Executar Processamento")

        if not api_key:
            st.warning("⚠️ Por favor, configure a API Key na sidebar")

        extratos = st.session_state.get("extratos", [])
        if not extratos:
            st.warning("Envie os extratos na aba Input")

        if st.button("🚀 Iniciar Análise", type="primary"):
            llm = get_llm("gemini/gemini-2.5-flash", custom_model, temperature, api_key)
            agents = create_agents(llm)
            resultados = {}

            # ── Barra de progresso geral (por arquivo) ────────────────────────
            progress_bar = st.progress(0, text="Aguardando início...")

            for i, doc in enumerate(extratos):
                filename = doc["filename"]
                text = doc["content"]
                total = len(extratos)

                progress_bar.progress(
                    i / total,
                    text=f"📂 Processando arquivo {i + 1} de {total}: **{filename}**",
                )

                # ── Painel de logs em tempo real ──────────────────────────────
                with st.status(
                    f"🤖 Agente trabalhando em: {filename}", expanded=True
                ) as status_box:

                    st.markdown("##### 📡 Log de Execução em Tempo Real")
                    log_container = st.container(height=380, border=False)

                    # Fila thread-safe para receber mensagens do CrewAI
                    log_queue: queue.Queue = queue.Queue(maxsize=500)

                    # Registra o handler temporariamente no logger raiz
                    handler = StreamlitLogHandler(log_queue)
                    handler.setFormatter(
                        logging.Formatter("%(asctime)s | %(name)s | %(message)s",
                                          datefmt="%H:%M:%S")
                    )
                    root_logger = logging.getLogger()
                    root_logger.addHandler(handler)

                    # Resultado que a thread vai preencher
                    thread_result: dict = {"value": None, "error": None}

                    def _run_crew(result_holder: dict):
                        """Executa o CrewAI em thread separada."""
                        try:
                            tasks = create_tasks(agents, text)
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

                    # Inicia a thread
                    crew_thread = threading.Thread(
                        target=_run_crew,
                        args=(thread_result,),
                        daemon=True,
                    )
                    crew_thread.start()

                    # ── Loop de polling: drena a fila e atualiza a UI ─────────
                    while crew_thread.is_alive():
                        drained = False
                        while not log_queue.empty():
                            line = log_queue.get_nowait()
                            render_log_line(line, log_container)
                            drained = True
                        if not drained:
                            time.sleep(0.15)

                    # Drena qualquer mensagem que ficou após o join
                    while not log_queue.empty():
                        render_log_line(log_queue.get_nowait(), log_container)

                    crew_thread.join()

                    # Remove o handler temporário para não duplicar em próximas iterações
                    root_logger.removeHandler(handler)

                    # Verifica resultado
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

                # Atualiza barra de progresso após cada arquivo
                progress_bar.progress(
                    (i + 1) / total,
                    text=f"✅ {i + 1} de {total} arquivos concluídos",
                )

            st.session_state["results"] = resultados
            # Persiste os textos brutos para o agente consolidador usar na Tab 4
            st.session_state["csvs_brutos"] = {
                fname: extrair_csv_do_texto(txt)
                for fname, txt in resultados.items()
            }
            st.success("🎉 Todos os extratos foram processados! Veja os resultados na aba **📊 Resultados**.")

    # ── TAB 3: RESULTADOS ─────────────────────────────────────────────────────
    with tab3:
        st.header("📊 Resultados")
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


    # ── TAB 4: CONSOLIDADO ────────────────────────────────────────────────────
    with tab4:
        st.header("🗂️ Consolidado")
        st.markdown(
            "Gera um **único CSV** a partir de todos os extratos processados, "
            "utilizando um agente consolidador dedicado que padroniza colunas, "
            "remove duplicatas e calcula o lucro por entidade."
        )

        csvs_brutos = st.session_state.get("csvs_brutos", {})

        if not csvs_brutos:
            st.info("⬅️ Primeiro processe os extratos na aba **🚀 Execução**.")
        else:
            # Mostra os CSVs individuais disponíveis
            with st.expander(f"📋 CSVs individuais disponíveis ({len(csvs_brutos)} arquivo(s))", expanded=False):
                for fname, csv_txt in csvs_brutos.items():
                    st.markdown(f"**{fname}**")
                    df_prev = texto_para_dataframe(csv_txt)
                    if df_prev is not None and not df_prev.empty:
                        st.dataframe(df_prev, use_container_width=True, height=200)
                    else:
                        st.text(csv_txt[:500] + ("..." if len(csv_txt) > 500 else ""))
                    st.divider()

            if st.button("🔀 Gerar CSV Consolidado", type="primary"):

                with st.status("🤖 Agente Consolidador trabalhando...", expanded=True) as status_consolidador:
                    st.markdown("##### 📡 Log de Consolidação em Tempo Real")
                    log_container_cons = st.container(height=320, border=False)

                    log_queue_cons: queue.Queue = queue.Queue(maxsize=500)
                    handler_cons = StreamlitLogHandler(log_queue_cons)
                    handler_cons.setFormatter(
                        logging.Formatter("%(asctime)s | %(name)s | %(message)s", datefmt="%H:%M:%S")
                    )
                    root_logger = logging.getLogger()
                    root_logger.addHandler(handler_cons)

                    thread_result_cons: dict = {"value": None, "error": None}

                    def _run_consolidation(result_holder: dict):
                        """Executa o agente consolidador em thread separada."""
                        try:
                            llm_cons = get_llm(
                                "gemini/gemini-2.5-flash", custom_model, temperature, api_key
                            )
                            consolidator = create_consolidator_agent(llm_cons)
                            task_cons = create_consolidation_task(consolidator, csvs_brutos)
                            crew_cons = Crew(
                                agents=[consolidator],
                                tasks=[task_cons],
                                process=Process.sequential,
                                verbose=True,
                            )
                            result_holder["value"] = str(crew_cons.kickoff())
                        except Exception as exc:
                            result_holder["error"] = exc
                            logger.error(f"Erro na consolidação: {exc}", exc_info=True)

                    thread_cons = threading.Thread(
                        target=_run_consolidation,
                        args=(thread_result_cons,),
                        daemon=True,
                    )
                    thread_cons.start()

                    while thread_cons.is_alive():
                        drained = False
                        while not log_queue_cons.empty():
                            render_log_line(log_queue_cons.get_nowait(), log_container_cons)
                            drained = True
                        if not drained:
                            time.sleep(0.15)

                    while not log_queue_cons.empty():
                        render_log_line(log_queue_cons.get_nowait(), log_container_cons)

                    thread_cons.join()
                    root_logger.removeHandler(handler_cons)

                    if thread_result_cons["error"]:
                        status_consolidador.update(
                            label="❌ Erro na consolidação", state="error", expanded=True
                        )
                        st.error(f"Erro: {thread_result_cons['error']}")
                    else:
                        status_consolidador.update(
                            label="✅ Consolidação concluída!", state="complete", expanded=False
                        )
                        st.session_state["csv_consolidado"] = thread_result_cons["value"]

            # ── Exibe resultado consolidado ───────────────────────────────────
            csv_consolidado_raw = st.session_state.get("csv_consolidado")

            if csv_consolidado_raw:
                st.divider()

                # Separa dados do resumo
                csv_limpo = extrair_csv_do_texto(csv_consolidado_raw)
                csv_dados_str, resumo_str = separar_resumo_do_csv(csv_limpo)

                # ── DataFrame interativo ──────────────────────────────────────
                st.subheader("📊 Tabela Consolidada")
                df_final = texto_para_dataframe(csv_dados_str)

                if df_final is not None and not df_final.empty:
                    # Métricas rápidas
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    total_linhas = len(df_final)
                    n_receitas = (df_final.get("Tipo", pd.Series()).str.upper() == "RECEITA").sum()
                    n_despesas = (df_final.get("Tipo", pd.Series()).str.upper() == "DESPESA").sum()
                    n_entidades = df_final.get("Entidade", pd.Series()).nunique()

                    col_m1.metric("📄 Total de Linhas", total_linhas)
                    col_m2.metric("📈 Receitas", n_receitas)
                    col_m3.metric("📉 Despesas", n_despesas)
                    col_m4.metric("🏢 Entidades", n_entidades)

                    # Filtros interativos
                    with st.expander("🔍 Filtros", expanded=False):
                        fcol1, fcol2, fcol3 = st.columns(3)

                        entidades_disp = sorted(df_final.get("Entidade", pd.Series()).dropna().unique().tolist())
                        filtro_entidade = fcol1.multiselect(
                            "Entidade", entidades_disp, default=entidades_disp
                        )

                        tipos_disp = sorted(df_final.get("Tipo", pd.Series()).dropna().unique().tolist())
                        filtro_tipo = fcol2.multiselect(
                            "Tipo", tipos_disp, default=tipos_disp
                        )

                        categorias_disp = sorted(df_final.get("Categoria", pd.Series()).dropna().unique().tolist())
                        filtro_categoria = fcol3.multiselect(
                            "Categoria", categorias_disp, default=categorias_disp
                        )

                    # Aplica filtros
                    df_filtrado = df_final.copy()
                    if "Entidade" in df_filtrado.columns and filtro_entidade:
                        df_filtrado = df_filtrado[df_filtrado["Entidade"].isin(filtro_entidade)]
                    if "Tipo" in df_filtrado.columns and filtro_tipo:
                        df_filtrado = df_filtrado[df_filtrado["Tipo"].isin(filtro_tipo)]
                    if "Categoria" in df_filtrado.columns and filtro_categoria:
                        df_filtrado = df_filtrado[df_filtrado["Categoria"].isin(filtro_categoria)]

                    st.dataframe(df_filtrado, use_container_width=True, height=420)

                    # ── Download do CSV filtrado ──────────────────────────────
                    csv_download = df_filtrado.to_csv(index=False, sep=",", encoding="utf-8-sig")
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="⬇️ Baixar CSV Consolidado",
                        data=csv_download.encode("utf-8-sig"),
                        file_name=f"consolidado_openfinance_{ts}.csv",
                        mime="text/csv",
                        type="primary",
                    )

                else:
                    st.warning("⚠️ Não foi possível renderizar o DataFrame. Exibindo CSV bruto.")
                    st.text_area("CSV bruto", value=csv_dados_str, height=300)
                    st.download_button(
                        label="⬇️ Baixar CSV Bruto",
                        data=csv_dados_str.encode("utf-8-sig"),
                        file_name=f"consolidado_bruto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                    )

                # ── Resumo de lucro por entidade ──────────────────────────────
                if resumo_str:
                    st.divider()
                    st.subheader("💰 Resumo — Lucro por Entidade")
                    st.markdown(resumo_str)

if __name__ == "__main__":
    main()
