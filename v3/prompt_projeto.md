# 🩺 Projeto: Sistema de Controle e Validação de Procedimentos Endoscópicos (SCVPE)

## 1. Contexto
A equipe de endoscopistas do hospital realiza diversos procedimentos diariamente, que são registrados internamente por meio de códigos **TUSS** (Terminologia Unificada da Saúde Suplementar).  
Esses registros são posteriormente processados e encaminhados ao setor administrativo e aos **convênios médicos** para fins de **faturamento e recebimento**.

Atualmente, há **divergências frequentes** entre:
- Os procedimentos **efetivamente realizados** e registrados pela equipe médica;
- Os procedimentos **reconhecidos e pagos** pelos convênios médicos.

Essas inconsistências geram **perdas financeiras significativas**, retrabalho administrativo e atrasos no recebimento.

---

## 2. Problema de Negócio
Atualmente, o processo de conferência e cobrança dos procedimentos depende de:
- Planilhas **Excel** emitidas periodicamente pelo hospital com registros de faturamento e pagamentos;
- Comparações manuais e não padronizadas entre o que foi **executado** e o que foi **faturado/pago**;
- Ausência de rastreabilidade entre registros médicos e registros financeiros.

Esse cenário ocasiona:
- Falta de controle sobre divergências e glosas (não pagamentos);
- Dificuldade de comprovar serviços realizados;
- Baixa visibilidade sobre valores pendentes;
- Retrabalho em cobranças e comunicações com convênios.

---

## 3. Objetivo do Projeto
Criar uma **solução interna integrada** para:

1. **Registrar e consolidar** todos os procedimentos endoscópicos realizados (via código TUSS);
2. **Receber e interpretar** os relatórios Excel fornecidos pelo hospital (contendo informações de faturamento e pagamentos);
3. **Realizar automaticamente o batimento** entre os procedimentos executados e os registros pagos pelos convênios;
4. **Identificar divergências**, gerar relatórios e apoiar a **cobrança administrativa** de valores não recebidos;
5. Permitir **auditoria e rastreabilidade** completa entre execução médica, faturamento e recebimento.

---

## 4. Business Case
A implementação desta solução proporcionará:

| Impacto | Descrição |
|----------|------------|
| 💰 **Financeiro** | Redução de perdas por divergências e glosas — potencial recuperação de receitas não pagas. |
| 🕒 **Produtividade** | Automatização da conferência que hoje é manual e propensa a erro. |
| 📊 **Transparência** | Visão consolidada e rastreável dos procedimentos realizados, faturados e pagos. |
| 🧾 **Compliance** | Melhoria na aderência às normas de auditoria e controle de faturamento médico. |
| 🧠 **Tomada de decisão** | Relatórios de desempenho e indicadores sobre execução e recebimento por convênio. |

---

## 5. Escopo Funcional

### a) Módulo de Registro de Procedimentos
- Interface web para registro manual ou importação em lote dos procedimentos realizados;
- Campos essenciais: data, paciente, código TUSS, descrição, convênio, médico responsável, status de envio.

### b) Módulo de Importação de Arquivos Hospitalares
- Leitura automática de planilhas Excel emitidas pelo hospital (definição de layout será parte da análise inicial);
- Identificação e mapeamento de campos relevantes (ex: código TUSS, valor pago, data do pagamento, convênio, número da guia).

### c) Módulo de Batimento e Validação
- Comparação entre registros internos e registros hospitalares/pagos;
- Regras configuráveis para considerar divergências (por exemplo: diferença de código, ausência de pagamento, valores divergentes);
- Classificação dos resultados: *Conferido*, *Divergente*, *Pendente*.

### d) Relatórios e Dashboard
- Relatórios de divergências por período, convênio e profissional;
- Dashboard gerencial com estatísticas de procedimentos, valores pagos e pendentes;
- Exportação para Excel e PDF.

### e) Módulo de Cobrança e Auditoria
- Geração automática de listas de divergências a serem cobradas do hospital ou convênios;
- Registro de ações administrativas tomadas (e.g., reenvio, contestação, justificativa);
- Histórico de auditoria e logs de alteração.

---

## 6. Escopo Técnico
- **Frontend:** React, Angular ou Vue.js (conforme padrão institucional);
- **Backend:** API REST em Python (FastAPI / Django) ou Node.js;
- **Banco de Dados:** PostgreSQL ou SQL Server (suporte a integrações hospitalares);
- **Integrações:** Upload e leitura de planilhas Excel (.xlsx), API hospitalar (se disponível);
- **Autenticação:** LDAP ou OAuth2 (usuários internos do hospital);
- **Infraestrutura:** Deploy em ambiente interno (on-premise ou intranet), com Docker e CI/CD.

---

## 7. Etapas do Projeto
1. **Levantamento de Requisitos e Análise dos Arquivos Excel**  
   - Coletar exemplos de planilhas hospitalares;  
   - Definir campos obrigatórios para registro interno e mapeamento de batimento.

2. **Modelagem de Dados e Arquitetura da Solução**

3. **Desenvolvimento dos Módulos (MVP):**
   - Registro de procedimentos  
   - Importação de planilhas  
   - Batimento básico e relatório de divergências  

4. **Validação com Usuários-Chave (Endoscopistas e Financeiro)**

5. **Expansão de Funcionalidades:**
   - Dashboard, auditoria e histórico de cobrança

6. **Implantação e Treinamento da Equipe**

---

## 8. Critérios de Sucesso
- 100% dos procedimentos endoscópicos registrados no sistema interno;
- Redução mínima de 80% no tempo de conferência mensal;
- Detecção automática de divergências com acurácia >95%;
- Relatórios gerados e enviados automaticamente ao setor financeiro;
- Recuperação comprovada de valores não pagos em até 3 meses após implantação.

---

## 9. Próximos Passos
1. Reunir amostras das planilhas Excel hospitalares;  
2. Identificar campos críticos (códigos TUSS, valores, datas, convênios);  
3. Definir modelo de dados preliminar;  
4. Validar com stakeholders (médicos e equipe administrativa);  
5. Iniciar prototipagem da solução.

---

> **Observação:** O projeto SCVPE visa garantir que o trabalho médico realizado seja corretamente reconhecido e pago pelos convênios, reduzindo perdas financeiras e melhorando o controle operacional da equipe de endoscopia.
