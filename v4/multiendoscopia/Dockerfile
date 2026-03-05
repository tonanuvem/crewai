# ── Build stage: compila dependências com gcc/g++ ─────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt


# ── Runtime stage: imagem final sem compiladores ──────────────────────────────
FROM python:3.12-slim AS runtime

# Metadados
LABEL maintainer="ENDOPRIME/GASTROPREV"
LABEL description="SISPRIME Multi-Agent System"

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:$PATH" \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Usuário não-root
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copia pacotes instalados no builder para o usuário appuser
COPY --from=builder /root/.local /home/appuser/.local

# Copia o código (feito por último para aproveitar cache das camadas anteriores)
COPY app.py .

# Diretórios de runtime com dono correto
RUN mkdir -p logs outputs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

# Healthcheck usando Python puro (sem depender do curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app_streamlit.py"]
