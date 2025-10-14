# =============================================================================
# .gitignore - Arquivo para Git
# =============================================================================

# Ambiente Python
venv/
env/
ENV/
.venv/
.env
*.pyc
__pycache__/
*.py[cod]
*$py.class

# Configurações sensíveis
.env
.env.local
.env.*.local
secrets.toml
.streamlit/secrets.toml

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Arquivos temporários
*.log
*.tmp
.pytest_cache/
.coverage
htmlcov/
.tox/

# Uploads e outputs (temporários)
uploads/*.pdf
uploads/*.docx
uploads/*.txt
!uploads/.gitkeep

outputs/*.md
outputs/*.txt
outputs/*.py
!outputs/.gitkeep

# Build e distribuição
build/
dist/
*.egg-info/
.eggs/

# Jupyter
.ipynb_checkpoints/
*.ipynb

# Banco de dados (se usar)
*.db
*.sqlite
*.sqlite3

# OS específicos
Thumbs.db
Desktop.ini

# Cache do Streamlit
.streamlit/cache/

# Logs de execução
logs/
*.jsonl
!logs/.gitkeep

# =============================================================================
# setup.sh - Script de Instalação Rápida (Linux/Mac)
# =============================================================================
#!/bin/bash

echo "🚀 Instalação Rápida - Sistema Multi-Agente BDD"
echo "================================================"
echo ""

# Verificar Python
echo "1️⃣ Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado!"
    echo "Instale Python 3.10+ em: https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Python $PYTHON_VERSION encontrado"
echo ""

# Criar ambiente virtual
echo "2️⃣ Criando ambiente virtual..."
if [ -d "venv" ]; then
    echo "⚠️  Ambiente virtual já existe. Removendo..."
    rm -rf venv
fi
python3 -m venv venv
echo "✅ Ambiente virtual criado"
echo ""

# Ativar ambiente
echo "3️⃣ Ativando ambiente virtual..."
source venv/bin/activate
echo "✅ Ambiente ativado"
echo ""

# Atualizar pip
echo "4️⃣ Atualizando pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ Pip atualizado"
echo ""

# Instalar dependências
echo "5️⃣ Instalando dependências..."
echo "   Isso pode levar alguns minutos..."
pip install -r requirements.txt > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Dependências instaladas"
else
    echo "❌ Erro ao instalar dependências"
    exit 1
fi
echo ""

# Criar diretórios
echo "6️⃣ Criando estrutura de diretórios..."
mkdir -p uploads outputs logs
touch uploads/.gitkeep outputs/.gitkeep logs/.gitkeep
echo "✅ Estrutura criada"
echo ""

# Verificar .env
echo "7️⃣ Verificando configuração..."
if [ ! -f ".env" ]; then
    echo "⚠️  Arquivo .env não encontrado!"
    echo "   Criando template..."
    cat > .env << EOF
# Google Gemini API Key
# Obtenha em: https://makersuite.google.com/app/apikey
GOOGLE_API_KEY=sua-chave-aqui
EOF
    echo "✅ Template .env criado"
    echo ""
    echo "🔑 IMPORTANTE: Configure sua API Key no arquivo .env"
    echo "   1. Acesse: https://makersuite.google.com/app/apikey"
    echo "   2. Copie sua chave"
    echo "   3. Cole no arquivo .env (substitua 'sua-chave-aqui')"
    echo ""
else
    echo "✅ Arquivo .env existe"
    
    # Verificar se está configurado
    if grep -q "sua-chave-aqui" .env; then
    echo "⚠️  API Key não configurada!"
    echo "   Configure no arquivo .env antes de continuar"
    exit 1
fi

echo "✅ Configuração OK"
echo ""

# Iniciar Streamlit
echo "🌐 Iniciando interface Streamlit..."
echo "   Acesse: http://localhost:8501"
echo ""
echo "   Pressione Ctrl+C para parar"
echo ""

streamlit run app_streamlit.py

# =============================================================================
# run.ps1 - Script de Execução (Windows PowerShell)
# =============================================================================
<#
🚀 Iniciando Sistema Multi-Agente BDD
Execute: .\run.ps1
#>

Write-Host "🚀 Iniciando Sistema Multi-Agente BDD" -ForegroundColor Cyan
Write-Host ""

# Ativar ambiente
if (Test-Path "venv") {
    & .\venv\Scripts\Activate.ps1
    Write-Host "✅ Ambiente virtual ativado" -ForegroundColor Green
} else {
    Write-Host "❌ Ambiente virtual não encontrado!" -ForegroundColor Red
    Write-Host "   Execute: .\setup.ps1" -ForegroundColor White
    exit 1
}

# Verificar .env
if (-not (Test-Path ".env")) {
    Write-Host "❌ Arquivo .env não encontrado!" -ForegroundColor Red
    Write-Host "   Execute: .\setup.ps1" -ForegroundColor White
    exit 1
}

$envContent = Get-Content .env -Raw
if ($envContent -match "sua-chave-aqui") {
    Write-Host "⚠️  API Key não configurada!" -ForegroundColor Yellow
    Write-Host "   Configure no arquivo .env antes de continuar" -ForegroundColor White
    exit 1
}

Write-Host "✅ Configuração OK" -ForegroundColor Green
Write-Host ""

# Iniciar Streamlit
Write-Host "🌐 Iniciando interface Streamlit..." -ForegroundColor Cyan
Write-Host "   Acesse: http://localhost:8501" -ForegroundColor White
Write-Host ""
Write-Host "   Pressione Ctrl+C para parar" -ForegroundColor Gray
Write-Host ""

streamlit run app_streamlit.py

# =============================================================================
# Makefile - Comandos úteis
# =============================================================================
.PHONY: help install test run clean deploy

help:
	@echo "🤖 Sistema Multi-Agente BDD - Comandos Disponíveis"
	@echo ""
	@echo "  make install    - Instala dependências"
	@echo "  make test       - Executa testes"
	@echo "  make run        - Inicia aplicação"
	@echo "  make clean      - Remove arquivos temporários"
	@echo "  make deploy     - Deploy no Streamlit Cloud"
	@echo ""

install:
	@echo "📦 Instalando dependências..."
	python -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo "✅ Instalação concluída!"

test:
	@echo "🧪 Executando testes..."
	. venv/bin/activate && python test_gemini_setup.py
	@echo "✅ Testes concluídos!"

run:
	@echo "🚀 Iniciando aplicação..."
	. venv/bin/activate && streamlit run app_streamlit.py

clean:
	@echo "🧹 Limpando arquivos temporários..."
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf uploads/*.pdf uploads/*.docx uploads/*.txt
	rm -rf outputs/*.md outputs/*.txt outputs/*.py
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	@echo "✅ Limpeza concluída!"

deploy:
	@echo "🚀 Preparando deploy..."
	@echo "1. Commit suas alterações: git add . && git commit -m 'Deploy'"
	@echo "2. Push para GitHub: git push origin main"
	@echo "3. Configure no Streamlit Cloud: https://streamlit.io/cloud"
	@echo "4. Adicione GOOGLE_API_KEY nos secrets"

# =============================================================================
# docker-compose.yml - Configuração Docker (Opcional)
# =============================================================================
version: '3.8'

services:
  streamlit:
    build: .
    container_name: bdd-multiagent
    ports:
      - "8501:8501"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
    volumes:
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3

# =============================================================================
# Dockerfile - Imagem Docker
# =============================================================================
FROM python:3.11-slim

# Metadados
LABEL maintainer="seu-email@exemplo.com"
LABEL description="Sistema Multi-Agente BDD com CrewAI e Gemini"
LABEL version="1.0.0"

# Diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Criar diretórios
RUN mkdir -p uploads outputs logs

# Expor porta
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Comando de execução
CMD ["streamlit", "run", "app_streamlit.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.serverAddress=0.0.0.0", \
     "--browser.gatherUsageStats=false"]

# =============================================================================
# .dockerignore - Ignorar ao criar imagem Docker
# =============================================================================
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Configurações
.env
.env.local
.streamlit/secrets.toml

# Arquivos temporários
uploads/
outputs/
logs/
*.log

# Git
.git/
.gitignore

# IDEs
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Documentação
docs/
README.md
LICENSE

# =============================================================================
# .github/workflows/ci.yml - CI/CD com GitHub Actions (Opcional)
# =============================================================================
name: CI/CD

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run tests
      env:
        GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
      run: |
        python test_gemini_setup.py
    
    - name: Lint with flake8
      run: |
        pip install flake8
        flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to Streamlit Cloud
      run: |
        echo "Deploy automático configurado no Streamlit Cloud"

# =============================================================================
# requirements.txt - Lista completa de dependências
# =============================================================================
# Core
streamlit>=1.28.0
python-dotenv>=1.0.0

# Multi-Agent System
crewai>=0.28.0
crewai-tools>=0.2.0

# LLM Integration
langchain>=0.1.0
langchain-google-genai>=1.0.0
google-generativeai>=0.3.0

# File Processing
python-docx>=1.1.0
PyPDF2>=3.0.0
pypdf>=3.17.0

# Utilities
pandas>=2.0.0
numpy>=1.24.0

# Development (opcional)
pytest>=7.4.0
pytest-cov>=4.1.0
black>=23.0.0
flake8>=6.0.0
mypy>=1.5.0

# =============================================================================
# INSTRUÇÕES FINAIS
# =============================================================================

COMO USAR OS SCRIPTS:

=== Linux/Mac ===

1. Tornar executável:
   chmod +x setup.sh run.sh

2. Instalar:
   ./setup.sh

3. Executar:
   ./run.sh

Ou usar Makefile:
   make install
   make run

=== Windows ===

1. PowerShell (como Administrador):
   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

2. Instalar:
   .\setup.ps1

3. Executar:
   .\run.ps1

=== Docker ===

1. Build:
   docker build -t bdd-multiagent .

2. Run:
   docker run -p 8501:8501 --env-file .env bdd-multiagent

Ou usar docker-compose:
   docker-compose up -d

=== Comandos Úteis ===

# Ver logs do Docker
docker logs -f bdd-multiagent

# Parar container
docker stop bdd-multiagent

# Remover tudo e recomeçar
docker-compose down -v
docker-compose up -d --build

# Acessar shell no container
docker exec -it bdd-multiagent /bin/bash

=== Verificar Instalação ===

python test_gemini_setup.py

Saída esperada:
✅ API Key encontrada
✅ Dependências OK
✅ Conexão com Gemini OK
✅ CrewAI funcionando
✅ Modelos testados

=== Solução de Problemas ===

Problema: Permissão negada (Linux/Mac)
Solução: chmod +x setup.sh run.sh

Problema: Script não executa (Windows)
Solução: Set-ExecutionPolicy RemoteSigned

Problema: Porta 8501 em uso
Solução: streamlit run app_streamlit.py --server.port 8502

Problema: API Key inválida
Solução: Verifique .env e gere nova chave

=== Estrutura Final do Projeto ===

seu-projeto/
├── .env                          # API Keys (NÃO commitar!)
├── .gitignore                    # Ignorar arquivos
├── .dockerignore                 # Ignorar no Docker
├── Dockerfile                    # Imagem Docker
├── docker-compose.yml            # Orquestração Docker
├── Makefile                      # Comandos úteis
├── requirements.txt              # Dependências Python
├── README.md                     # Documentação
├── LICENSE                       # Licença MIT
│
├── setup.sh                      # Setup Linux/Mac
├── setup.ps1                     # Setup Windows
├── run.sh                        # Run Linux/Mac
├── run.ps1                       # Run Windows
│
├── app_streamlit.py              # ← Interface principal
├── crew_development.py           # Sistema multi-agente
├── test_gemini_setup.py          # Testes de configuração
│
├── uploads/                      # Arquivos temporários
│   └── .gitkeep
├── outputs/                      # Resultados gerados
│   └── .gitkeep
├── logs/                         # Logs de execução
│   └── .gitkeep
│
├── .github/                      # CI/CD (opcional)
│   └── workflows/
│       └── ci.yml
│
└── docs/                         # Documentação extra
    ├── images/
    ├── examples/
    └── tutorials/

=== Comandos Rápidos ===

# Instalação One-Line (Linux/Mac)
curl -sSL https://raw.githubusercontent.com/seu-usuario/bdd-multiagent/main/setup.sh | bash

# Instalação One-Line (Windows)
iwr https://raw.githubusercontent.com/seu-usuario/bdd-multiagent/main/setup.ps1 | iex

# Verificar saúde da aplicação
curl http://localhost:8501/_stcore/health

# Ver métricas
curl http://localhost:8501/_stcore/metrics

=== Deploy Produção ===

# Streamlit Cloud (Gratuito)
1. Push para GitHub
2. Conecte em streamlit.io/cloud
3. Configure secrets
4. Deploy automático!

# Heroku
heroku create seu-app
git push heroku main
heroku config:set GOOGLE_API_KEY=sua-chave

# AWS EC2
- Use Dockerfile
- Configure security groups
- Use nginx como reverse proxy

# Google Cloud Run
gcloud run deploy bdd-multiagent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated

=== Monitoramento ===

# Logs em tempo real (Linux/Mac)
tail -f logs/*.jsonl

# Logs em tempo real (Windows)
Get-Content logs\*.jsonl -Wait

# Análise de performance
python -m cProfile -o profile.stats app_streamlit.py

---

✅ SETUP COMPLETO!

Agora você tem:
- Scripts de instalação automática
- Docker support
- CI/CD configurado
- Comandos úteis (Makefile)
- Deploy preparado

Para começar: ./setup.sh && ./run.sh
chave-aqui" .env; then
        echo "⚠️  API Key ainda não configurada!"
        echo "   Configure no arquivo .env"
    else
        echo "✅ API Key configurada"
    fi
fi
echo ""

# Executar testes
echo "8️⃣ Executando testes de configuração..."
if python3 test_gemini_setup.py; then
    echo "✅ Todos os testes passaram!"
else
    echo "⚠️  Alguns testes falharam"
    echo "   Verifique a configuração da API Key"
fi
echo ""

# Resumo
echo "================================================"
echo "✅ Instalação concluída!"
echo ""
echo "📝 Próximos passos:"
echo "   1. Configure GOOGLE_API_KEY no arquivo .env"
echo "   2. Execute: streamlit run app_streamlit.py"
echo "   3. Acesse: http://localhost:8501"
echo ""
echo "🆘 Precisa de ajuda?"
echo "   - Documentação: README.md"
echo "   - Issues: https://github.com/seu-usuario/bdd-multiagent/issues"
echo "================================================"

# =============================================================================
# setup.ps1 - Script de Instalação Rápida (Windows PowerShell)
# =============================================================================
<# 
🚀 Instalação Rápida - Sistema Multi-Agente BDD
Execute: .\setup.ps1
#>

Write-Host "🚀 Instalação Rápida - Sistema Multi-Agente BDD" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Verificar Python
Write-Host "1️⃣ Verificando Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python não encontrado!" -ForegroundColor Red
    Write-Host "Instale Python 3.10+ em: https://python.org" -ForegroundColor Red
    exit 1
}
Write-Host "✅ $pythonVersion encontrado" -ForegroundColor Green
Write-Host ""

# Criar ambiente virtual
Write-Host "2️⃣ Criando ambiente virtual..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "⚠️  Ambiente virtual já existe. Removendo..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force venv
}
python -m venv venv
Write-Host "✅ Ambiente virtual criado" -ForegroundColor Green
Write-Host ""

# Ativar ambiente
Write-Host "3️⃣ Ativando ambiente virtual..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
Write-Host "✅ Ambiente ativado" -ForegroundColor Green
Write-Host ""

# Atualizar pip
Write-Host "4️⃣ Atualizando pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip | Out-Null
Write-Host "✅ Pip atualizado" -ForegroundColor Green
Write-Host ""

# Instalar dependências
Write-Host "5️⃣ Instalando dependências..." -ForegroundColor Yellow
Write-Host "   Isso pode levar alguns minutos..." -ForegroundColor Gray
pip install -r requirements.txt | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Dependências instaladas" -ForegroundColor Green
} else {
    Write-Host "❌ Erro ao instalar dependências" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Criar diretórios
Write-Host "6️⃣ Criando estrutura de diretórios..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path uploads, outputs, logs | Out-Null
New-Item -ItemType File -Force -Path uploads\.gitkeep, outputs\.gitkeep, logs\.gitkeep | Out-Null
Write-Host "✅ Estrutura criada" -ForegroundColor Green
Write-Host ""

# Verificar .env
Write-Host "7️⃣ Verificando configuração..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  Arquivo .env não encontrado!" -ForegroundColor Yellow
    Write-Host "   Criando template..." -ForegroundColor Gray
    
    @"
# Google Gemini API Key
# Obtenha em: https://makersuite.google.com/app/apikey
GOOGLE_API_KEY=sua-chave-aqui
"@ | Out-File -Encoding UTF8 .env
    
    Write-Host "✅ Template .env criado" -ForegroundColor Green
    Write-Host ""
    Write-Host "🔑 IMPORTANTE: Configure sua API Key no arquivo .env" -ForegroundColor Cyan
    Write-Host "   1. Acesse: https://makersuite.google.com/app/apikey" -ForegroundColor White
    Write-Host "   2. Copie sua chave" -ForegroundColor White
    Write-Host "   3. Cole no arquivo .env (substitua 'sua-chave-aqui')" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "✅ Arquivo .env existe" -ForegroundColor Green
    
    # Verificar se está configurado
    $envContent = Get-Content .env -Raw
    if ($envContent -match "sua-chave-aqui") {
        Write-Host "⚠️  API Key ainda não configurada!" -ForegroundColor Yellow
        Write-Host "   Configure no arquivo .env" -ForegroundColor White
    } else {
        Write-Host "✅ API Key configurada" -ForegroundColor Green
    }
}
Write-Host ""

# Executar testes
Write-Host "8️⃣ Executando testes de configuração..." -ForegroundColor Yellow
python test_gemini_setup.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Todos os testes passaram!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Alguns testes falharam" -ForegroundColor Yellow
    Write-Host "   Verifique a configuração da API Key" -ForegroundColor White
}
Write-Host ""

# Resumo
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ Instalação concluída!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Próximos passos:" -ForegroundColor Cyan
Write-Host "   1. Configure GOOGLE_API_KEY no arquivo .env" -ForegroundColor White
Write-Host "   2. Execute: streamlit run app_streamlit.py" -ForegroundColor White
Write-Host "   3. Acesse: http://localhost:8501" -ForegroundColor White
Write-Host ""
Write-Host "🆘 Precisa de ajuda?" -ForegroundColor Cyan
Write-Host "   - Documentação: README.md" -ForegroundColor White
Write-Host "   - Issues: https://github.com/seu-usuario/bdd-multiagent/issues" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan

# =============================================================================
# run.sh - Script de Execução (Linux/Mac)
# =============================================================================
#!/bin/bash

echo "🚀 Iniciando Sistema Multi-Agente BDD"
echo ""

# Ativar ambiente
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Ambiente virtual ativado"
else
    echo "❌ Ambiente virtual não encontrado!"
    echo "   Execute: ./setup.sh"
    exit 1
fi

# Verificar .env
if [ ! -f ".env" ]; then
    echo "❌ Arquivo .env não encontrado!"
    echo "   Execute: ./setup.sh"
    exit 1
fi

if grep -q "sua-