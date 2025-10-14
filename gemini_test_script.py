"""
Script de Teste para Validar Configuração do Google Gemini

Execute este script ANTES de rodar o sistema completo para garantir
que tudo está configurado corretamente.

Como usar:
1. Configure GOOGLE_API_KEY no .env
2. Execute: python test_gemini_setup.py
"""

import os
import sys
from dotenv import load_dotenv

# Carregar .env
load_dotenv()

def test_api_key():
    """Testa se a API key está configurada"""
    print("🔑 Testando API Key...")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        print("❌ ERRO: GOOGLE_API_KEY não encontrada!")
        print("\n📝 Como resolver:")
        print("1. Crie arquivo .env na raiz do projeto")
        print("2. Adicione: GOOGLE_API_KEY=sua-chave-aqui")
        print("3. Obtenha chave em: https://makersuite.google.com/app/apikey")
        return False
    
    if len(api_key) < 20:
        print("❌ ERRO: API Key parece inválida (muito curta)")
        return False
    
    print(f"✅ API Key encontrada: {api_key[:10]}...{api_key[-5:]}")
    return True


def test_dependencies():
    """Testa se todas as dependências estão instaladas"""
    print("\n📦 Testando dependências...")
    
    required_packages = {
        "crewai": "crewai",
        "langchain_google_genai": "langchain-google-genai",
        "dotenv": "python-dotenv"
    }
    
    missing = []
    
    for module, package in required_packages.items():
        try:
            __import__(module)
            print(f"✅ {package} instalado")
        except ImportError:
            print(f"❌ {package} NÃO instalado")
            missing.append(package)
    
    if missing:
        print(f"\n📝 Instale os pacotes faltantes:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    return True


def test_gemini_connection():
    """Testa conexão com Gemini"""
    print("\n🌐 Testando conexão com Gemini...")
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            convert_system_message_to_human=True
        )
        
        # Teste simples
        response = llm.invoke("Responda apenas: OK")
        print(f"✅ Gemini respondeu: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao conectar com Gemini: {str(e)}")
        
        if "API key not valid" in str(e):
            print("\n📝 Sua API key está inválida. Verifique:")
            print("1. https://makersuite.google.com/app/apikey")
            print("2. Copie a chave corretamente")
            print("3. Não adicione espaços antes/depois")
        
        return False


def test_crewai_basic():
    """Testa funcionamento básico do CrewAI"""
    print("\n🤖 Testando CrewAI básico...")
    
    try:
        from crewai import Agent, Task, Crew, Process
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            convert_system_message_to_human=True,
            temperature=0.5
        )
        
        # Criar agente simples
        agent = Agent(
            role="Testador",
            goal="Testar se o sistema funciona",
            backstory="Você é um agente de teste.",
            llm=llm,
            verbose=False
        )
        
        # Criar task simples
        task = Task(
            description="Diga apenas: 'Sistema funcionando!'",
            agent=agent,
            expected_output="Mensagem de confirmação"
        )
        
        # Criar crew
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=0
        )
        
        # Executar
        result = crew.kickoff()
        print(f"✅ CrewAI funcionando: {str(result)[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Erro no CrewAI: {str(e)}")
        return False


def test_model_comparison():
    """Testa diferentes modelos Gemini"""
    print("\n⚡ Testando modelos Gemini...")
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        import time
        
        models = ["gemini-1.5-flash", "gemini-1.5-pro"]
        test_prompt = "Conte até 3"
        
        for model in models:
            print(f"\n  Testando {model}...")
            
            llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                convert_system_message_to_human=True
            )
            
            start = time.time()
            response = llm.invoke(test_prompt)
            duration = time.time() - start
            
            print(f"    ✅ Resposta: {response.content[:30]}...")
            print(f"    ⏱️  Tempo: {duration:.2f}s")
            
            time.sleep(1)  # Respeitar rate limit
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao testar modelos: {str(e)}")
        return False


def run_all_tests():
    """Executa todos os testes"""
    print("=" * 60)
    print("🧪 TESTE DE CONFIGURAÇÃO - GEMINI + CREWAI")
    print("=" * 60)
    
    tests = [
        ("API Key", test_api_key),
        ("Dependências", test_dependencies),
        ("Conexão Gemini", test_gemini_connection),
        ("CrewAI Básico", test_crewai_basic),
        ("Comparação de Modelos", test_model_comparison)
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
            
            if not result:
                print(f"\n⚠️  Teste '{name}' falhou. Corrija antes de continuar.")
                break
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Testes interrompidos pelo usuário")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Erro inesperado no teste '{name}': {str(e)}")
            results.append((name, False))
            break
    
    # Resumo
    print("\n" + "=" * 60)
    print("📊 RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{status} - {name}")
    
    print(f"\n📈 Resultado: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 SUCESSO! Sistema pronto para uso!")
        print("\n📝 Próximos passos:")
        print("1. Execute: python crew_development.py")
        print("2. Ou use o modo interativo")
        return True
    else:
        print("\n⚠️  Corrija os erros acima antes de continuar")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
