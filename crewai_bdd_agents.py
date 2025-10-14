"""
Sistema Multi-Agente para automatizar:
Domain Storytelling → User Stories → BDD → Código

Instalar:
pip install crewai crewai-tools langchain-google-genai

Configurar:
export GOOGLE_API_KEY="sua-chave-aqui"
ou criar .env com: GOOGLE_API_KEY=sua-chave-aqui

Obter chave gratuita em: https://makersuite.google.com/app/apikey
"""

from crewai import Agent, Task, Crew, Process
from crewai_tools import FileReadTool, FileWriterTool
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# =============================================================================
# CONFIGURAÇÃO DO LLM - GOOGLE GEMINI
# =============================================================================

# Verificar se a chave está configurada
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError(
        "GOOGLE_API_KEY não encontrada!\n"
        "Configure: export GOOGLE_API_KEY='sua-chave-aqui'\n"
        "Ou crie arquivo .env com: GOOGLE_API_KEY=sua-chave-aqui\n"
        "Obtenha em: https://makersuite.google.com/app/apikey"
    )

# Modelos disponíveis:
# - gemini-1.5-pro: Mais poderoso, contexto 2M tokens
# - gemini-1.5-flash: Mais rápido e barato, contexto 1M tokens
# - gemini-pro: Versão anterior, contexto 32k tokens

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",  # ou "gemini-1.5-flash" para maior velocidade
    temperature=0.7,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    convert_system_message_to_human=True  # Gemini não suporta system messages nativamente
)

# =============================================================================
# FERRAMENTAS
# =============================================================================

file_reader = FileReadTool()
file_writer = FileWriterTool()

# =============================================================================
# AGENTE 1: DOMAIN ANALYST (Analista de Domínio)
# =============================================================================

domain_analyst = Agent(
    role="Analista de Domínio Especialista",
    goal="Compreender profundamente o domínio do negócio e criar Domain Storytelling claro e detalhado",
    backstory="""Você é um especialista em Domain-Driven Design e Domain Storytelling.
    Sua missão é conversar com stakeholders, entender processos de negócio e documentá-los
    usando a técnica de Domain Storytelling, identificando:
    - Atores (pessoas, sistemas)
    - Atividades (verbos, ações)
    - Objetos de trabalho (substantivos, entidades)
    - Sequência e fluxo
    
    Você cria narrativas claras que qualquer pessoa do negócio pode entender.""",
    llm=llm,
    verbose=True,
    allow_delegation=False
)

# =============================================================================
# AGENTE 2: PRODUCT OWNER (Gestor de Produto)
# =============================================================================

product_owner = Agent(
    role="Product Owner",
    goal="Transformar Domain Storytelling em User Stories bem definidas com critérios de aceitação claros",
    backstory="""Você é um Product Owner experiente que domina técnicas ágeis.
    Sua especialidade é pegar narrativas de Domain Storytelling e transformá-las em
    User Stories seguindo o formato:
    
    Como [papel]
    Quero [ação]
    Para [benefício]
    
    Critérios de Aceitação:
    - [critério 1]
    - [critério 2]
    
    Você garante que cada story seja testável, valiosa e independente (INVEST).""",
    llm=llm,
    verbose=True,
    allow_delegation=False
)

# =============================================================================
# AGENTE 3: QA ENGINEER (Engenheiro de Qualidade)
# =============================================================================

qa_engineer = Agent(
    role="QA Engineer especialista em BDD",
    goal="Criar especificações Gherkin executáveis a partir de User Stories",
    backstory="""Você é um QA Engineer expert em Behavior-Driven Development (BDD).
    Sua missão é transformar User Stories em cenários de teste usando Gherkin:
    
    Funcionalidade: [nome]
    
    Cenário: [descrição]
      Dado [contexto inicial]
      E [mais contexto]
      Quando [ação]
      Então [resultado esperado]
      E [verificação adicional]
    
    Você cria cenários que cobrem casos de sucesso, falha e edge cases.
    Seus cenários são claros, concisos e executáveis.""",
    llm=llm,
    verbose=True,
    allow_delegation=False
)

# =============================================================================
# AGENTE 4: SENIOR DEVELOPER (Desenvolvedor Sênior)
# =============================================================================

