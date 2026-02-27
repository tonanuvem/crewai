# openfinance - Sistema Multi Agentes - SISPRIME

Exemplo Prático de PROJECT BASED LEARNING

Motivação:
- O objetivo estratégico é construir uma solução baseada em OPEN FINANCE que gerencie as operações e dados analíticos de todos os Bancos, visando apoiar a empresa na tomada de decisões para eficiência operacional com controles e relatórios gerencias . Ao fornecer insights detalhados sobre tendências procedimentos, pagamentos efetuados, receitas e despesas praticadas, possíveis melhorias no fluxo de caixa, dentre outros; essa solução permitirá que a empresa analise seu fluxo financeiro, reduzindo riscos e otimizando decisões ágeis.

Agentes:

1) Analista de Dados Multi Bancos
2) Verificador de Correlação
3) Controlador de Pagamentos
4) Controlador de Recebimentos
5) Elaborador de Relatórios

Tarefas:

- O Agente 1 (Analista de Dados Multi Bancos) é responsável por ler os extratos dos vários Bancos e categorizar as diversas receitas e despesas com base nas Entidades Empresariais definidas.
- O Agente 2 (Verificador de Correlação) é responsável por ler as informações necessárias e fazer a correlação entre Planilha_Hospital e Produtividade_Procedimentos.
- O Agente 3 (Controlador de Pagamento) é responsável por avaliar as transferências aos Médicos Parceiros com base na agenda de execução da Produtividade_Procedimentos.
- O Agente 3 (Controlador de Pagamento) é responsável por avaliar se os pagamentos cadastrados pela Contadora foram realizados (por exemplo: tributos, guias de INSS, pró-labores).
- O Agente 4 (Controlador de Recebimentos) é responsável por verificar se foram recebidos os valores referentes às consultas realizadas junto aos pacientes.
- O Agente 5 (Elaborador de Relatórios) é responsável por montar relatórios que apoiam a tomada de decisão e envio sistemático por e-mail aos envolvidos.


Visualizar arquivos MD:
- https://stackedit.io/app


## Domain Story Telling:

![alt text](OpenFinance_Health.svg)

## Projeto da Solução:

![alt text](SISPRIME_ARQUITETURA_MICROSERVICES.png)
