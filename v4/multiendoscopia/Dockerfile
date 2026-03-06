# ── Build stage: compila dependências com gcc/g++ ─────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Instala em /opt/venv (path fixo, independente de usuário)
# Evita o problema de --user instalar em /root/.local e não ser encontrado pelo appuser
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Runtime stage: imagem final sem compiladores ──────────────────────────────
FROM python:3.12-slim AS runtime

# Metadados
LABEL maintainer="ENDOPRIME/GASTROPREV"
LABEL description="SISPRIME Multi-Agent System"

# Variáveis de ambiente
# HOME=/tmp e XDG_*: CrewAI 1.10+ instancia TokenManager e TraceCollectionListener
# no momento do import, tentando criar arquivos em $HOME/.local/share/crewai.
# Redirecionamos tudo para /tmp que sempre tem permissão de escrita.
# OTEL_SDK_DISABLED + CREWAI_TELEMETRY_OPT_OUT: desativam o sistema de tracing
# que é a origem do PermissionError mesmo com os paths corrigidos.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HOME=/tmp \
    XDG_DATA_HOME=/tmp/.local/share \
    XDG_CONFIG_HOME=/tmp/.config \
    XDG_CACHE_HOME=/tmp/.cache \
    CREWAI_STORAGE_DIR=/tmp/crewai_storage \
    CREWAI_HOME=/tmp/crewai_home \
    OTEL_SDK_DISABLED=true \
    CREWAI_TELEMETRY_OPT_OUT=true \
    DO_NOT_TRACK=1

# Usuário não-root
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copia o virtualenv do builder (path fixo, acessível por qualquer usuário)
COPY --from=builder /opt/venv /opt/venv

# Copia o código
COPY app.py .

# Diretórios de runtime + diretórios /tmp que o CrewAI precisa
RUN mkdir -p logs outputs \
        /tmp/crewai_storage \
        /tmp/crewai_home \
        /tmp/.local/share/crewai \
        /tmp/.config \
        /tmp/.cache \
    && chown -R appuser:appuser /app \
    && chmod -R 777 /tmp

USER appuser

EXPOSE 8501

# Healthcheck usando Python puro (sem depender do curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py"]
