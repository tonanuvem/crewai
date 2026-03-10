""" app-endoscopia-v7
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

# Colunas canônicas do formato PRODUCAO 2025 NOVO (MAIO+ 2025) — 12 campos
# Sem QTD, sem EXAME REALIZADO 1/2, apenas EXAME REALIZADO único
_COLUNAS_2025_NOVO = [
    "Data", "Paciente", "NrAtendimento",
    "Convenio", "Origem", "Procedimento",
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
    "procedimento adicional":                "ProcedimentosAdicionais",
    "procedimentos adicionais":              "ProcedimentosAdicionais",
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

# Mapeamento para formato 2025 NOVO (MAIO+ 2025) - sem QTD, sem EXAME REALIZADO 1/2
_MAP_PRODUCAO_2025_NOVO = {
    "data":                                  "Data",
    "nome do paciente":                      "Paciente",
    "nº atendimento":                        "NrAtendimento",
    "n° atendimento":                        "NrAtendimento",
    "n atendimento":                         "NrAtendimento",
    "nr atendimento":                        "NrAtendimento",
    "convênio":                              "Convenio",
    "convenio":                              "Convenio",
    "origem":                                "Origem",
    "exame realizado":                       "Procedimento",
    "procedimentos adicionais":              "ProcedimentosAdicionais",
    "procedimento adicional":                "ProcedimentosAdicionais",
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

# Mapeamento para formato 2026 (com QTD no início)
_MAP_PRODUCAO_2026 = {
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
    "exame realizado":                       "Procedimento",
    "procedimento":                          "Procedimento",
    "procedimentos adicionais":              "ProcedimentosAdicionais",
    "procedimento adicional":                "ProcedimentosAdicionais",
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


def _detectar_formato_producao(df: pd.DataFrame, nome_aba: str = "") -> str:
    """
    Detecta o formato da planilha baseado nas colunas e nome da aba.
    Retorna: '2025_LEGADO' (JAN-ABR 2025), '2025_NOVO' (MAI+ 2025), '2026'
    """
    colunas_norm = [_normalizar_coluna(col) for col in df.columns]
    aba_upper = nome_aba.upper()
    
    # Formato 2025 LEGADO: tem "EXAME REALIZADO 1" e "EXAME REALIZADO 2"
    if "exame realizado 1" in colunas_norm or "exame realizado 2" in colunas_norm:
        return "2025_LEGADO"
    
    # Formato 2026: tem coluna QTD no início
    if "qtd" in colunas_norm:
        return "2026"
    
    # Formato 2025 NOVO (a partir de MAIO): sem QTD, sem EXAME REALIZADO 1/2
    # Tem apenas "EXAME REALIZADO" e "PROCEDIMENTOS ADICIONAIS"
    if "exame realizado" in colunas_norm and "procedimentos adicionais" in colunas_norm:
        return "2025_NOVO"
    
    # Fallback: tenta detectar pelo nome da aba
    if "2025" in aba_upper:
        # Se é JAN-ABR 2025, provavelmente é legado
        meses_legado = ["JANEIRO", "FEVEREIRO", "MARÇO", "MARCO", "ABRIL"]
        if any(mes in aba_upper for mes in meses_legado):
            return "2025_LEGADO"
        return "2025_NOVO"
    
    return "2026"


def _padronizar_data(valor: str) -> str:
    """Converte qualquer formato de data reconhecível para DD/MM/AAAA."""
    if pd.isna(valor):
        return ""

    s = str(valor).strip()

    try:
        # Tenta formato ISO primeiro (YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS)
        if re.match(r'^\d{4}-\d{2}-\d{2}', s):
            dt = pd.to_datetime(s, format='ISO8601')
            return dt.strftime("%d/%m/%Y")
        
        # Outros formatos
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s


def _corrigir_data_malformada(data: str, aba_origem: str) -> str:
    """
    Corrige datas malformadas usando o mês da AbaOrigemDados como referência.
    Exemplos:
    - 18/032025 + ABA: MARÇO 2025 → 18/03/2025
    - 170/2025 + ABA: MAIO 2025 → 17/05/2025
    - 2706/2025 + ABA: JUNHO 2025 → 27/06/2025
    """
    if not data or not aba_origem:
        return data
    
    # Extrai mês e ano da AbaOrigemDados
    meses = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARÇO": "03", "MARCO": "03",
        "ABRIL": "04", "MAIO": "05", "JUNHO": "06",
        "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09",
        "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12"
    }
    
    mes_ref = None
    ano_ref = None
    aba_upper = aba_origem.upper()
    
    for nome_mes, num_mes in meses.items():
        if nome_mes in aba_upper:
            mes_ref = num_mes
            # Extrai ano (4 dígitos)
            match_ano = re.search(r'20\d{2}', aba_upper)
            if match_ano:
                ano_ref = match_ano.group()
            break
    
    if not mes_ref or not ano_ref:
        return data
    
    # Padrões de datas malformadas
    data_limpa = data.replace("/", "").replace("-", "").strip()
    
    # Padrão: 18032025 (sem separadores)
    if len(data_limpa) == 8 and data_limpa.isdigit():
        dia = data_limpa[:2]
        mes = data_limpa[2:4]
        ano = data_limpa[4:]
        if mes == mes_ref:  # Valida se o mês bate
            return f"{dia}/{mes}/{ano}"
    
    # Padrão: 170/2025 (dia com 3 dígitos)
    if re.match(r'^\d{3}/\d{4}$', data):
        dia = data[:2]  # Pega os 2 primeiros dígitos
        ano = data[-4:]
        return f"{dia}/{mes_ref}/{ano}"
    
    # Padrão: 2706/2025 (dia+mes sem separador)
    if re.match(r'^\d{4}/\d{4}$', data):
        dia = data[:2]
        mes = data[2:4]
        ano = data[-4:]
        if mes == mes_ref:  # Valida se o mês bate
            return f"{dia}/{mes}/{ano}"
    
    # Padrão: 17/042025 (ano sem separador)
    if re.match(r'^\d{2}/\d{6}$', data):
        dia = data[:2]
        mes = data[3:5]
        ano = data[5:]
        if mes == mes_ref:  # Valida se o mês bate
            return f"{dia}/{mes}/{ano}"
    
    return data


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


def _atribuir_colunas(df: pd.DataFrame, formato: str, nome_aba: str = "") -> pd.DataFrame:
    """
    Atribui cabeçalho canônico a DataFrames sem cabeçalho explícito.
    """
    n = len(df.columns)
    
    # Detecta qual base usar baseado no número de colunas e nome da aba
    if n == 12:
        # 12 colunas = formato 2025 NOVO (MAIO+ 2025)
        base = _COLUNAS_2025_NOVO
    elif n == 13:
        # 13 colunas: pode ser COM_QTD (2026) ou SEM_QTD (2025 LEGADO)
        # Verifica se primeira coluna parece QTD
        amostra = df.iloc[:, 0].dropna().head(5).tolist()
        primeiro_parece_qtd = all(
            re.match(r"^\d*$", str(v).strip()) for v in amostra if str(v).strip()
        )
        base = _COLUNAS_COM_QTD if primeiro_parece_qtd else _COLUNAS_SEM_QTD
    else:
        # Fallback: tenta detectar pelo nome da aba
        if "2025" in nome_aba.upper():
            meses_legado = ["JANEIRO", "FEVEREIRO", "MARÇO", "MARCO", "ABRIL"]
            if any(mes in nome_aba.upper() for mes in meses_legado):
                base = _COLUNAS_SEM_QTD
            else:
                base = _COLUNAS_2025_NOVO
        else:
            base = _COLUNAS_COM_QTD

    df.columns = (base + [f"Extra_{k}" for k in range(n - len(base))])[:n] if n <= len(base) else \
                 base + [f"Extra_{k}" for k in range(n - len(base))]
    return df


# =============================================================================
# PROCESSADORES POR TIPO
# =============================================================================

def _processar_aba_producao(df: pd.DataFrame, nome_aba: str) -> pd.DataFrame:
    """
    Normaliza um DataFrame de PRODUCAO:
    - Detecta formato (2025_LEGADO, 2025_NOVO, 2026)
    - Renomeia colunas pelo mapa apropriado
    - Garante QTD (0 se ausente), Data, Paciente, Procedimento
    - Gera linhas extras para 'Procedimento2' (EXAME REALIZADO 2 das abas 2025 LEGADO)
    - Adiciona TipoArquivo = 'PRODUCAO' e AbaOrigemDados
    - Descarta linhas sem Paciente válido
    """
    # Detecta formato baseado nas colunas e nome da aba
    formato = _detectar_formato_producao(df, nome_aba)
    
    # Seleciona mapa apropriado
    if formato == "2025_LEGADO":
        mapa = _MAP_PRODUCAO
    elif formato == "2025_NOVO":
        mapa = _MAP_PRODUCAO_2025_NOVO
    else:  # 2026
        mapa = _MAP_PRODUCAO_2026
    
    # CORREÇÃO: Remove primeira coluna se for Unnamed e formato não é 2026
    # Isso acontece quando pandas lê cabeçalho sem QTD mas dados têm coluna extra
    if formato != "2026" and len(df.columns) > 0:
        primeira_col = str(df.columns[0]).lower()
        if "unnamed" in primeira_col or primeira_col.strip() in ("", "nan"):
            df = df.iloc[:, 1:]  # Remove primeira coluna
    
    df = _renomear_colunas(df, mapa)
    
    # CORREÇÃO: Limpa valores "Unnamed: N" dos dados (problema do Excel)
    for col in df.columns:
        df[col] = df[col].apply(
            lambda v: "" if str(v).strip().upper().startswith("UNNAMED:") else v
        )

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

    # Primeiro aplica padronização básica
    df["Data"] = df["Data"].apply(_padronizar_data)
    
    # Depois corrige datas malformadas usando AbaOrigemDados
    df["Data"] = df.apply(
        lambda row: _corrigir_data_malformada(row["Data"], nome_aba),
        axis=1
    )
    
    # Tenta padronizar novamente após correção
    df["Data"] = df["Data"].apply(_padronizar_data)
    
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

        # Trata Procedimento2 (EXAME REALIZADO 2 das abas 2025 LEGADO) como linha extra
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
            df = _atribuir_colunas(df, formato, nome_aba)
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
# FUNÇÕES DE CORRELAÇÃO LOCAL
# =============================================================================

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional

# Dicionário de sinônimos e variações de procedimentos
SINONIMOS_PROCEDIMENTOS = {
    # Colonoscopia e variações
    "COLONO": ["COLONOSCOPIA", "COLONOSCOPIA INCLUI", "RETOSSIGMOIDOSCOPIA"],
    "COLONOSCOPIA": ["COLONO", "COLONOSCOPIA INCLUI", "RETOSSIGMOIDOSCOPIA"],
    "COLONOCOPIA": ["COLONO", "COLONOSCOPIA"],  # Typo comum
    "RETOSSIGMOIDOSCOPIA": ["COLONOSCOPIA", "COLONO"],
    
    # Endoscopia Digestiva Alta
    "ENDOSCOPIA": ["EDA", "ENDOSCOPIA DIGESTIVA ALTA", "ESOFAGOGASTRODUODENOSCOPIA", "ESOFAGO GASTRO DUODENOSCOPIA"],
    "EDA": ["ENDOSCOPIA", "ENDOSCOPIA DIGESTIVA ALTA", "ESOFAGOGASTRODUODENOSCOPIA"],
    "ENDOCOSPIA": ["ENDOSCOPIA"],  # Typo
    "ENDOSCOPIA": ["ENDOSCOPIA"],  # Typo
    "ENDDOSCOPIA": ["ENDOSCOPIA"],  # Typo
    "ESOFAGOGASTRODUODENOSCOPIA": ["ENDOSCOPIA", "EDA"],
    "ESOFAGO GASTRO DUODENOSCOPIA": ["ENDOSCOPIA", "EDA"],
    
    # Ecoendoscopia
    "ECOENDOSCOPIA": ["ECOEDA", "ULTRASSOM ENDOSCOPICO"],
    "ECOEDA": ["ECOENDOSCOPIA", "ULTRASSOM ENDOSCOPICO"],
    
    # Teste de Urease / H. Pylori
    "TESTE": ["PESQUISA", "EXAME"],
    "UREASE": ["H PYLORI", "HELICOBACTER", "HELICOBACTER PYLORI"],
    "TESTE DE UREASE": ["PESQUISA H PYLORI", "TESTE UREASE", "UREASE", "H PYLORI", "HELICOBACTER"],
    "TESTE DA UREASE": ["TESTE DE UREASE", "PESQUISA H PYLORI", "HELICOBACTER"],
    "HP": ["H PYLORI", "HELICOBACTER"],
    "HPYLORI": ["H PYLORI", "HELICOBACTER"],
    "HELICOBACTER": ["H PYLORI", "UREASE", "HP"],
    "HELICOBACTER PYLORI": ["H PYLORI", "UREASE", "HP"],
    
    # Anátomo Patológico / Biópsia / Citologia
    "ANATOMO": ["BIOPSIA", "CITOLOGIA", "AP"],
    "ANATOMIA": ["BIOPSIA", "CITOLOGIA", "AP"],
    "ANATOMIA PATOLOGICA": ["BIOPSIA", "CITOLOGIA", "AP", "ANÁTOMO PATOLÓGICO"],
    "ANATOMO PATOLOGICA": ["BIOPSIA", "CITOLOGIA", "AP", "ANÁTOMO PATOLÓGICO"],
    "ANATOMO PATOLOGICO": ["AP", "BIOPSIA", "CITOLOGIA", "ANÁTOMO PATOLÓGICO", "ANATOMOPATOLOGICO"],
    "ANÁTOMO PATOLÓGICO": ["AP", "BIOPSIA", "CITOLOGIA", "ANATOMO PATOLOGICO", "ANATOMOPATOLOGICO"],
    "ANÁTOMO PATLÓGICO": ["ANÁTOMO PATOLÓGICO", "BIOPSIA", "AP"],  # Typo
    "ANATOMOPATOLOGICO": ["AP", "BIOPSIA", "CITOLOGIA", "ANATOMO PATOLOGICO"],
    "ANÁTOMOPATOLOGICO": ["AP", "BIOPSIA", "CITOLOGIA", "ANÁTOMO PATOLÓGICO"],
    "AP": ["ANATOMO PATOLOGICO", "BIOPSIA", "CITOLOGIA", "ANÁTOMO PATOLÓGICO", "ANATOMOPATOLOGICO"],
    "BIOPSIA": ["ANATOMO PATOLOGICO", "AP", "CITOLOGIA", "BIOPSIAS"],
    "BIOPSIAS": ["BIOPSIA", "ANATOMO PATOLOGICO", "AP"],
    "BIOPSIA SERIADO": ["BIOPSIA", "ANÁTOMO PATOLÓGICO", "AP"],
    "CITOLOGIA": ["BIOPSIA", "ANATOMO PATOLOGICO", "AP"],
    
    # Polipectomia
    "POLIPECTOMIA": ["POLIPO", "RESSECCAO POLIPO", "RETIRADA POLIPO"],
    "POLIPO": ["POLIPECTOMIA", "RESSECCAO POLIPO"],
    "PÓLIPO": ["POLIPECTOMIA", "POLIPO"],
    "POLIOECTOMIA": ["POLIPECTOMIA"],  # Typo
    
    # Hemostasia
    "HEMOSTASIA": ["HEMOSTASE", "CONTROLE SANGRAMENTO", "HEMOSTASE ENDOSCOPICA"],
    "HEMOSTASE": ["HEMOSTASIA", "CONTROLE SANGRAMENTO"],
    
    # Mucosectomia
    "MUCOSECTOMIA": ["RESSECCAO MUCOSA", "RESSECCAO ENDOSCOPICA"],
    
    # Tatuagem
    "TATUAGEM": ["MARCACAO", "TATUAGEM ENDOSCOPICA"],
    
    # Biópsia Hepática
    "BIOPSIA HEPATICA": ["BIOPSIA", "HEPATICA"],
    "HEPATICA": ["BIOPSIA HEPATICA", "FIGADO"],
    
    # CPRE / Colangiopancreatografia / Papilotomia
    "CPRE": ["COLANGIOPANCREATOGRAFIA", "COLANGIOPANCREATOGRAFIA RETROGRADA", "PAPILOTOMIA"],
    "COLANGIOPANCREATOGRAFIA": ["CPRE", "PAPILOTOMIA", "COLANGIOPANCREATOGRAFIA RETROGRADA"],
    "COLANGIOPANCREATOGRAFIA RETROGRADA": ["CPRE", "COLANGIOPANCREATOGRAFIA", "PAPILOTOMIA"],
    "PAPILOTOMIA": ["CPRE", "COLANGIOPANCREATOGRAFIA"],
    "PAPILOTOMIA ENDOSCOPICA": ["CPRE", "PAPILOTOMIA"],
    
    # Dilatação
    "DILATACAO": ["DILATAÇÃO", "DILATACAO PNEUMATICA"],
    "DILATAÇÃO": ["DILATACAO", "DILATACAO PNEUMATICA"],
    
    # Gastrostomia
    "GASTROSTOMIA": ["GTT", "GASTROSTOMIA ENDOSCOPICA"],
    "GASTROSTOMIA ENDOSCOPICA": ["GASTROSTOMIA", "GTT"],
    "GTT": ["GASTROSTOMIA"],
    
    # Passagem de Sonda
    "SONDA": ["PASSAGEM SONDA", "SONDA NASO ENTERAL", "SONDA NASOENTERAL"],
    "PASSAGEM DE SONDA": ["SONDA", "SONDA NASO ENTERAL", "PASSAGEM SONDAS"],
    "PASSAGEM DE SONDAS": ["PASSAGEM DE SONDA", "SONDA"],
    "SONDA NASO ENTERAL": ["SONDA", "PASSAGEM SONDA"],
    
    # Anuscopia / Retoscopia
    "ANUSCOPIA": ["RETOSCOPIA", "EXAME ANORRETAL"],
    "RETOSCOPIA": ["ANUSCOPIA"],
    
    # Prótese
    "PROTESE": ["COLOCACAO PROTESE", "IMPLANTE PROTESE"],
    "PRÓTESE": ["PROTESE", "COLOCACAO PROTESE"],
    "COLOCACAO DE PROTESE": ["PROTESE", "IMPLANTE PROTESE"],
    "COLOCACAO PROTESE": ["PROTESE", "COLOCACAO DE PROTESE"],
    
    # Visita Hospitalar
    "VISITA": ["VISITA HOSPITALAR", "VISITA PACIENTE INTERNADO", "HOSPITALAR"],
    "VISITA HOSPITALAR": ["VISITA", "VISITA PACIENTE INTERNADO", "HOSPITALAR"],
    "HOSPITALAR": ["VISITA", "VISITA HOSPITALAR"],
    
    # Cromoscopia
    "CROMOSCOPIA": ["CROMOSCOPIA ENDOSCOPICA", "COLORACAO"],
    
    # Esôfago
    "ESOFAGO": ["ESOFAGICO", "ESOFAGICA"],
    "ESOFAGICO": ["ESOFAGO"],
    
    # Cálculo / Coledociano
    "CALCULO": ["CALCULOSE", "PEDRA"],
    "COLEDOCIANO": ["COLECOCO", "BILIAR"],
    
    # Drenagem
    "DRENAGEM": ["DRENAGEM BILIAR", "DESCOMPRESSAO"],
    "DESCOMPRESSAO": ["DRENAGEM"],
    "DESCOMPRESSAO COLONICA": ["DESCOMPRESSAO", "COLONICA"],
    "COLONICA": ["COLON", "COLONOSCOPIA"],
    
    # Ostomia
    "OSTOMIA": ["GASTROSTOMIA", "COLOSTOMIA"],
    "TROCA DE GTT": ["GTT", "GASTROSTOMIA"],
}

def _normalizar_procedimento(proc: str) -> str:
    """Normaliza nome de procedimento para comparação semântica."""
    if not proc or str(proc).strip() in ("", "nan", "NaN"):
        return ""
    s = str(proc).upper().strip()
    # Remove acentos
    s = s.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
    s = s.replace('Â', 'A').replace('Ê', 'E').replace('Ô', 'O')
    s = s.replace('Ã', 'A').replace('Õ', 'O')
    s = s.replace('Ç', 'C')
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove plural (S no final de palavras)
    s = re.sub(r'\bBIOPSIAS\b', 'BIOPSIA', s)
    s = re.sub(r'\bPOLIPOS\b', 'POLIPO', s)
    s = re.sub(r'\bSONDAS\b', 'SONDA', s)
    # Remove separadores comuns em procedimentos compostos
    s = re.sub(r'\s*[/+]\s*', ' ', s)  # Remove / e +
    return s

def _expandir_abreviacao(proc: str) -> str:
    """Expande abreviações comuns de procedimentos."""
    ABREVIACOES = {
        "COLONO": "COLONOSCOPIA",
        "EDA": "ENDOSCOPIA DIGESTIVA ALTA",
        "RETO": "RETOSSIGMOIDOSCOPIA",
        "RETOSSIGMOIDO": "RETOSSIGMOIDOSCOPIA",
        "POLIPECTOMIA": "POLIPECTOMIA",
        "LIGADURA": "LIGADURA ELASTICA",
        "DILATACAO": "DILATACAO ESOFAGICA",
        "ESCLEROSE": "ESCLEROTERAPIA",
        "MUCOSECTOMIA": "MUCOSECTOMIA",
        "HEMOSTASIA": "HEMOSTASIA ENDOSCOPICA",
    }
    proc_norm = _normalizar_procedimento(proc)
    
    # Verifica match exato
    if proc_norm in ABREVIACOES:
        return ABREVIACOES[proc_norm]
    
    # Verifica se começa com abreviação
    for abrev, expandido in ABREVIACOES.items():
        if proc_norm.startswith(abrev + " ") or proc_norm == abrev:
            return proc_norm.replace(abrev, expandido, 1)
    
    return proc_norm

def _match_palavra_contida(proc1: str, proc2: str) -> bool:
    """Verifica se um procedimento está contido no outro ou compartilha palavra-chave."""
    p1 = _normalizar_procedimento(proc1).strip()
    p2 = _normalizar_procedimento(proc2).strip()
    
    if not p1 or not p2:
        return False
    
    # Verifica contenção direta
    if p1 in p2 or p2 in p1:
        return True
    
    # Verifica se primeira palavra significativa é igual (mínimo 4 caracteres)
    palavras1 = [p for p in p1.split() if len(p) >= 4]
    palavras2 = [p for p in p2.split() if len(p) >= 4]
    
    if palavras1 and palavras2:
        # Verifica se primeira palavra significativa é igual
        if palavras1[0] == palavras2[0]:
            return True
        # Verifica se alguma palavra significativa está contida
        for palavra in palavras1:
            if len(palavra) >= 6 and any(palavra in p2_word or p2_word in palavra for p2_word in palavras2):
                return True
    
    return False

def _verificar_sinonimo(proc1: str, proc2: str) -> bool:
    """Verifica se dois procedimentos são sinônimos conhecidos."""
    p1_norm = _normalizar_procedimento(proc1)
    p2_norm = _normalizar_procedimento(proc2)
    
    # Verifica match direto no dicionário
    for chave, sinonimos in SINONIMOS_PROCEDIMENTOS.items():
        if chave in p1_norm:
            for sin in sinonimos:
                if sin in p2_norm:
                    return True
        if chave in p2_norm:
            for sin in sinonimos:
                if sin in p1_norm:
                    return True
    
    # Para procedimentos compostos (ex: "ANATOMO + POLIPECTOMIA")
    # Verifica se todas as palavras-chave de um estão no outro
    palavras1 = set(p1_norm.split())
    palavras2 = set(p2_norm.split())
    
    # Se tem pelo menos 2 palavras em comum e são palavras-chave
    palavras_chave = {'BIOPSIA', 'POLIPECTOMIA', 'POLIPO', 'ANATOMO', 'TESTE', 'UREASE', 
                      'MUCOSECTOMIA', 'HEMOSTASIA', 'ENDOSCOPIA', 'COLONOSCOPIA', 'COLONO'}
    comuns = palavras1 & palavras2 & palavras_chave
    if len(comuns) >= 2:
        return True
    
    return False

def _similaridade_procedimento(proc1: str, proc2: str, cache: Dict = None) -> float:
    """Calcula similaridade entre dois procedimentos (0.0 a 1.0) com cache e sinônimos."""
    if cache is not None:
        key = (proc1, proc2)
        if key in cache:
            return cache[key]
    
    # Expande abreviações antes de comparar
    p1_expandido = _expandir_abreviacao(proc1)
    p2_expandido = _expandir_abreviacao(proc2)
    
    if not p1_expandido or not p2_expandido:
        return 0.0
    
    # Match exato após expansão
    if p1_expandido == p2_expandido:
        if cache is not None:
            cache[(proc1, proc2)] = 1.0
        return 1.0
    
    # Verifica match por palavra contida
    if _match_palavra_contida(p1_expandido, p2_expandido):
        if cache is not None:
            cache[(proc1, proc2)] = 0.95
        return 0.95
    
    # Verifica sinônimos conhecidos
    if _verificar_sinonimo(proc1, proc2):
        if cache is not None:
            cache[(proc1, proc2)] = 1.0
        return 1.0
    
    # Verifica se um contém o outro (palavras-chave)
    palavras1 = set(p1_expandido.split())
    palavras2 = set(p2_expandido.split())
    intersecao = palavras1 & palavras2
    
    if intersecao:
        # Se tem palavras em comum, calcula similaridade
        ratio = len(intersecao) / max(len(palavras1), len(palavras2))
        if ratio >= 0.4:
            score = SequenceMatcher(None, p1_expandido, p2_expandido).ratio()
            if cache is not None:
                cache[(proc1, proc2)] = score
            return score
    
    # Fallback para SequenceMatcher completo
    score = SequenceMatcher(None, p1_expandido, p2_expandido).ratio()
    if cache is not None:
        cache[(proc1, proc2)] = score
    return score

def _datas_compativeis(data1: str, data2: str, tolerancia_dias: int = 1) -> bool:
    """Verifica se duas datas são compatíveis (tolerância ±N dias)."""
    if data1 == data2:
        return True
    try:
        d1 = datetime.strptime(data1, "%d/%m/%Y")
        d2 = datetime.strptime(data2, "%d/%m/%Y")
        return abs((d1 - d2).days) <= tolerancia_dias
    except:
        return False

def _extrair_valor_numerico(valor: str) -> float:
    """Extrai valor numérico de string."""
    if not valor or str(valor).strip() in ("", "nan", "NaN"):
        return 0.0
    try:
        s = str(valor).replace("R$", "").replace(",", ".").strip()
        return float(s)
    except:
        return 0.0

def _normalizar_nome_paciente(nome: str) -> str:
    """Normaliza nome de paciente removendo acentos e caracteres especiais."""
    if not nome or str(nome).strip() in ("", "nan", "NaN"):
        return ""
    s = str(nome).upper().strip()
    # Remove acentos
    s = s.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
    s = s.replace('Â', 'A').replace('Ê', 'E').replace('Ô', 'O')
    s = s.replace('Ã', 'A').replace('Õ', 'O')
    s = s.replace('Ç', 'C')
    s = s.replace('À', 'A').replace('È', 'E').replace('Ì', 'I').replace('Ò', 'O').replace('Ù', 'U')
    s = s.replace('Ü', 'U').replace('Ö', 'O').replace('Ä', 'A')
    # Remove caracteres especiais, mantém apenas letras e espaços
    s = re.sub(r'[^A-Z\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _criar_indice_repasse(df_rep: pd.DataFrame) -> Dict[Tuple[str, str], List[int]]:
    """Cria índice para busca rápida no REPASSE por (Data, Paciente)."""
    indice = {}
    for idx, row in df_rep.iterrows():
        data = row.get("Data", "")
        paciente = _normalizar_nome_paciente(row.get("Paciente", ""))
        key = (data, paciente)
        if key not in indice:
            indice[key] = []
        indice[key].append(idx)
    return indice

def _criar_indice_repasse_atendimento(df_rep: pd.DataFrame) -> Dict[Tuple[str, str], List[int]]:
    """Cria índice para busca rápida no REPASSE por (Data, NrAtendimento)."""
    indice = {}
    for idx, row in df_rep.iterrows():
        data = row.get("Data", "")
        nr_atend = str(row.get("NrAtendimento", "")).strip()
        if nr_atend and nr_atend not in ("", "nan", "NaN"):
            key = (data, nr_atend)
            if key not in indice:
                indice[key] = []
            indice[key].append(idx)
    return indice

def _determinar_status_correlacao(valor_liberado: float, tem_match: bool) -> str:
    """Determina o status de correlação baseado no valor liberado."""
    if not tem_match:
        return "NAO_FATURADO_NO_REPASSE"
    
    if valor_liberado == 0:
        return "CORRELACIONADO_COM_GLOSA_TOTAL"
    elif valor_liberado > 0:
        return "CORRELACIONADO"
    else:
        return "CORRELACIONADO"

def correlacionar_csv_arquivos(csv_producao: str, csv_repasse: str, limiar_similaridade: float = 0.65) -> str:
    """
    Correlaciona dois CSVs (PRODUCAO e REPASSE) usando chave composta otimizada.
    
    Otimizações implementadas:
    - Índice hash para busca O(1) por Data+Paciente
    - Fallback por NrAtendimento quando não encontra por nome
    - Normalização de nomes sem acentos e caracteres especiais
    - Cache de similaridade de procedimentos
    - Busca com tolerância de ±1 dia
    
    Args:
        csv_producao: CSV padronizado da PRODUCAO
        csv_repasse: CSV padronizado do REPASSE
        limiar_similaridade: Threshold para match de procedimento (0.0-1.0)
    
    Returns:
        CSV correlacionado com sufixos _PRODUCAO e _REPASSE nas colunas
    """
    try:
        # Carrega DataFrames
        df_prod = pd.read_csv(io.StringIO(csv_producao), dtype=str)
        df_rep = pd.read_csv(io.StringIO(csv_repasse), dtype=str)
        
        df_prod.fillna("", inplace=True)
        df_rep.fillna("", inplace=True)
        
        logger.info(f"Correlação: {len(df_prod)} linhas PRODUCAO, {len(df_rep)} linhas REPASSE")
        
        # Normaliza colunas essenciais
        for df in [df_prod, df_rep]:
            if "Data" in df.columns:
                df["Data"] = df["Data"].apply(_padronizar_data)
        
        # Cria índices para busca rápida no REPASSE
        indice_repasse = _criar_indice_repasse(df_rep)
        indice_atendimento = _criar_indice_repasse_atendimento(df_rep)
        logger.info(f"Índice por nome: {len(indice_repasse)} chaves | Índice por atendimento: {len(indice_atendimento)} chaves")
        
        # Marca linhas do REPASSE como não usadas
        df_rep["_matched"] = False
        
        # Cache de similaridade
        cache_similaridade = {}
        
        # Lista de resultados
        linhas_resultado = []
        matches_encontrados = 0
        matches_por_atendimento = 0
        
        # Para cada linha da PRODUCAO, busca match no REPASSE
        for idx_prod, row_prod in df_prod.iterrows():
            data_prod = row_prod.get("Data", "")
            paciente_prod = row_prod.get("Paciente", "")
            paciente_norm = _normalizar_nome_paciente(paciente_prod)
            nr_atend_prod = str(row_prod.get("NrAtendimento", "")).strip()
            proc_prod = row_prod.get("Procedimento", "")
            
            # Busca candidatos no índice (mesma data + mesmo paciente)
            candidatos = []
            metodo_busca = "NOME"
            
            # Busca exata por nome
            key_exata = (data_prod, paciente_norm)
            if key_exata in indice_repasse:
                candidatos.extend(indice_repasse[key_exata])
            
            # Busca com tolerância de ±1 dia por nome
            if not candidatos:
                try:
                    data_dt = datetime.strptime(data_prod, "%d/%m/%Y")
                    for delta in [-1, 1]:
                        data_tolerancia = (data_dt + timedelta(days=delta)).strftime("%d/%m/%Y")
                        key_tolerancia = (data_tolerancia, paciente_norm)
                        if key_tolerancia in indice_repasse:
                            candidatos.extend(indice_repasse[key_tolerancia])
                except:
                    pass
            
            # FALLBACK: Busca por NrAtendimento se não encontrou por nome
            if not candidatos and nr_atend_prod and nr_atend_prod not in ("", "nan", "NaN"):
                metodo_busca = "ATENDIMENTO"
                key_atend = (data_prod, nr_atend_prod)
                if key_atend in indice_atendimento:
                    candidatos.extend(indice_atendimento[key_atend])
                
                # Busca com tolerância de ±1 dia por atendimento
                if not candidatos:
                    try:
                        data_dt = datetime.strptime(data_prod, "%d/%m/%Y")
                        for delta in [-1, 1]:
                            data_tolerancia = (data_dt + timedelta(days=delta)).strftime("%d/%m/%Y")
                            key_tolerancia = (data_tolerancia, nr_atend_prod)
                            if key_tolerancia in indice_atendimento:
                                candidatos.extend(indice_atendimento[key_tolerancia])
                    except:
                        pass
            
            # Busca melhor match entre os candidatos
            melhor_match = None
            melhor_score = 0.0
            melhor_idx = None
            
            for idx_rep in candidatos:
                if df_rep.at[idx_rep, "_matched"]:
                    continue
                
                row_rep = df_rep.iloc[idx_rep]
                proc_rep = row_rep.get("Procedimento", "")
                
                # Calcula similaridade do procedimento (com cache)
                sim = _similaridade_procedimento(proc_prod, proc_rep, cache_similaridade)
                
                if sim >= limiar_similaridade and sim > melhor_score:
                    melhor_score = sim
                    melhor_match = row_rep
                    melhor_idx = idx_rep
            
            # Monta linha correlacionada
            linha_corr = {}
            
            # Cria chave de correlação com NrAtendimento
            proc_normalizado = _normalizar_procedimento(proc_prod)
            chave_correlacao = f"{paciente_norm}_{nr_atend_prod}_{data_prod}_{proc_normalizado}".replace(" ", "-")
            linha_corr["ChaveCorrelacao"] = chave_correlacao
            
            # Adiciona colunas da PRODUCAO com sufixo
            for col in df_prod.columns:
                if col != "TipoArquivo":
                    linha_corr[f"{col}_PRODUCAO"] = row_prod[col]
            
            # Se encontrou match, adiciona colunas do REPASSE
            if melhor_match is not None:
                df_rep.at[melhor_idx, "_matched"] = True
                matches_encontrados += 1
                if metodo_busca == "ATENDIMENTO":
                    matches_por_atendimento += 1
                
                for col in df_rep.columns:
                    if col not in ["_matched", "TipoArquivo"]:
                        if col not in df_prod.columns or col in ["Data", "Paciente", "Procedimento"]:
                            linha_corr[f"{col}_REPASSE"] = melhor_match[col]
                
                # Determina StatusCorrelacao
                valor_rep = _extrair_valor_numerico(melhor_match.get("ValorLiberado", "0"))
                status = _determinar_status_correlacao(valor_rep, True)
                linha_corr["SimilaridadeProcedimento"] = f"{melhor_score:.2f}"
            else:
                status = "NAO_FATURADO_NO_REPASSE"
                linha_corr["SimilaridadeProcedimento"] = "0.00"
            
            linha_corr["StatusCorrelacao"] = status
            linhas_resultado.append(linha_corr)
        
        logger.info(f"Matches encontrados: {matches_encontrados}/{len(df_prod)} ({matches_encontrados/len(df_prod)*100:.1f}%)")
        logger.info(f"Matches por atendimento: {matches_por_atendimento}")
        
        # Adiciona linhas do REPASSE que não foram matcheadas
        nao_matcheados = 0
        for idx_rep, row_rep in df_rep.iterrows():
            if not row_rep["_matched"]:
                nao_matcheados += 1
                linha_corr = {}
                
                # Cria chave de correlação com dados do REPASSE
                data_rep = row_rep.get("Data", "")
                paciente_rep = row_rep.get("Paciente", "")
                paciente_norm = _normalizar_nome_paciente(paciente_rep)
                nr_atend_rep = str(row_rep.get("NrAtendimento", "")).strip()
                proc_rep = row_rep.get("Procedimento", "")
                proc_normalizado = _normalizar_procedimento(proc_rep)
                chave_correlacao = f"{paciente_norm}_{nr_atend_rep}_{data_rep}_{proc_normalizado}".replace(" ", "-")
                linha_corr["ChaveCorrelacao"] = chave_correlacao
                
                # Colunas da PRODUCAO vazias
                for col in df_prod.columns:
                    if col != "TipoArquivo":
                        linha_corr[f"{col}_PRODUCAO"] = ""
                
                # Colunas do REPASSE preenchidas
                for col in df_rep.columns:
                    if col not in ["_matched", "TipoArquivo"]:
                        if col not in df_prod.columns or col in ["Data", "Paciente", "Procedimento"]:
                            linha_corr[f"{col}_REPASSE"] = row_rep[col]
                
                linha_corr["StatusCorrelacao"] = "REPASSE_NAO_IDENTIFICADO_NA_PRODUCAO"
                linha_corr["SimilaridadeProcedimento"] = "0.00"
                linhas_resultado.append(linha_corr)
        
        logger.info(f"Linhas REPASSE não matcheadas: {nao_matcheados}")
        logger.info(f"Cache de similaridade: {len(cache_similaridade)} entradas")
        
        # Cria DataFrame final
        df_final = pd.DataFrame(linhas_resultado)
        
        # Ordena por Data_PRODUCAO (ou Data_REPASSE se PRODUCAO vazia)
        if "Data_PRODUCAO" in df_final.columns:
            df_final["_sort_date"] = df_final.apply(
                lambda r: r["Data_PRODUCAO"] if r["Data_PRODUCAO"] else r.get("Data_REPASSE", ""),
                axis=1
            )
            df_final = df_final.sort_values("_sort_date")
            df_final.drop(columns=["_sort_date"], inplace=True)
        
        return df_final.to_csv(index=False, encoding="utf-8")
        
    except Exception as e:
        logger.error(f"Erro na correlação local: {e}", exc_info=True)
        return ""


# =============================================================================
# CONFIGURAÇÃO DO LLM
# =============================================================================

@st.cache_resource
def get_llm(provider: str, model_name: str, temperature: float, api_key: str, base_url: str = None) -> LLM:
    if not api_key:
        st.error("⚠️ API Key não configurada!")
        st.stop()

    model_name = model_name.strip()
    
    # Mapeamento de prefixos por provider
    provider_prefixes = {
        "Google Gemini": "google/",
        "OpenAI": "openai/",
        "Anthropic": "anthropic/",
        "Groq": "groq/",
        "Ollama": "ollama/",
        "Azure OpenAI": "azure/",
        "AWS Bedrock": "bedrock/",
        "Cohere": "cohere/",
        "HuggingFace": "huggingface/",
        "OpenRouter": "openrouter/",
        "Mistral AI": "mistral/",
        "Grok (X.AI)": "xai/",
    }
    
    prefix = provider_prefixes.get(provider, "")
    
    # Adiciona prefixo se não existir
    if prefix and not model_name.startswith(prefix):
        model_name = f"{prefix}{model_name}"
    
    try:
        llm_params = {
            "model": model_name,
            "api_key": api_key,
            "temperature": temperature
        }
        
        # Adiciona base_url se fornecido (para Ollama, Azure, etc)
        if base_url and base_url.strip():
            llm_params["base_url"] = base_url.strip()
        
        return LLM(**llm_params)
    except Exception as e:
        st.error(f"Erro ao inicializar o modelo '{model_name}': {e}")
        st.info(f"Verifique se o nome do modelo e a API Key estão corretos para {provider}")
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

        # Seleção do Provider
        provider = st.selectbox(
            "🤖 Provider LLM",
            options=[
                "Google Gemini",
                "OpenAI",
                "Anthropic",
                "Groq",
                "OpenRouter",
                "HuggingFace",
                "Mistral AI",
                "Grok (X.AI)",
                "Ollama",
                "Azure OpenAI",
                "AWS Bedrock",
                "Cohere",
            ],
            index=0,
            help="Selecione o provedor do modelo de linguagem"
        )

        # API Key
        env_key_map = {
            "Google Gemini": "GOOGLE_API_KEY",
            "OpenAI": "OPENAI_API_KEY",
            "Anthropic": "ANTHROPIC_API_KEY",
            "Groq": "GROQ_API_KEY",
            "OpenRouter": "OPENROUTER_API_KEY",
            "HuggingFace": "HUGGINGFACE_API_KEY",
            "Mistral AI": "MISTRAL_API_KEY",
            "Grok (X.AI)": "XAI_API_KEY",
            "Azure OpenAI": "AZURE_API_KEY",
            "AWS Bedrock": "AWS_ACCESS_KEY_ID",
            "Cohere": "COHERE_API_KEY",
            "Ollama": "",
        }

        env_key = env_key_map.get(provider, "")
        env_api_key = os.getenv(env_key, "") if env_key else ""
        
        api_key = st.text_input(
            f"🔑 API Key ({provider})",
            value=env_api_key,
            type="password",
            help=f"Sua chave de API para {provider}" + (f" (variável: {env_key})" if env_key else ""),
        )

        if api_key or provider == "Ollama":
            st.success(f"✅ {provider} configurado")
        else:
            st.warning(f"⚠️ API Key não preenchida — modo Local disponível")

        st.divider()

        # Modelos principais por provider (baseado em docs.crewai.com)
        provider_models = {
            "Google Gemini": [
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ],
            "OpenAI": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                "o1-preview",
                "o1-mini",
            ],
            "Anthropic": [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
            ],
            "Groq": [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ],
            "OpenRouter": [
                "anthropic/claude-3.5-sonnet",
                "openai/gpt-4o",
                "google/gemini-2.0-flash-exp",
                "meta-llama/llama-3.3-70b-instruct",
                "deepseek/deepseek-chat",
                "qwen/qwen-2.5-72b-instruct",
                "x-ai/grok-2-1212",
            ],
            "HuggingFace": [
                "meta-llama/Meta-Llama-3.1-70B-Instruct",
                "meta-llama/Meta-Llama-3.1-8B-Instruct",
                "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "microsoft/Phi-3-medium-4k-instruct",
                "Qwen/Qwen2.5-72B-Instruct",
            ],
            "Mistral AI": [
                "mistral-large-latest",
                "mistral-medium-latest",
                "mistral-small-latest",
                "open-mistral-7b",
                "open-mixtral-8x7b",
            ],
            "Grok (X.AI)": [
                "grok-2-1212",
                "grok-2-vision-1212",
                "grok-beta",
            ],
            "Ollama": [
                "llama3.2",
                "llama3.1",
                "mistral",
                "qwen2.5",
                "phi3",
                "gemma2",
            ],
            "Azure OpenAI": [
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-35-turbo",
            ],
            "AWS Bedrock": [
                "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "anthropic.claude-3-sonnet-20240229-v1:0",
                "anthropic.claude-3-haiku-20240307-v1:0",
                "meta.llama3-70b-instruct-v1:0",
                "meta.llama3-8b-instruct-v1:0",
            ],
            "Cohere": [
                "command-r-plus",
                "command-r",
                "command",
                "command-light",
            ],
        }

        # Nome do modelo - selectbox com opções do provider
        available_models = provider_models.get(provider, [])
        
        if available_models:
            custom_model = st.selectbox(
                "📝 Modelo",
                options=available_models,
                index=0,
                help=f"Selecione o modelo {provider}"
            )
        else:
            custom_model = st.text_input(
                "📝 Nome do Modelo",
                value="",
                help=f"Digite o nome do modelo {provider}"
            )

        # Base URL (para Ollama, Azure, etc)
        show_base_url = provider in ["Ollama", "Azure OpenAI"]
        base_url = ""
        if show_base_url:
            default_url = "http://localhost:11434" if provider == "Ollama" else ""
            base_url = st.text_input(
                "🌐 Base URL",
                value=default_url,
                help=f"URL base da API {provider}"
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
                    #st.text(text)
                    st.text_area("Dados RAW", value=text, height=400)
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
                f"🤖 Agente IA — {provider} (requer API Key)",
            ],
            index=0,
            horizontal=True,
            help=(
                "**Transformação Local**: usa a função `transformar_csv_arquivo` diretamente, "
                "sem consumir tokens nem precisar de API Key. Recomendado para arquivos "
                "Excel/CSV nos formatos padrão PRODUCAO e REPASSE.\n\n"
                f"**Agente IA ({provider})**: usa o agente CrewAI com o modelo configurado "
                "na sidebar. Mais flexível para arquivos fora do padrão, mas requer API Key."
            ),
        )

        usa_llm = modo_execucao.startswith("🤖")

        # Descrição contextual do modo selecionado
        if usa_llm:
            st.info(
                f"🤖 **Modo LLM ativo** — O Agente Analista de Endoscopia ({provider}) irá interpretar "
                "cada arquivo e estruturar os dados em CSV. Requer **API Key** configurada na sidebar."
            )
            if not api_key and provider != "Ollama":
                st.warning("⚠️ Preencha a **API Key** na sidebar para usar este modo.")
        else:
            st.info(
                "🔄 **Modo Local ativo** — A função `transformar_csv_arquivo` será chamada diretamente, "
                "sem uso de IA. Mais rápido e sem custo de tokens. "
                "Ideal para arquivos Excel nos formatos padrão PRODUCAO e REPASSE."
            )

        st.divider()

        btn_label = f"🚀 Iniciar Análise com {provider}" if usa_llm else "🔄 Iniciar Transformação Local"
        btn_disabled = not extratos or (usa_llm and not api_key and provider != "Ollama")

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

            # ── MODO LLM: CrewAI + LLM selecionado ───────────────────────────────
            else:
                llm = get_llm(provider, custom_model, temperature, api_key, base_url)
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
                #combined_output += f"# Resultado: {file}\n\n{result}\n\n{'-' * 36}\n\n"

                st.divider()
                st.subheader("📄 Resultado Consolidado")
                #st.text_area("Relatório completo", value=combined_output, height=400)
                st.text_area("Relatório completo", value={result}, height=400)
                c1, c2, c3 = st.columns(3)
                c1.metric("Caracteres", len(result))
                c2.metric("Palavras", len(result.split()))
                c3.metric("Linhas", len(result.splitlines()))
                
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
            # Identifica arquivos PRODUCAO e REPASSE
            csv_producao = None
            csv_repasse = None
            nome_producao = ""
            nome_repasse = ""
            
            for fname, csv_txt in csvs_brutos.items():
                # Detecta tipo pelo conteúdo
                if "TipoArquivo" in csv_txt:
                    linhas = csv_txt.split("\n")
                    if len(linhas) > 1:
                        # Verifica primeira linha de dados
                        if "PRODUCAO" in linhas[1]:
                            csv_producao = csv_txt
                            nome_producao = fname
                        elif "REPASSE" in linhas[1]:
                            csv_repasse = csv_txt
                            nome_repasse = fname
            
            # Mostra preview dos arquivos identificados
            col_prev1, col_prev2 = st.columns(2)
            with col_prev1:
                if csv_producao:
                    st.success(f"✅ PRODUCAO: {nome_producao}")
                else:
                    st.warning("⚠️ Arquivo PRODUCAO não identificado")
            with col_prev2:
                if csv_repasse:
                    st.success(f"✅ REPASSE: {nome_repasse}")
                else:
                    st.warning("⚠️ Arquivo REPASSE não identificado")
            
            if not csv_producao or not csv_repasse:
                st.error(
                    "❌ É necessário ter exatamente 1 arquivo PRODUCAO e 1 arquivo REPASSE processados. "
                    "Verifique se os arquivos foram processados corretamente na aba Execução."
                )
            else:
                # Informações dos arquivos testados
                df_prod_prev = texto_para_dataframe(csv_producao)
                df_rep_prev = texto_para_dataframe(csv_repasse)
                
                linhas_prod = len(df_prod_prev) if df_prod_prev is not None else 0
                linhas_rep = len(df_rep_prev) if df_rep_prev is not None else 0
                
                st.markdown("### 📁 Arquivos para serem correlacionados")
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.metric("**PRODUCAO:**", f"{linhas_prod} linhas")
                with col_info2:
                    st.metric("**REPASSE:**", f"{linhas_rep} linhas")
                
                with st.expander(f"📋 Preview dos CSVs ({len(csvs_brutos)} arquivo(s))", expanded=False):
                    st.markdown("**PRODUCAO:**")
                    if df_prod_prev is not None and not df_prod_prev.empty:
                        st.dataframe(df_prod_prev.head(5), use_container_width=True)
                    
                    st.markdown("**REPASSE:**")
                    if df_rep_prev is not None and not df_rep_prev.empty:
                        st.dataframe(df_rep_prev.head(5), use_container_width=True)

                st.divider()
                
                # Seleção do modo de correlação
                st.subheader("⚙️ Modo de Correlação")
                
                modo_correlacao = st.radio(
                    "Escolha como realizar a correlação:",
                    options=[
                        "🔄 Correlação Local (sem API Key)",
                        f"🤖 Correlação com Agente IA — {provider} (requer API Key)",
                    ],
                    index=0,
                    horizontal=True,
                    help=(
                        "**Correlação Local**: usa a função `correlacionar_csv_arquivos` com "
                        "correspondência semântica de procedimentos. Rápido e sem custo de tokens.\n\n"
                        f"**Agente IA ({provider})**: usa o agente Correlacionador com LLM para "
                        "interpretação mais flexível. Requer API Key."
                    ),
                )
                
                usa_llm_corr = modo_correlacao.startswith("🤖")
                
                if usa_llm_corr:
                    st.info(
                        f"🤖 **Modo LLM ativo** — O Agente Correlacionador ({provider}) irá realizar "
                        "o batimento dos dados. Requer **API Key** configurada na sidebar."
                    )
                    if not api_key and provider != "Ollama":
                        st.warning("⚠️ Preencha a **API Key** na sidebar para usar este modo.")
                else:
                    st.info(
                        "🔄 **Modo Local ativo** — A função `correlacionar_csv_arquivos` será chamada "
                        "diretamente com correspondência semântica de procedimentos. Rápido e sem custo."
                    )
                
                st.divider()
                
                btn_label_corr = f"🤖 Gerar Correlação com {provider}" if usa_llm_corr else "🔄 Gerar Correlação Local"
                btn_disabled_corr = usa_llm_corr and not api_key and provider != "Ollama"

                if st.button(btn_label_corr, type="primary", disabled=btn_disabled_corr):
                    
                    # ── MODO LOCAL: correlacionar_csv_arquivos ───────────────────
                    if not usa_llm_corr:
                        with st.status("🔄 Correlacionando localmente...", expanded=True) as status_local:
                            try:
                                csv_correlacionado = correlacionar_csv_arquivos(csv_producao, csv_repasse)
                                
                                if csv_correlacionado:
                                    st.session_state["csv_correlacionado"] = csv_correlacionado
                                    status_local.update(
                                        label="✅ Correlação local concluída!",
                                        state="complete",
                                        expanded=False
                                    )
                                else:
                                    status_local.update(
                                        label="❌ Erro na correlação local",
                                        state="error",
                                        expanded=True
                                    )
                                    st.error("Não foi possível gerar a correlação. Verifique os logs.")
                            except Exception as exc:
                                status_local.update(
                                    label="❌ Erro na correlação local",
                                    state="error",
                                    expanded=True
                                )
                                st.error(f"Erro: {exc}")
                                logger.error(f"Erro em correlacionar_csv_arquivos: {exc}", exc_info=True)
                    
                    # ── MODO LLM: Agente Correlacionador ──────────────────────────
                    else:
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
                                        provider, custom_model, temperature, api_key, base_url
                                    )
                                    correlator = create_correlator_agent(llm_corr, verbose_mode)
                                    # Passa apenas PRODUCAO e REPASSE
                                    csvs_para_correlacao = {
                                        nome_producao: csv_producao,
                                        nome_repasse: csv_repasse
                                    }
                                    task_corr = create_correlation_task(correlator, csvs_para_correlacao)
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
                    
                    # Métricas detalhadas de correlação
                    st.markdown("---")
                    st.markdown("### 📊 Resultados da Correlação")
                    
                    # Calcula métricas adicionais
                    n_repasse_nao_identificado = (status_col.str.upper() == "REPASSE_NAO_IDENTIFICADO_NA_PRODUCAO").sum()
                    
                    # Tenta identificar matches por nome vs atendimento (se houver coluna de método)
                    matches_nome = 0
                    matches_atendimento = 0
                    if "MetodoMatch" in df_final.columns:
                        matches_nome = (df_final["MetodoMatch"].str.upper() == "NOME").sum()
                        matches_atendimento = (df_final["MetodoMatch"].str.upper() == "ATENDIMENTO").sum()
                    
                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        st.markdown("**Correlações bem-sucedidas**")
                        perc_corr = (n_correlacionado / total_linhas * 100) if total_linhas > 0 else 0
                        st.info(f"**{n_correlacionado}** ({perc_corr:.1f}%)")
                        
                        if matches_nome > 0 or matches_atendimento > 0:
                            st.markdown("**Matches por nome normalizado**")
                            perc_nome = (matches_nome / n_correlacionado * 100) if n_correlacionado > 0 else 0
                            st.success(f"**{matches_nome}** ({perc_nome:.1f}%)")
                            
                            st.markdown("**Matches por NrAtendimento (fallback)**")
                            perc_atend = (matches_atendimento / n_correlacionado * 100) if n_correlacionado > 0 else 0
                            st.success(f"**{matches_atendimento}** ({perc_atend:.1f}%)")
                    
                    with col_r2:
                        st.markdown("**Não faturados no REPASSE**")
                        perc_nao_fat = (n_nao_faturado / total_linhas * 100) if total_linhas > 0 else 0
                        st.warning(f"**{n_nao_faturado}** ({perc_nao_fat:.1f}%)")
                    
                    with col_r3:
                        st.markdown("**REPASSE não identificado**")
                        perc_rep_nao_id = (n_repasse_nao_identificado / total_linhas * 100) if total_linhas > 0 else 0
                        st.error(f"**{n_repasse_nao_identificado}** ({perc_rep_nao_id:.1f}%)")
                    
                    st.markdown("---")

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
