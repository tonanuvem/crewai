# 🚀 Guia Completo: CrewAI com Google Gemini

## 📋 Pré-requisitos

### 1. Obter API Key do Google (GRATUITA!)

1. Acesse: https://makersuite.google.com/app/apikey
2. Faça login com sua conta Google
3. Clique em "Create API Key"
4. Copie a chave gerada

**Limites Gratuitos (Generoso!):**
- Gemini 1.5 Pro: 2 requisições/minuto, 1.500/dia
- Gemini 1.5 Flash: 15 requisições/minuto, 1.500/dia
- 100% gratuito para desenvolvimento

### 2. Instalar Dependências

```bash
# Criar ambiente virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar pacotes
pip install crewai crewai-tools langchain-google-genai python-dotenv
```

### 3. Configurar API Key

**Opção A: Variável de Ambiente**
```bash
# Linux/Mac
export GOOGLE_API_KEY="sua-chave-aqui"

# Windows (CMD)
set GOOGLE_API_KEY=sua-chave-aqui

# Windows (PowerShell)
$env:GOOGLE_API_KEY="sua-chave-aqui"
```

**Opção B: Arquivo .env (RECOMENDADO)**
```bash
# Criar arquivo .env na raiz do projeto
echo "GOOGLE_API_KEY=sua-chave-aqui" > .env
```

## 🎯 Comparação de Modelos Gemini

| Modelo | Contexto | Velocidade | Custo | Uso Recomendado |
|--------|----------|------------|-------|-----------------|
| **gemini-1.5-pro** | 2M tokens | Médio | Grátis | Análises complexas, código grande |
| **gemini-1.5-flash** | 1M tokens | Rápido | Grátis | Desenvolvimento ágil, iterações |
| **gemini-pro** | 32k tokens | Médio | Grátis | Projetos menores |

**Recomendação:**
- Use `gemini-1.5-flash` para desenvolvimento (mais rápido)
- Use `gemini-1.5-pro` para código complexo ou quando precisar de mais contexto

## 🔧 Configurações Otimizadas

### Para Máxima Velocidade:
```python
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.5,  # Menos criativo, mais focado
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True,
    max_output_tokens=8192  # Limitar output para ser mais rápido
)
```

### Para Máxima Qualidade:
```python
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0.7,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True,
    top_p=0.95,  # Controle adicional
    top_k=40
)
```

### Para Código Determinístico:
```python
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.1,  # Quase determinístico
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True
)
```

## 📊 Exemplo de Uso Completo

```python
# 1. Criar arquivo .env
"""
GOOGLE_API_KEY=AIzaSy...sua-chave...
"""

# 2. Executar o script
from crew_development import main

if __name__ == "__main__":
    main()
```

## ⚡ Otimizações de Performance

### 1. Cache de Respostas
```python
from langchain.cache import InMemoryCache
from langchain.globals import set_llm_cache

set_llm_cache(InMemoryCache())
```

### 2. Execução Paralela (para agents independentes)
```python
crew = Crew(
    agents=[...],
    tasks=[...],
    process=Process.parallel,  # Em vez de sequential
    max_rpm=10  # Requests por minuto
)
```

### 3. Streaming (ver progresso em tempo real)
```python
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    streaming=True,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True
)
```

## 🐛 Troubleshooting

### Erro: "API key not valid"
```bash
# Verificar se a chave está correta
echo $GOOGLE_API_KEY  # Linux/Mac
echo %GOOGLE_API_KEY%  # Windows

# Gerar nova chave em: https://makersuite.google.com/app/apikey
```

### Erro: "Resource exhausted"
```python
# Você atingiu o rate limit. Soluções:

# 1. Adicionar delay entre requests
import time
time.sleep(1)  # 1 segundo entre requests

# 2. Usar gemini-1.5-flash (limite maior)
# 3. Aguardar reset do limite (60 segundos)
```

### Erro: "convert_system_message_to_human required"
```python
# Gemini não suporta system messages nativamente
# SEMPRE adicione este parâmetro:
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    convert_system_message_to_human=True  # ESSENCIAL!
)
```

## 💡 Dicas Avançadas

### 1. Usar Modelos Diferentes por Agente
```python
# Agents simples = Flash (rápido)
llm_fast = ChatGoogleGenerativeAI(model="gemini-1.5-flash", ...)

# Agents complexos = Pro (poderoso)
llm_powerful = ChatGoogleGenerativeAI(model="gemini-1.5-pro", ...)

domain_analyst = Agent(
    role="...",
    llm=llm_powerful  # Usa Pro para análise
)

code_reviewer = Agent(
    role="...",
    llm=llm_fast  # Usa Flash para revisão rápida
)
```

### 2. Callback para Monitorar Custos
```python
from langchain.callbacks import get_openai_callback

# Mesmo sendo Gemini, funciona para tracking
with get_openai_callback() as cb:
    result = crew.kickoff()
    print(f"Tokens usados: {cb.total_tokens}")
```

### 3. Fallback entre Modelos
```python
from langchain.chat_models import init_chat_model

llm = init_chat_model(
    "gemini-1.5-pro",
    model_provider="google_genai",
    configurable_fields=["model"],
)

# Se Pro falhar, usar Flash automaticamente
```

## 📈 Estimativas de Performance

### Projeto Pequeno (1 feature simples):
- Modelo: gemini-1.5-flash
- Tempo: 2-5 minutos
- Tokens: ~50k
- Custo: Grátis

### Projeto Médio (5-10 features):
- Modelo: gemini-1.5-pro
- Tempo: 10-20 minutos
- Tokens: ~200k
- Custo: Grátis

### Projeto Grande (20+ features):
- Modelo: mix (Flash + Pro)
- Tempo: 30-60 minutos
- Tokens: ~500k
- Custo: Grátis (dentro dos limites)

## 🔐 Segurança

```python
# NUNCA commite o .env
# Adicione ao .gitignore:
echo ".env" >> .gitignore

# Use variáveis de ambiente em produção
import os
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    raise ValueError("GOOGLE_API_KEY não configurada!")
```

## 🎓 Recursos Adicionais

- **Documentação Gemini**: https://ai.google.dev/docs
- **CrewAI Docs**: https://docs.crewai.com
- **LangChain + Gemini**: https://python.langchain.com/docs/integrations/chat/google_generative_ai

## ✅ Checklist Final

- [ ] API Key do Google criada
- [ ] Dependências instaladas (`pip install ...`)
- [ ] Arquivo .env configurado
- [ ] Testado com script simples
- [ ] Modelo escolhido (Flash vs Pro)
- [ ] Rate limits entendidos
- [ ] .gitignore configurado

---

**🚀 Pronto para começar!** Execute o script e veja a mágica acontecer.