senior_developer = Agent(
    role="Senior Software Developer",
    goal="Implementar código limpo e testável baseado nas especificações BDD",
    backstory="""Você é um desenvolvedor sênior expert em:
    - Clean Architecture
    - Domain-Driven Design
    - Test-Driven Development
    - SOLID principles
    - Design Patterns
    
    Você recebe especificações Gherkin e implementa:
    1. Entidades do domínio
    2. Use Cases
    3. Step Definitions (implementação dos steps do Gherkin)
    4. Testes automatizados
    
    Seu código é limpo, bem documentado e fácil de manter.
    Você SEMPRE implementa os testes antes ou junto com o código.""",
    llm=llm,
    verbose=True,
    allow_delegation=False
)

# =============================================================================
# AGENTE 5: CODE REVIEWER (Revisor de Código)
# =============================================================================

code_reviewer = Agent(
    role="Code Reviewer e Arquiteto de Software",
    goal="Revisar código, garantir qualidade e sugerir melhorias",
    backstory="""Você é um arquiteto de software sênior responsável por:
    - Revisar código gerado
    - Verificar aderência aos padrões
    - Identificar bugs potenciais
    - Sugerir otimizações
    - Validar cobertura de testes
    - Garantir que o código atende às especificações
    
    Você é criterioso mas construtivo nas suas revisões.""",
    llm=llm,
    verbose=True,
    allow_delegation=False
)

# =============================================================================
# TASKS (TAREFAS)
# =============================================================================

def create_domain_storytelling_task(business_description: str) -> Task:
    return Task(
        description=f"""
        Analise a seguinte descrição de negócio e crie um Domain Storytelling detalhado:
        
        {business_description}
        
        Produza:
        1. Lista de Atores identificados
        2. Fluxo sequencial numerado (Ator → [ação] → Objeto)
        3. Objetos de trabalho (entidades do domínio)
        4. Regras de negócio identificadas
        5. Glossário de termos do domínio
        
        Formato: Markdown estruturado
        """,
        agent=domain_analyst,
        expected_output="Documento de Domain Storytelling completo em Markdown"
    )


def create_user_stories_task() -> Task:
    return Task(
        description="""
        Com base no Domain Storytelling fornecido, crie User Stories seguindo:
        
        Para cada fluxo identificado:
        1. Título da Story
        2. Formato: Como/Quero/Para
        3. Critérios de Aceitação (mínimo 3)
        4. Definição de Pronto
        5. Estimativa de complexidade (P, M, G)
        
        Priorize stories por valor de negócio.
        """,
        agent=product_owner,
        expected_output="Conjunto de User Stories em formato Markdown",
        context=[create_domain_storytelling_task]  # Depende da task anterior
    )


def create_bdd_scenarios_task() -> Task:
    return Task(
        description="""
        Transforme as User Stories em cenários Gherkin executáveis.
        
        Para cada User Story:
        1. Crie pelo menos 3 cenários:
           - Cenário de sucesso (happy path)
           - Cenário de falha/validação
           - Cenário de edge case
        
        2. Use a sintaxe correta do Gherkin
        3. Steps devem ser claros e atômicos
        4. Inclua exemplos quando usar Scenario Outline
        
        Formato: Arquivo .feature válido
        """,
        agent=qa_engineer,
        expected_output="Arquivos .feature com cenários Gherkin completos",
        context=[create_user_stories_task]
    )


def create_implementation_task() -> Task:
    return Task(
        description="""
        Implemente o código completo baseado nos cenários Gherkin.
        
        Crie:
        1. Entidades do Domínio (dataclasses/classes)
        2. Use Cases (casos de uso)
        3. Step Definitions (implementação dos steps)
        4. Testes unitários
        5. Mocks/Stubs necessários
        
        Requisitos:
        - Python 3.10+
        - Type hints em todo código
        - Docstrings explicativas
        - Código limpo e SOLID
        - Cobertura de testes > 80%
        
        Organize em módulos separados:
        - domain/ (entidades)
        - use_cases/ (casos de uso)
        - tests/ (testes)
        - features/ (steps)
        """,
        agent=senior_developer,
        expected_output="Código Python completo, organizado e testado",
        context=[create_bdd_scenarios_task]
    )


def create_code_review_task() -> Task:
    return Task(
        description="""
        Revise o código implementado e produza um relatório de qualidade.
        
        Analise:
        1. Aderência às especificações Gherkin
        2. Qualidade do código (SOLID, Clean Code)
        3. Cobertura de testes
        4. Bugs potenciais
        5. Oportunidades de refatoração
        6. Documentação
        
        Produza:
        - Checklist de aprovação
        - Lista de melhorias sugeridas
        - Riscos identificados
        - Nota de qualidade (0-10)
        """,
        agent=code_reviewer,
        expected_output="Relatório de revisão de código completo",
        context=[create_implementation_task]
    )


