""" app-endoscopia-v6
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
- Coluna TipoArquivo = "PRODUCAO" ou "REPASSE".

Desmembramento de Procedimentos Adicionais: 
- Se houver preenchimento na coluna "PROCEDIMENTOS ADICIONAIS" (ex: TESTE DE UREASE), você deve gerar uma LINHA EXTRA no CSV para cada procedimento listado.
- Na linha extra, o nome do procedimento adicional deve entrar na coluna Procedimento. As demais informações (Data, Atendimento, Paciente, Convênio, etc.) devem ser replicadas da linha principal.
- Para essas linhas extras, inclua obrigatoriamente a tag PROCEDIMENTO_ADICIONAL na coluna Observacao. A linha do procedimento principal deve ter a Observacao vazia.
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
            # FIX: remove quebras de linha internas em células Excel (Alt+Enter)
            df = df.apply(lambda col: col.map(
                lambda v: re.sub(r"[\r\n]+", " ", str(v)).strip() if isinstance(v, str) else v
            ))
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
# FUNÇÕES DE TRANSFORMAÇÃO DE ARQUIVOS
# =============================================================================

# =============================================================================
# CONSTANTES
# =============================================================================

# Padrão da linha de título informativo (descartada)
_RE_LINHA_INFORMATIVA = re.compile(
    r"CONTROLE DE EXAMES E PROCEDIMENTOS NA ENDOSCOPIA",
    re.IGNORECASE,
)

# Colunas canônicas do formato PRODUCAO com QTD (2026) — 13 campos
_COLUNAS_COM_QTD = [
    "QTD", "Data", "Paciente", "NrAtendimento",
    "Convenio", "Origem", "Procedimento",
    "ProcedimentosAdicionais", "MedicoExecutor",
    "LocalSetor", "Sala", "Carater", "Observacao",
]

# Colunas canônicas do formato PRODUCAO sem QTD (legado 2025) — 13 campos
# O primeiro campo é Data (sem QTD), e há EXAME REALIZADO 1 + EXAME REALIZADO 2
_COLUNAS_SEM_QTD = [
    "Data", "Paciente", "NrAtendimento",
    "Convenio", "Origem", "Procedimento", "Procedimento2",
    "ProcedimentosAdicionais", "MedicoExecutor",
    "LocalSetor", "Sala", "Carater", "Observacao",
]

# =============================================================================
# MAPEAMENTOS DE COLUNAS → NOMES PADRONIZADOS
# =============================================================================

_MAP_PRODUCAO = {
    "qtd":                                   "QTD",
    "data":                                  "Data",
    "nome do paciente":                      "Paciente",
    "nº atendimento":                        "NrAtendimento",
    "n° atendimento":                        "NrAtendimento",
    "n atendimento":                         "NrAtendimento",
    "nr atendimento":                        "NrAtendimento",
    "convênio":                              "Convenio",
    "convenio":                              "Convenio",
    "origem":                                "Origem",
    "exame realizado":                       "Procedimento",      # com ou sem espaço trailing
    "exame realizado 1":                     "Procedimento",
    "exame realizado 2":                     "Procedimento2",
    "procedimentos adicionais":              "ProcedimentosAdicionais",
    "procedimento adicional":                "ProcedimentosAdicionais",
    "procedimento adocional":                "ProcedimentosAdicionais",  # typo real do arquivo
    "médico executor":                       "MedicoExecutor",
    "medico executor":                       "MedicoExecutor",
    "local / setor":                         "LocalSetor",
    "local/setor":                           "LocalSetor",
    "sala":                                  "Sala",
    "carater":                               "Carater",
    "caráter":                               "Carater",
    "observação + procedimentos adicionais": "Observacao",
    "observacao":                            "Observacao",
    "observação":                            "Observacao",
}

_MAP_REPASSE = {
    "ds estabelecimento":  "Estabelecimento",
    "ds terceiro":         "Terceiro",
    "nr repasse terceiro": "NrRepasse",
    "nr atendimento":      "NrAtendimento",
    "paciente":            "Paciente",
    "convenio":            "Convenio",
    "convênio":            "Convenio",
    "ds categoria":        "Categoria",
    "cód item tuss":       "CodigoTUSS",
    "cod item tuss":       "CodigoTUSS",
    "ds procedimento":     "Procedimento",
    "nm medico executor":  "MedicoExecutor",
    "porcentagem":         "Porcentagem",
    "ds funcao":           "Funcao",
    "ds especialidade":    "Especialidade",
    "qt procedimento":     "QtProcedimento",
    "dt procedimento":     "Data",
    "vl liberado":         "ValorLiberado",
}

# =============================================================================
# FUNÇÕES AUXILIARES PRIVADAS
# =============================================================================

def _normalizar_coluna(col: str) -> str:
    return re.sub(r"\s+", " ", col.strip()).lower()


def _renomear_colunas(df: pd.DataFrame, mapa: dict) -> pd.DataFrame:
    novo = {
        col: mapa[_normalizar_coluna(col)]
        for col in df.columns
        if _normalizar_coluna(col) in mapa
    }
    return df.rename(columns=novo)


def _padronizar_data(valor: str) -> str:
    """Converte qualquer formato de data reconhecível para DD/MM/AAAA."""
    s = str(valor).strip() if valor else ""
    if s in ("", "nan", "NaT", "NaN"):
        return ""
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%d/%m/%Y")
    except Exception:
        return s


def _padronizar_valor(valor: str) -> str:
    """Remove R$, espaços e normaliza separadores decimais."""
    s = str(valor).strip() if valor else ""
    if not s:
        return ""
    s = re.sub(r"[R$\s]", "", s)
    if re.search(r"\d\.\d{3},", s):      # 1.234,56 → 1234.56
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")           # 664,61 → 664.61
    return re.sub(r"[,.]$", "", s)


def _identificar_tipo_arquivo(nome_aba: str, nome_arquivo: str = "") -> str:
    """
    Retorna 'REPASSE' ou 'PRODUCAO'.
    Prioridade: nome_aba → nome_arquivo → fallback PRODUCAO.
    """
    if "REPASSE" in nome_aba.upper():
        return "REPASSE"
    if "REPASSE" in nome_arquivo.upper():
        return "REPASSE"
    return "PRODUCAO"


def _detectar_tipo_por_cabecalho(linhas: list[str]) -> str:
    """
    Detecta o tipo (PRODUCAO ou REPASSE) inspecionando as primeiras linhas.
    Usa colunas exclusivas do REPASSE como indicadores.
    """
    _COLS_REPASSE = {
        "ds estabelecimento", "ds terceiro", "nr repasse terceiro",
        "ds procedimento", "nm medico executor", "dt procedimento",
        "vl liberado", "cód item tuss", "ds categoria",
    }
    for linha in linhas[:3]:
        cols = {c.strip().lower() for c in linha.split(",")}
        if cols & _COLS_REPASSE:
            return "REPASSE"
    return "PRODUCAO"


def _linha_e_valida(linha: str) -> bool:
    """
    Descarta:
    - linhas em branco ou só vírgulas/espaços
    - linhas com apenas 1 valor não vazio (ex: "429,,,,,,,,,,,")
    - linha de título informativo ("CONTROLE DE EXAMES...")
    - linha com colunas todas 'Unnamed: N'
    """
    s = linha.strip()
    if not s or re.match(r"^[,\s]*$", s):
        return False
    nao_vazios = [p.strip() for p in s.split(",") if p.strip()]
    if len(nao_vazios) <= 1:
        return False
    if _RE_LINHA_INFORMATIVA.search(s):
        return False
    if all(re.match(r"^unnamed\s*:\s*\d+$", v, re.I) for v in nao_vazios):
        return False
    return True


def _detectar_cabecalho_producao(linhas: list[str]) -> tuple[str, int]:
    """
    Inspeciona as primeiras linhas válidas e retorna:
      ("COM_QTD", idx)   — cabeçalho explícito com a coluna QTD
      ("SEM_QTD", idx)   — cabeçalho explícito sem QTD (formato 2025)
      ("SEM_HEADER", 0)  — sem cabeçalho; dados começam na linha 0

    idx = índice em `linhas` onde está o cabeçalho (ou 0 se não houver).
    """
    for idx, linha in enumerate(linhas[:5]):
        upper = linha.upper()
        campos = [c.strip() for c in linha.split(",")]

        # Cabeçalho 2026 com QTD
        if "QTD" in campos[0].upper() and "DATA" in upper:
            return "COM_QTD", idx

        # Cabeçalho 2025 sem QTD — começa com DATA
        if campos[0].strip().upper() in ("DATA",) and "NOME DO PACIENTE" in upper:
            return "SEM_QTD", idx

    return "SEM_HEADER", 0


def _atribuir_colunas(df: pd.DataFrame, formato: str) -> pd.DataFrame:
    """
    Atribui cabeçalho canônico a DataFrames sem cabeçalho explícito.
    """
    n = len(df.columns)
    if formato == "COM_QTD":
        base = _COLUNAS_COM_QTD
    else:  # SEM_QTD ou SEM_HEADER (tratado como COM_QTD pois 1ª col é número)
        # Heurística: se 1ª coluna tem valores numéricos ou vazia → COM_QTD
        amostra = df.iloc[:, 0].dropna().head(5).tolist()
        primeiro_parece_qtd = all(
            re.match(r"^\d*$", str(v).strip()) for v in amostra if str(v).strip()
        )
        base = _COLUNAS_COM_QTD if primeiro_parece_qtd else _COLUNAS_SEM_QTD

    df.columns = (base + [f"Extra_{k}" for k in range(n - len(base))])[:n] if n <= len(base) else \
                 base + [f"Extra_{k}" for k in range(n - len(base))]
    return df


# =============================================================================
# PROCESSADORES POR TIPO
# =============================================================================

def _processar_aba_producao(df: pd.DataFrame, nome_aba: str) -> pd.DataFrame:
    """
    Normaliza um DataFrame de PRODUCAO:
    - Renomeia colunas pelo mapa
    - Garante QTD (0 se ausente), Data, Paciente, Procedimento
    - Gera linhas extras para 'Procedimento2' (EXAME REALIZADO 2 das abas 2025)
    - Adiciona TipoArquivo = 'PRODUCAO' e AbaOrigemDados
    - Descarta linhas sem Paciente válido
    """
    df = _renomear_colunas(df, _MAP_PRODUCAO)

    for col in ("QTD", "Data", "Paciente", "Procedimento", "Procedimento2",
                "Convenio", "Origem", "NrAtendimento", "MedicoExecutor",
                "LocalSetor", "Sala", "Carater", "Observacao",
                "ProcedimentosAdicionais"):
        if col not in df.columns:
            df[col] = ""

    # Normaliza QTD
    df["QTD"] = df["QTD"].apply(
        lambda v: "0" if str(v).strip() in ("", "nan", "NaN") else str(v).strip()
    )

    df["Data"]         = df["Data"].apply(_padronizar_data)
    df["Paciente"]     = df["Paciente"].apply(
        lambda v: re.sub(r"\s+", " ", str(v).strip()).upper()
    )
    df["Procedimento"] = df["Procedimento"].apply(
        lambda v: str(v).strip().upper() if str(v).strip() not in ("", "-", "nan") else ""
    )

    linhas_saida = []
    for _, row in df.iterrows():
        paciente = str(row.get("Paciente", "")).strip()
        # Descarta linhas de formatação sem paciente real
        if not paciente or paciente in ("NAN", ""):
            continue

        linha_principal = row.copy()
        linha_principal["TipoArquivo"]    = "PRODUCAO"
        linha_principal["AbaOrigemDados"] = f"ABA: {nome_aba}"
        linhas_saida.append(linha_principal)

        # Trata Procedimento2 (EXAME REALIZADO 2 das abas 2025) como linha extra
        proc2 = str(row.get("Procedimento2", "")).strip().upper()
        if proc2 and proc2 not in ("", "-", "NAN", "NONE"):
            extra = row.copy()
            extra["Procedimento"]    = proc2
            extra["Procedimento2"]   = ""
            extra["Observacao"]      = "PROCEDIMENTO_ADICIONAL"
            extra["TipoArquivo"]     = "PRODUCAO"
            extra["AbaOrigemDados"]  = f"ABA: {nome_aba}"
            extra["QTD"]             = "0"
            linhas_saida.append(extra)

    df_saida = pd.DataFrame(linhas_saida)
    df_saida.drop(columns=["Procedimento2"], inplace=True, errors="ignore")
    # Remove colunas lixo: Extra_N e duplicatas pandas (sufixo .1, .2, ...)
    lixo = [c for c in df_saida.columns
            if re.match(r"^Extra_\d+$", str(c)) or re.search(r"\.\d+$", str(c))]
    df_saida.drop(columns=lixo, inplace=True, errors="ignore")
    return df_saida


def _processar_aba_repasse(df: pd.DataFrame, nome_aba: str) -> pd.DataFrame:
    """
    Normaliza um DataFrame de REPASSE:
    - Renomeia colunas pelo mapa
    - Padroniza Data, Paciente e ValorLiberado
    - Adiciona TipoArquivo = 'REPASSE' e AbaOrigemDados
    """
    df = _renomear_colunas(df, _MAP_REPASSE)

    for col in ("Data", "Paciente", "Procedimento", "Convenio",
                "NrAtendimento", "MedicoExecutor", "ValorLiberado",
                "CodigoTUSS", "QtProcedimento"):
        if col not in df.columns:
            df[col] = ""

    df["Data"]          = df["Data"].apply(_padronizar_data)
    df["Paciente"]      = df["Paciente"].apply(
        lambda v: re.sub(r"\s+", " ", str(v).strip()).upper()
    )
    df["ValorLiberado"] = df["ValorLiberado"].apply(_padronizar_valor)
    df["TipoArquivo"]   = "REPASSE"
    df["AbaOrigemDados"] = f"ABA: {nome_aba}"
    # Remove lixo de colunas extras
    lixo = [c for c in df.columns if re.match(r"^Extra_\d+$", str(c))]
    df.drop(columns=lixo, inplace=True, errors="ignore")
    return df


# =============================================================================
# PROCESSAMENTO DE UM BLOCO TEXTO (UMA ABA)
# =============================================================================

def _processar_bloco_texto(
    dados_aba: str,
    nome_aba: str,
    nome_arquivo: str,
) -> str:
    """Filtra, detecta formato e processa o texto de uma única aba."""

    # FIX defensivo: colapsa \n internos em campos entre aspas (origem: CSV/TXT)
    dados_aba = re.sub(
        r'"([^"]*)"',
        lambda m: '"' + m.group(1).replace('\n', ' ').replace('\r', '') + '"',
        dados_aba,
    )
    # ── 1. Filtrar linhas inválidas ──────────────────────────────────────────
    linhas_validas = [l for l in dados_aba.splitlines() if _linha_e_valida(l)]
    if not linhas_validas:
        return ""

    tipo = _identificar_tipo_arquivo(nome_aba, nome_arquivo)
    if tipo == "PRODUCAO":
        tipo = _detectar_tipo_por_cabecalho(linhas_validas)

    # ── 2. REPASSE — cabeçalho sempre explícito ──────────────────────────────
    if tipo == "REPASSE":
        try:
            df = pd.read_csv(io.StringIO("\n".join(linhas_validas)), dtype=str)
            df.fillna("", inplace=True)
            df_proc = _processar_aba_repasse(df, nome_aba)
            return df_proc.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Erro REPASSE '{nome_aba}': {exc}")
            return ""

    # ── 3. PRODUCAO — detecta formato ────────────────────────────────────────
    formato, idx_hdr = _detectar_cabecalho_producao(linhas_validas)

    if formato in ("COM_QTD", "SEM_QTD"):
        # Cabeçalho explícito na linha idx_hdr; descarta linhas anteriores
        linhas_csv = linhas_validas[idx_hdr:]
        try:
            df = pd.read_csv(io.StringIO("\n".join(linhas_csv)), dtype=str)
            df.fillna("", inplace=True)
        except Exception as exc:
            logger.warning(f"Erro PRODUCAO com header '{nome_aba}': {exc}")
            return ""
    else:
        # SEM_HEADER: nenhum cabeçalho encontrado → aplica cabeçalho canônico
        try:
            df = pd.read_csv(
                io.StringIO("\n".join(linhas_validas)),
                header=None, dtype=str,
            )
            df.fillna("", inplace=True)
            df = _atribuir_colunas(df, formato)
        except Exception as exc:
            logger.warning(f"Erro PRODUCAO sem header '{nome_aba}': {exc}")
            return ""

    df_proc = _processar_aba_producao(df, nome_aba)
    return df_proc.to_csv(index=False, encoding="utf-8")


def _consolidar_blocos(blocos_csv: list[str]) -> str:
    """Une múltiplos CSVs em um único, com cabeçalho único na primeira linha."""
    dfs = []
    for bloco in blocos_csv:
        bloco = bloco.strip()
        if not bloco:
            continue
        try:
            df = pd.read_csv(io.StringIO(bloco), dtype=str)
            df.fillna("", inplace=True)
            dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return ""
    df_final = pd.concat(dfs, ignore_index=True, sort=False)
    df_final.fillna("", inplace=True)
    return df_final.to_csv(index=False, encoding="utf-8")


# =============================================================================
# FUNÇÃO PÚBLICA PRINCIPAL
# =============================================================================

def transformar_csv_arquivo(
    conteudo_texto: str,
    nome_arquivo: str = "",
    desmembrar_procedimentos_adicionais: bool = False,
) -> str:
    """
    Transforma o conteúdo extraído de um arquivo de endoscopia (PRODUCAO ou REPASSE)
    em um CSV padronizado puro, sem linhas vazias ou texto explicativo.

    Regras aplicadas:
    - Remove linhas completamente vazias, com só vírgulas (ex: "429,,,,,,,,,,,,")
      ou com apenas um valor não vazio
    - Remove linhas informativas de título ("CONTROLE DE EXAMES E PROCEDIMENTOS
      NA ENDOSCOPIA / MÊS ANO,Unnamed: 1,Unnamed: 2,...")
    - Extrai o nome da aba do marcador "=== ABA: <nome> ===" e insere na coluna
      AbaOrigemDados (ex: "ABA: JANEIRO 2026")
    - Primeira linha do CSV = cabeçalho obrigatório
    - Data padronizada para DD/MM/AAAA
    - Paciente em MAIÚSCULAS sem espaços extras
    - TipoArquivo = 'PRODUCAO' ou 'REPASSE' (identificado pelo nome da aba/arquivo)
    - Coluna QTD incluída; preenchida com "0" quando ausente na aba de origem
    - Abas com formato legado 2025 (EXAME REALIZADO 1 / EXAME REALIZADO 2) têm
      "EXAME REALIZADO 2" tratado como linha extra de procedimento

    Args:
        conteudo_texto:   Texto extraído por extract_text_from_file.
                          Para Excel: contém blocos "=== ABA: <nome> ===" separando abas.
        nome_arquivo:     Nome original do arquivo (fallback para identificar tipo).
        desmembrar_procedimentos_adicionais:
                          Se True E TipoArquivo for PRODUCAO, chama
                          desmembrar_procedimentos_adicionais_csv_arquivo antes de retornar.

    Returns:
        CSV puro (str) com cabeçalho na primeira linha, ou "" em caso de falha total.
    """
    blocos_csv: list[str] = []

    # Divide por marcadores de aba (formato gerado por read_excel_file)
    partes = re.split(r"(===\s*ABA:\s*.+?===)", conteudo_texto)

    if len(partes) > 1:
        it = iter(partes[1:])
        for marcador, dados_aba in zip(it, it):
            nome_aba = re.sub(r"===\s*ABA:\s*|===", "", marcador).strip()
            dados_aba = dados_aba.strip()
            if not dados_aba:
                continue
            try:
                bloco = _processar_bloco_texto(dados_aba, nome_aba, nome_arquivo)
                if bloco:
                    blocos_csv.append(bloco)
            except Exception as exc:
                logger.warning(f"Falha ao processar aba '{nome_aba}': {exc}")
    else:
        # Arquivo CSV/TXT simples sem marcador de aba
        nome_aba = re.sub(r"\.[^.]+$", "", nome_arquivo)
        try:
            bloco = _processar_bloco_texto(conteudo_texto.strip(), nome_aba, nome_arquivo)
            if bloco:
                blocos_csv.append(bloco)
        except Exception as exc:
            logger.error(f"Falha ao processar '{nome_arquivo}': {exc}")
            return ""

    if not blocos_csv:
        return ""

    resultado = _consolidar_blocos(blocos_csv)

    # Desmembramento opcional (só PRODUCAO)
    if desmembrar_procedimentos_adicionais and _identificar_tipo_arquivo(nome_arquivo) == "PRODUCAO":
        resultado = desmembrar_procedimentos_adicionais_csv_arquivo(resultado)

    return resultado


# =============================================================================
# FUNÇÃO PÚBLICA: DESMEMBRAMENTO DE PROCEDIMENTOS ADICIONAIS
# =============================================================================

def desmembrar_procedimentos_adicionais_csv_arquivo(csv_texto: str) -> str:
    """
    Recebe um CSV de PRODUCAO já padronizado e desmembra a coluna
    'ProcedimentosAdicionais' em linhas extras.

    Regras:
    - Para cada valor em 'ProcedimentosAdicionais', gera uma LINHA EXTRA com:
        * Procedimento  = nome do procedimento adicional (MAIÚSCULAS)
        * Observacao    = "PROCEDIMENTO_ADICIONAL"
        * QTD           = "0"
        * demais campos = replicados da linha principal
    - A linha principal mantém sua Observacao original (vazia ou com valor já existente).
    - Não altera linhas de REPASSE (TipoArquivo != 'PRODUCAO').
    - Remove a coluna 'ProcedimentosAdicionais' do CSV final.
    - Delimitadores suportados: ponto-e-vírgula, '+', quebra de linha.
      Vírgulas são delimitadoras apenas quando não fazem parte de número decimal.

    Args:
        csv_texto: CSV puro (string) com cabeçalho na primeira linha.

    Returns:
        CSV puro (string) com as linhas extras já inseridas e sem
        a coluna 'ProcedimentosAdicionais'.
    """
    if not csv_texto or not csv_texto.strip():
        return csv_texto

    try:
        df = pd.read_csv(io.StringIO(csv_texto.strip()), dtype=str)
        df.fillna("", inplace=True)
    except Exception as exc:
        logger.warning(f"desmembrar_procedimentos_adicionais_csv_arquivo: erro ao ler CSV: {exc}")
        return csv_texto

    if "ProcedimentosAdicionais" not in df.columns:
        return csv_texto

    linhas_saida = []
    for _, row in df.iterrows():
        linhas_saida.append(row.copy())

        # Só desmembra linhas de PRODUCAO
        if str(row.get("TipoArquivo", "")).strip().upper() != "PRODUCAO":
            continue

        proc_adicionais = str(row.get("ProcedimentosAdicionais", "")).strip()
        if proc_adicionais.upper() in ("", "NAN", "NONE", "NAN", "-"):
            continue

        # Delimitadores: ; | + | quebra de linha
        # Vírgula apenas quando não separa dígitos (evita quebrar "1,234")
        separados = re.split(r"[;+\n\r]+|(?<!\d),(?!\d)", proc_adicionais)

        for proc in separados:
            proc = proc.strip().upper()
            if not proc or proc in ("-", ""):
                continue
            extra = row.copy()
            extra["Procedimento"]            = proc
            extra["ProcedimentosAdicionais"] = ""
            extra["Observacao"]              = "PROCEDIMENTO_ADICIONAL"
            extra["QTD"]                     = "0"
            linhas_saida.append(extra)

    df_saida = pd.DataFrame(linhas_saida)
    df_saida.drop(columns=["ProcedimentosAdicionais"], inplace=True, errors="ignore")
    df_saida.fillna("", inplace=True)
    return df_saida.to_csv(index=False, encoding="utf-8")

###############################################################################


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
            "🔑 API Key",
            value=env_api_key,
            type="password",
            help="Sua chave da API do Google Gemini",
        )

        if api_key:
            st.success("✅ API Key configurada")
        else:
            st.warning("⚠️ API Key não preenchida — modo Local disponível")

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
                    #st.text(text[:2000])
                    st.text(text)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Caracteres", len(text))
                    c2.metric("Palavras", len(text.split()))
                    c3.metric("Linhas", len(text.splitlines()))
                    
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    nome_sem_ext = os.path.splitext(doc["filename"])[0]
                    st.download_button(
                        label="⬇️ Baixar CSV RAW",
                        data=text.encode("utf-8-sig"),
                        file_name=f"raw_{nome_sem_ext}_{ts}.csv",
                        mime="text/csv",
                        type="primary",
                    )

    # ── TAB 2: EXECUÇÃO ───────────────────────────────────────────────────────
    with tab2:
        st.header("🚀 Executar Análise dos Arquivos")

        extratos = st.session_state.get("extratos", [])
        if not extratos:
            st.warning("Envie os arquivos na aba Input antes de executar.")

        # ── Seleção do modo de execução ───────────────────────────────────────
        st.subheader("⚙️ Modo de Processamento")

        modo_execucao = st.radio(
            "Escolha como os arquivos serão processados:",
            options=[
                "🔄 Transformação Local (sem API Key)",
                "🤖 Agente IA — LLM Gemini (requer API Key)",
            ],
            index=0,
            horizontal=True,
            help=(
                "**Transformação Local**: usa a função `transformar_csv_arquivo` diretamente, "
                "sem consumir tokens nem precisar de API Key. Recomendado para arquivos "
                "Excel/CSV nos formatos padrão PRODUCAO e REPASSE.\n\n"
                "**Agente IA (LLM)**: usa o agente CrewAI com o modelo Gemini configurado "
                "na sidebar. Mais flexível para arquivos fora do padrão, mas requer API Key."
            ),
        )

        usa_llm = modo_execucao.startswith("🤖")

        # Descrição contextual do modo selecionado
        if usa_llm:
            st.info(
                "🤖 **Modo LLM ativo** — O Agente Analista de Endoscopia (Gemini) irá interpretar "
                "cada arquivo e estruturar os dados em CSV. Requer **API Key** configurada na sidebar."
            )
            if not api_key:
                st.warning("⚠️ Preencha a **API Key** na sidebar para usar este modo.")
        else:
            st.info(
                "🔄 **Modo Local ativo** — A função `transformar_csv_arquivo` será chamada diretamente, "
                "sem uso de IA. Mais rápido e sem custo de tokens. "
                "Ideal para arquivos Excel nos formatos padrão PRODUCAO e REPASSE."
            )

        st.divider()

        btn_label = "🚀 Iniciar Análise com LLM" if usa_llm else "🔄 Iniciar Transformação Local"
        btn_disabled = not extratos or (usa_llm and not api_key)

        if st.button(btn_label, type="primary", disabled=btn_disabled):

            resultados = {}
            progress_bar = st.progress(0, text="Aguardando início...")

            # ── MODO LOCAL: transformar_csv_arquivo ───────────────────────────
            if not usa_llm:
                for i, doc in enumerate(extratos):
                    filename = doc["filename"]
                    text = doc["content"]
                    total = len(extratos)

                    progress_bar.progress(
                        i / total,
                        text=f"📂 Processando arquivo {i + 1} de {total}: **{filename}**",
                    )

                    with st.status(f"🔄 Transformando: {filename}", expanded=True) as status_box:
                        try:
                            csv_resultado = transformar_csv_arquivo(text, filename)
                            if csv_resultado:
                                resultados[filename] = csv_resultado
                                status_box.update(
                                    label=f"✅ Concluído: {filename}",
                                    state="complete",
                                    expanded=False,
                                )
                            else:
                                status_box.update(
                                    label=f"⚠️ Sem dados: {filename}",
                                    state="error",
                                    expanded=True,
                                )
                                st.warning(
                                    f"Nenhum dado extraído de **{filename}**. "
                                    "Verifique se o arquivo está no formato padrão PRODUCAO ou REPASSE."
                                )
                        except Exception as exc:
                            status_box.update(
                                label=f"❌ Erro em {filename}", state="error", expanded=True
                            )
                            st.error(f"Erro ao transformar **{filename}**: {exc}")
                            logger.error(
                                f"Erro em transformar_csv_arquivo({filename}): {exc}", exc_info=True
                            )

                    progress_bar.progress(
                        (i + 1) / total,
                        text=f"✅ {i + 1} de {total} arquivos concluídos",
                    )

                st.session_state["results"] = resultados
                # No modo local o CSV já vem puro — não precisa de extração adicional
                st.session_state["csvs_brutos"] = dict(resultados)
                st.success(
                    "🎉 Transformação concluída! Veja os resultados na aba **📊 Resultados** "
                    "ou inicie a correlação na aba **🔀 Correlação**."
                )

            # ── MODO LLM: CrewAI + Gemini ─────────────────────────────────────
            else:
                llm = get_llm("gemini-2.5-flash-lite", custom_model, temperature, api_key)
                agents = create_agents(llm, verbose_mode)

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
                st.success(
                    "🎉 Análise concluída! Veja os resultados na aba **📊 Resultados** "
                    "ou inicie a correlação na aba **🔀 Correlação**."
                )

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
                #st.markdown(result)
                combined_output += f"# Resultado: {file}\n\n{result}\n\n{'-' * 36}\n\n"

            st.divider()
            st.subheader("📄 Resultado Consolidado")
            st.text_area("Relatório completo", value=combined_output, height=400)
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_sem_ext = os.path.splitext(file)[0]
            st.download_button(
                label="⬇️ Baixar CSV Processado",
                data=result.encode("utf-8-sig"),
                file_name=f"processado_{nome_sem_ext}_{ts}.csv",
                mime="text/csv",
                type="primary",
            )

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