# =============================================================================
# CREW (EQUIPE)
# =============================================================================

def create_software_development_crew(business_description: str) -> Crew:
    """
    Cria uma equipe multi-agente para desenvolvimento completo
    """
    
    # Criar tasks com a descrição do negócio
    task1 = create_domain_storytelling_task(business_description)
    task2 = create_user_stories_task()
    task3 = create_bdd_scenarios_task()
    task4 = create_implementation_task()
    task5 = create_code_review_task()
    
    # Configurar contexto entre tasks
    task2.context = [task1]
    task3.context = [task2]
    task4.context = [task3]
    task5.context = [task4]
    
    return Crew(
        agents=[
            domain_analyst,
            product_owner,
            qa_engineer,
            senior_developer,
            code_reviewer
        ],
        tasks=[task1, task2, task3, task4, task5],
        process=Process.sequential,  # Execução sequencial
        verbose=2,  # Máximo de logs
        memory=True,  # Habilita memória entre tasks
        # Embeddings para Gemini (opcional, para melhor memória)
        embedder={
            "provider": "google",
            "config": {
                "model": "models/embedding-001",
                "task_type": "retrieval_document"
            }
        }
    )


# =============================================================================
# EXEMPLO DE USO
# =============================================================================

def main():
    """
    Exemplo de execução completa
    """
    
    # Descrição do negócio (entrada do usuário)
    business_description = """
    Nossa empresa precisa de um sistema de aprovação de despesas.
    
    Processo atual:
    - Funcionário preenche formulário de despesa com valor, categoria e justificativa
    - Despesas até R$ 500 são aprovadas automaticamente
    - Despesas entre R$ 500 e R$ 5.000 precisam de aprovação do gestor
    - Despesas acima de R$ 5.000 precisam de aprovação do diretor
    - Sistema deve enviar email para aprovador
    - Funcionário deve poder anexar comprovantes
    - Histórico de aprovações deve ser mantido
    
    Regras:
    - Não pode haver despesas duplicadas (mesmo valor, data e funcionário)
    - Comprovante é obrigatório para despesas > R$ 100
    - Aprovação deve acontecer em até 48h úteis
    """
    
    print("🚀 Iniciando Sistema Multi-Agente de Desenvolvimento\n")
    print("=" * 80)
    
    # Criar a crew
    crew = create_software_development_crew(business_description)
    
    # Executar o processo completo
    result = crew.kickoff()
    
    print("\n" + "=" * 80)
    print("✅ PROCESSO COMPLETO!")
    print("=" * 80)
    print("\n📊 Resultados:\n")
    print(result)
    
    # Salvar resultados
    with open("output_desenvolvimento_completo.md", "w", encoding="utf-8") as f:
        f.write(str(result))
    
    print("\n💾 Resultados salvos em: output_desenvolvimento_completo.md")


# =============================================================================
# VERSÃO INTERATIVA (OPCIONAL)
# =============================================================================

def interactive_mode():
    """
    Modo interativo para iteração com os agentes
    """
    print("🤖 Modo Interativo - Sistema Multi-Agente\n")
    
    print("Descreva o processo de negócio que deseja automatizar:")
    business_description = input("\n> ")
    
    print("\n⚙️  Processando com 5 agentes especializados...")
    print("   1. Domain Analyst (Análise)")
    print("   2. Product Owner (User Stories)")
    print("   3. QA Engineer (BDD/Gherkin)")
    print("   4. Senior Developer (Código)")
    print("   5. Code Reviewer (Revisão)")
    
    crew = create_software_development_crew(business_description)
    result = crew.kickoff()
    
    print("\n✅ Processo concluído!")
    print("\nDeseja refinar alguma parte? (domain/stories/bdd/code/review/não)")
    refinement = input("> ").lower()
    
    if refinement != "não":
        print(f"\n🔄 Refinando {refinement}...")
        # Aqui você pode criar tasks específicas para refinamento


# =============================================================================
# EXECUÇÃO
# =============================================================================

if __name__ == "__main__":
    # Escolha um modo:
    
    # Modo 1: Execução completa automática
    main()
    
    # Modo 2: Interativo (descomente para usar)
    # interactive_mode()
