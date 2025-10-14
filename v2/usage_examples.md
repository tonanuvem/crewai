# 📖 Guia Prático: Exemplos de Uso Real

## 🎯 Cenários Completos do Início ao Fim

---

## Exemplo 1: Sistema de Agendamento de Consultas

### 📄 Input (Descrição do Negócio)

```markdown
Sistema de Agendamento Online - Clínica Médica

CONTEXTO:
Clínica com 15 médicos de diversas especialidades precisa automatizar agendamentos.

ATORES:
- Paciente (novo e retorno)
- Médico
- Recepcionista
- Sistema

PROCESSO ATUAL (Manual):
1. Paciente liga para clínica
2. Recepcionista verifica agenda do médico em planilha Excel
3. Marca horário disponível
4. Anota em caderno
5. Liga para confirmar 1 dia antes

PROCESSO DESEJADO (Automatizado):
1. Paciente acessa site/app
2. Escolhe especialidade médica
3. Sistema mostra médicos disponíveis com foto e currículo
4. Paciente escolhe médico
5. Sistema exibe calendário com horários livres
6. Paciente seleciona data/hora
7. Preenche dados (se novo) ou faz login (se retorno)
8. Confirma agendamento
9. Recebe confirmação por email e SMS
10. Médico recebe notificação
11. Sistema envia lembretes automáticos

REGRAS DE NEGÓCIO:
- Consultas com antecedência mínima de 2 horas
- Máximo 3 consultas agendadas por paciente
- Duração padrão: 30 minutos
- Intervalo almoço: 12h-13h (bloqueado)
- Horário funcionamento: 8h-18h
- Apenas dias úteis

CANCELAMENTO:
- Até 4h antes: sem cobrança
- Menos de 4h: multa de 50% do valor
- Não comparecimento: multa de 100%

REMARCAÇÃO:
- Permitida até 2h antes
- Máximo 2 remarcações por consulta
- Horário anterior é liberado automaticamente

NOTIFICAÇÕES:
- Email confirmação imediata
- SMS 24h antes
- SMS 2h antes
- Push notification no app

INTEGRAÇÕES:
- Sistema de prontuário eletrônico
- Gateway de pagamento (pré-pagamento opcional)
- Google Calendar (médico)
- WhatsApp Business API

DADOS DO PACIENTE:
- Nome completo
- CPF
- Data nascimento
- Telefone/Email
- Endereço
- Convênio (se houver)
- Histórico de consultas

VALIDAÇÕES:
- CPF válido
- Email válido
- Telefone válido (DDD + 9 dígitos)
- Paciente maior de 18 anos ou responsável
- Convênio ativo (se informado)

EXCEÇÕES:
- Primeira consulta: obrigatório chegar 15min antes
- Retorno: até 30 dias após última consulta (desconto 20%)
- Urgências: encaminhar para pronto-socorro
```

### 📊 Output Esperado

**1. Domain Storytelling**
```
FLUXO: Agendamento de Consulta

1. Paciente → acessa → Portal de Agendamento
2. Sistema → exibe → Lista de Especialidades
3. Paciente → seleciona → Especialidade (ex: Cardiologia)
4. Sistema → busca → Médicos Disponíveis
5. Sistema → mostra → Perfis dos Médicos
6. Paciente → escolhe → Médico
7. Sistema → consulta → Agenda do Médico
8. Sistema → exibe → Horários Livres
9. Paciente → seleciona → Data/Hora
10. Sistema → verifica → Regras de Negócio
11. Paciente → preenche/confirma → Dados Pessoais
12. Sistema → valida → CPF, Email, Telefone
13. Sistema → cria → Agendamento
14. Sistema → envia → Email de Confirmação
15. Sistema → envia → SMS de Confirmação
16. Sistema → notifica → Médico
17. Sistema → agenda → Lembretes Automáticos

ENTIDADES IDENTIFICADAS:
- Paciente
- Médico
- Especialidade
- Agendamento
- Horário
- Notificação
- Prontuário
```

**2. User Stories**

```markdown
## Epic: Agendamento de Consultas

### US-001: Buscar Médicos por Especialidade
**Como** paciente  
**Quero** ver todos os médicos de uma especialidade  
**Para** escolher o profissional adequado  

**Critérios de Aceitação:**
- Listar todas as especialidades disponíveis
- Exibir foto, nome e CRM do médico
- Mostrar próximos horários disponíveis
- Filtrar por convênio aceito
- Ordenar por avaliação ou primeiro disponível

**Definição de Pronto:**
- Testes unitários > 80%
- Cenários BDD implementados
- Performance < 1s para listar

---

### US-002: Agendar Consulta
**Como** paciente  
**Quero** agendar uma consulta online  
**Para** evitar ligações telefônicas  

**Critérios de Aceitação:**
- Validar antecedência mínima (2h)
- Verificar máximo de 3 agendamentos
- Bloquear horários indisponíveis
- Confirmar dados do paciente
- Enviar confirmação por email/SMS

---

### US-003: Cancelar Consulta
**Como** paciente  
**Quero** cancelar minha consulta  
**Para** liberar o horário se não puder comparecer  

**Critérios de Aceitação:**
- Permitir cancelamento até 4h antes
- Aplicar multa se < 4h
- Liberar horário automaticamente
- Notificar médico do cancelamento
- Atualizar histórico do paciente

---

### US-004: Receber Lembretes
**Como** paciente  
**Quero** receber lembretes da consulta  
**Para** não esquecer  

**Critérios de Aceitação:**
- SMS 24h antes
- SMS 2h antes
- Push no app 1h antes
- Email com localização e instruções
```

**3. Cenários Gherkin**

```gherkin
Funcionalidade: Agendamento de Consultas

  Contexto:
    Dado que existe um médico "Dr. João Silva" da especialidade "Cardiologia"
    E o médico tem horários disponíveis hoje às "14:00"
    E o sistema está funcionando normalmente

  Cenário: Agendar consulta com sucesso
    Dado que sou um paciente cadastrado com CPF "123.456.789-00"
    E tenho menos de 3 consultas agendadas
    Quando acesso o sistema de agendamento
    E seleciono a especialidade "Cardiologia"
    E escolho o médico "Dr. João Silva"
    E seleciono o horário "14:00" para hoje
    E confirmo meus dados pessoais
    Então a consulta deve ser agendada com sucesso
    E devo receber um email de confirmação
    E devo receber um SMS de confirmação
    E o médico deve ser notificado
    E o horário deve ficar bloqueado para outros pacientes

  Cenário: Tentar agendar sem antecedência mínima
    Dado que sou um paciente cadastrado
    Quando tento agendar uma consulta para daqui a 1 hora
    Então devo ver a mensagem "Antecedência mínima: 2 horas"
    E a consulta não deve ser criada

  Cenário: Tentar agendar com 3 consultas já marcadas
    Dado que sou um paciente com 3 consultas agendadas
    Quando tento agendar uma nova consulta
    Então devo ver a mensagem "Limite de 3 consultas atingido"
    E devo ser orientado a cancelar ou comparecer em uma consulta

  Cenário: Cancelar consulta com mais de 4h de antecedência
    Dado que tenho uma consulta agendada para daqui a 2 dias
    Quando cancelo a consulta
    Então o cancelamento deve ser confirmado
    E não deve haver cobrança de multa
    E o horário deve ser liberado
    E o médico deve ser notificado

  Cenário: Cancelar consulta com menos de 4h de antecedência
    Dado que tenho uma consulta agendada para daqui a 2 horas
    Quando cancelo a consulta
    Então o cancelamento deve ser confirmado
    E uma multa de 50% deve ser aplicada
    E o horário deve ser liberado
    E o médico deve ser notificado

  Esquema do Cenário: Validar dados do paciente
    Dado que estou agendando uma consulta
    Quando informo o CPF "<cpf>"
    Então devo ver a mensagem "<mensagem>"

    Exemplos:
      | cpf             | mensagem                    |
      | 123.456.789-00  | CPF válido                  |
      | 111.111.111-11  | CPF inválido                |
      | abc.def.ghi-jk  | Formato de CPF inválido     |
      |                 | CPF é obrigatório           |

  Cenário: Receber lembretes automáticos
    Dado que tenho uma consulta agendada para amanhã às "14:00"
    Quando faltarem 24 horas para a consulta
    Então devo receber um SMS com "Lembrete: Consulta amanhã às 14:00"
    E quando faltarem 2 horas
    Então devo receber outro SMS com "Sua consulta é às 14:00 hoje"
```

**4. Código Python Gerado**

```python
# domain/entities.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

class EspecialidadeMedica(Enum):
    CARDIOLOGIA = "cardiologia"
    DERMATOLOGIA = "dermatologia"
    PEDIATRIA = "pediatria"
    # ... outras

class StatusAgendamento(Enum):
    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    CANCELADO = "cancelado"
    REALIZADO = "realizado"
    NAO_COMPARECEU = "nao_compareceu"

@dataclass
class Paciente:
    id: str
    nome: str
    cpf: str
    email: str
    telefone: str
    data_nascimento: datetime
    
    def validar(self) -> tuple[bool, str]:
        if not self._validar_cpf():
            return False, "CPF inválido"
        if not self._validar_email():
            return False, "Email inválido"
        if not self._validar_telefone():
            return False, "Telefone inválido"
        return True, "Válido"

@dataclass
class Medico:
    id: str
    nome: str
    crm: str
    especialidade: EspecialidadeMedica
    email: str

@dataclass
class Agendamento:
    id: str
    paciente: Paciente
    medico: Medico
    data_hora: datetime
    status: StatusAgendamento
    criado_em: datetime
    cancelado_em: Optional[datetime] = None
    motivo_cancelamento: Optional[str] = None
    
    def pode_cancelar(self) -> tuple[bool, str, float]:
        """Retorna (permitido, motivo, multa)"""
        agora = datetime.now()
        horas_antecedencia = (self.data_hora - agora).total_seconds() / 3600
        
        if horas_antecedencia >= 4:
            return True, "Cancelamento permitido", 0.0
        elif horas_antecedencia >= 0:
            return True, "Multa de 50%", 0.5
        else:
            return False, "Consulta já passou", 1.0


# use_cases/agendar_consulta.py
class AgendarConsultaUseCase:
    ANTECEDENCIA_MINIMA_HORAS = 2
    MAX_CONSULTAS_POR_PACIENTE = 3
    
    def __init__(self, repo_agendamentos, repo_medicos, servico_notificacao):
        self.repo_agendamentos = repo_agendamentos
        self.repo_medicos = repo_medicos
        self.notificacao = servico_notificacao
    
    def executar(
        self,
        paciente: Paciente,
        medico_id: str,
        data_hora: datetime
    ) -> Agendamento:
        # Validar paciente
        valido, mensagem = paciente.validar()
        if not valido:
            raise ValueError(mensagem)
        
        # Verificar antecedência mínima
        agora = datetime.now()
        horas = (data_hora - agora).total_seconds() / 3600
        if horas < self.ANTECEDENCIA_MINIMA_HORAS:
            raise ValueError(
                f"Antecedência mínima: {self.ANTECEDENCIA_MINIMA_HORAS} horas"
            )
        
        # Verificar limite de consultas
        consultas_ativas = self.repo_agendamentos.contar_ativas(paciente.id)
        if consultas_ativas >= self.MAX_CONSULTAS_POR_PACIENTE:
            raise ValueError(
                f"Limite de {self.MAX_CONSULTAS_POR_PACIENTE} consultas atingido"
            )
        
        # Verificar disponibilidade do médico
        medico = self.repo_medicos.buscar(medico_id)
        if not medico:
            raise ValueError("Médico não encontrado")
        
        if not self.repo_medicos.horario_disponivel(medico_id, data_hora):
            raise ValueError("Horário indisponível")
        
        # Criar agendamento
        agendamento = Agendamento(
            id=self._gerar_id(),
            paciente=paciente,
            medico=medico,
            data_hora=data_hora,
            status=StatusAgendamento.AGENDADO,
            criado_em=datetime.now()
        )
        
        # Salvar
        self.repo_agendamentos.salvar(agendamento)
        
        # Notificações
        self.notificacao.enviar_confirmacao_paciente(paciente, agendamento)
        self.notificacao.enviar_notificacao_medico(medico, agendamento)
        self.notificacao.agendar_lembretes(agendamento)
        
        return agendamento


# tests/test_agendar_consulta.py
def test_agendar_consulta_com_sucesso():
    # Arrange
    paciente = criar_paciente_valido()
    medico_id = "medico-123"
    data_hora = datetime.now() + timedelta(hours=24)
    
    use_case = AgendarConsultaUseCase(repo_mock, repo_medicos_mock, notif_mock)
    
    # Act
    agendamento = use_case.executar(paciente, medico_id, data_hora)
    
    # Assert
    assert agendamento.status == StatusAgendamento.AGENDADO
    assert agendamento.paciente.id == paciente.id
    assert notif_mock.emails_enviados == 1
    assert notif_mock.sms_enviados == 1
```

---

## Exemplo 2: E-commerce - Carrinho de Compras

### 📄 Input (Descrição do Negócio)

```markdown
Sistema de Carrinho de Compras - Loja Online de Eletrônicos

CONTEXTO:
E-commerce com 10.000+ produtos precisa de sistema de carrinho robusto e performático.

ATORES:
- Cliente (visitante ou logado)
- Sistema de Estoque
- Sistema de Precificação
- Sistema de Pagamento
- Sistema de Frete

FLUXO PRINCIPAL:
1. Cliente navega por produtos
2. Adiciona produtos ao carrinho
3. Sistema reserva estoque temporariamente
4. Cliente altera quantidades (opcional)
5. Cliente aplica cupom de desconto (opcional)
6. Cliente calcula frete
7. Cliente escolhe forma de pagamento
8. Sistema processa pagamento
9. Confirma pedido

REGRAS DE CARRINHO:
- Estoque reservado por 15 minutos
- Após 15min, libera automaticamente
- Máximo 10 unidades por produto
- Máximo 50 itens no carrinho total
- Preços atualizados em tempo real
- Desconto aplicado sobre subtotal

PRECIFICAÇÃO:
- Preço base do produto
- Descontos promocionais (%)
- Cupons de desconto (R$ ou %)
- Frete calculado por CEP
- Impostos já incluídos no preço

VALIDAÇÕES:
- Estoque disponível ao adicionar
- Quantidade positiva e inteira
- Produto ativo e disponível
- CEP válido para frete
- Cupom válido e ativo
- Limite de desconto: 70%

FRETE:
- PAC: 5-10 dias úteis (mais barato)
- SEDEX: 2-3 dias úteis (mais caro)
- Retirada: mesmo dia (grátis)
- Frete grátis acima de R$ 500

CUPONS DE DESCONTO:
- Código único
- Validade (início e fim)
- Tipo: percentual ou fixo
- Valor mínimo do pedido
- Primeira compra ou geral
- Limite de uso por cliente
- Limite de uso total

ESTOQUE:
- Verificar disponibilidade real-time
- Reservar ao adicionar no carrinho
- Liberar se não comprar em 15min
- Notificar se produto ficar indisponível
- Sugerir produtos similares

PERSISTÊNCIA:
- Carrinho salvo para clientes logados
- Carrinho temporário (cookie) para visitantes
- Sincronizar ao fazer login
- Manter por 30 dias se inativo

CÁLCULOS:
- Subtotal = Σ(preço × quantidade)
- Desconto Cupom = f(subtotal, cupom)
- Frete = f(CEP, peso, valor)
- Total = Subtotal - Desconto + Frete

NOTIFICAÇÕES:
- Produto adicionado (toast)
- Estoque baixo (< 5 unidades)
- Produto indisponível
- Reserva expirando (5min antes)
- Preço alterado

EXCEÇÕES:
- Produto removido do catálogo: remover do carrinho
- Estoque insuficiente: atualizar quantidade máxima
- Cupom expirado: remover e notificar
- Frete não disponível: sugerir alternativas
```

### 📊 Output Esperado

**1. Domain Storytelling**
```
FLUXO: Adicionar Produto ao Carrinho

1. Cliente → visualiza → Página do Produto
2. Cliente → seleciona → Quantidade
3. Cliente → clica → "Adicionar ao Carrinho"
4. Sistema → verifica → Estoque Disponível
5. Sistema → valida → Quantidade Máxima
6. Sistema → reserva → Estoque Temporário (15min)
7. Sistema → adiciona → Item ao Carrinho
8. Sistema → calcula → Subtotal
9. Sistema → exibe → Toast de Confirmação
10. Sistema → atualiza → Badge do Carrinho
11. Cliente → visualiza → Carrinho Atualizado

FLUXO: Aplicar Cupom

1. Cliente → acessa → Carrinho
2. Cliente → digita → Código do Cupom
3. Sistema → valida → Cupom (validade, limites)
4. Sistema → verifica → Valor Mínimo do Pedido
5. Sistema → calcula → Desconto
6. Sistema → aplica → Desconto ao Subtotal
7. Sistema → atualiza → Total
8. Sistema → exibe → Economia

ENTIDADES:
- Carrinho
- ItemCarrinho
- Produto
- Cupom
- ReservaEstoque
- CalculadoraPreco
- CalculadoraFrete
```

**2. User Stories**

```markdown
### US-010: Adicionar Produto ao Carrinho
**Como** cliente  
**Quero** adicionar produtos ao meu carrinho  
**Para** comprar múltiplos itens de uma vez  

**Critérios de Aceitação:**
- Validar estoque antes de adicionar
- Máximo 10 unidades por produto
- Máximo 50 itens no carrinho
- Reservar estoque por 15 minutos
- Exibir confirmação visual
- Atualizar subtotal automaticamente

---

### US-011: Aplicar Cupom de Desconto
**Como** cliente  
**Quero** aplicar cupom de desconto  
**Para** economizar na compra  

**Critérios de Aceitação:**
- Validar código do cupom
- Verificar validade (datas)
- Verificar valor mínimo do pedido
- Calcular desconto corretamente
- Exibir valor economizado
- Permitir remover cupom

---

### US-012: Calcular Frete
**Como** cliente  
**Quero** calcular o frete antes de finalizar  
**Para** saber o custo total  

**Critérios de Aceitação:**
- Validar CEP
- Mostrar opções (PAC, SEDEX, Retirada)
- Exibir prazo de entrega
- Mostrar se tem frete grátis
- Salvar opção escolhida
```

**3. Cenários Gherkin**

```gherkin
Funcionalidade: Carrinho de Compras

  Contexto:
    Dado que existe um produto "Notebook Dell" com preço R$ 3.000
    E o produto tem 10 unidades em estoque
    E o carrinho está vazio

  Cenário: Adicionar produto com sucesso
    Quando adiciono 2 unidades de "Notebook Dell" ao carrinho
    Então o carrinho deve conter 1 item
    E a quantidade do item deve ser 2
    E o subtotal deve ser R$ 6.000
    E o estoque deve ser reservado por 15 minutos
    E devo ver a mensagem "Produto adicionado ao carrinho"

  Cenário: Tentar adicionar mais que o estoque disponível
    Quando adiciono 15 unidades de "Notebook Dell" ao carrinho
    Então devo ver a mensagem "Estoque insuficiente. Máximo: 10 unidades"
    E o carrinho deve permanecer vazio

  Cenário: Tentar adicionar mais que o limite por produto
    Quando adiciono 11 unidades de "Notebook Dell" ao carrinho
    Então devo ver a mensagem "Máximo 10 unidades por produto"
    E o carrinho deve permanecer vazio

  Cenário: Aplicar cupom de desconto válido
    Dado que tenho "Notebook Dell" no carrinho
    E existe um cupom "PRIMEIRACOMPRA" de 10% de desconto
    E o cupom é válido até amanhã
    Quando aplico o cupom "PRIMEIRACOMPRA"
    Então o desconto de R$ 600 deve ser aplicado
    E o total deve ser R$ 5.400
    E devo ver "Cupom aplicado! Você economizou R$ 600"

  Cenário: Tentar aplicar cupom expirado
    Dado que tenho produtos no carrinho
    E existe um cupom "VENCIDO" que expirou ontem
    Quando tento aplicar o cupom "VENCIDO"
    Então devo ver a mensagem "Cupom expirado"
    E nenhum desconto deve ser aplicado

  Cenário: Tentar aplicar cupom com valor mínimo não atingido
    Dado que existe um cupom "FRETEGRATIS" com valor mínimo de R$ 500
    E tenho produtos no carrinho totalizando R$ 300
    Quando tento aplicar o cupom "FRETEGRATIS"
    Então devo ver "Valor mínimo não atingido. Adicione mais R$ 200"

  Cenário: Calcular frete por CEP
    Dado que tenho produtos no carrinho
    Quando informo o CEP "01310-100"
    Então devo ver as opções:
      | Tipo     | Prazo      | Valor   |
      | PAC      | 5-10 dias  | R$ 25   |
      | SEDEX    | 2-3 dias   | R$ 45   |
      | Retirada | Mesmo dia  | Grátis  |

  Cenário: Frete grátis acima de R$ 500
    Dado que tenho produtos totalizando R$ 550
    Quando calculo o frete para "01310-100"
    Então o frete PAC deve ser grátis
    E devo ver "🎉 Você ganhou frete grátis!"

  Cenário: Estoque liberado após 15 minutos
    Dado que adicionei produtos ao carrinho há 16 minutos
    Quando outro cliente tenta comprar o mesmo produto
    Então o estoque deve estar disponível
    E meu carrinho deve ser atualizado
    E devo receber notificação "Alguns itens do seu carrinho expiraram"

  Esquema do Cenário: Validar quantidade
    Quando adiciono <quantidade> unidades ao carrinho
    Então devo ver a mensagem "<mensagem>"

    Exemplos:
      | quantidade | mensagem                              |
      | 0          | Quantidade deve ser maior que zero    |
      | -1         | Quantidade inválida                   |
      | 1          | Produto adicionado ao carrinho        |
      | 10         | Produto adicionado ao carrinho        |
      | 11         | Máximo 10 unidades por produto        |
```

**4. Código Python Gerado**

```python
# domain/entities/carrinho.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

@dataclass
class ItemCarrinho:
    produto_id: str
    nome: str
    preco: Decimal
    quantidade: int
    reservado_em: datetime
    reservado_ate: datetime
    
    @property
    def subtotal(self) -> Decimal:
        return self.preco * self.quantidade
    
    def esta_expirado(self) -> bool:
        return datetime.now() > self.reservado_ate
    
    def minutos_restantes(self) -> int:
        delta = self.reservado_ate - datetime.now()
        return max(0, int(delta.total_seconds() / 60))


@dataclass
class Cupom:
    codigo: str
    tipo: str  # 'percentual' ou 'fixo'
    valor: Decimal
    valido_de: datetime
    valido_ate: datetime
    valor_minimo_pedido: Decimal
    limite_uso_cliente: int
    limite_uso_total: int
    usos_totais: int = 0
    
    def esta_valido(self) -> tuple[bool, str]:
        agora = datetime.now()
        
        if agora < self.valido_de:
            return False, "Cupom ainda não está ativo"
        
        if agora > self.valido_ate:
            return False, "Cupom expirado"
        
        if self.usos_totais >= self.limite_uso_total:
            return False, "Cupom esgotado"
        
        return True, "Cupom válido"
    
    def calcular_desconto(self, subtotal: Decimal) -> Decimal:
        if self.tipo == 'percentual':
            return subtotal * (self.valor / 100)
        else:  # fixo
            return min(self.valor, subtotal)


@dataclass
class Carrinho:
    id: str
    cliente_id: Optional[str]
    itens: List[ItemCarrinho] = field(default_factory=list)
    cupom: Optional[Cupom] = None
    criado_em: datetime = field(default_factory=datetime.now)
    atualizado_em: datetime = field(default_factory=datetime.now)
    
    TEMPO_RESERVA_MINUTOS = 15
    MAX_ITENS_CARRINHO = 50
    MAX_QUANTIDADE_POR_PRODUTO = 10
    
    @property
    def quantidade_total_itens(self) -> int:
        return sum(item.quantidade for item in self.itens)
    
    @property
    def subtotal(self) -> Decimal:
        return sum(item.subtotal for item in self.itens)
    
    @property
    def desconto(self) -> Decimal:
        if not self.cupom:
            return Decimal('0')
        return self.cupom.calcular_desconto(self.subtotal)
    
    def calcular_total(self, frete: Decimal = Decimal('0')) -> Decimal:
        return self.subtotal - self.desconto + frete
    
    def pode_adicionar_item(self, quantidade: int) -> tuple[bool, str]:
        if quantidade <= 0:
            return False, "Quantidade deve ser maior que zero"
        
        if quantidade > self.MAX_QUANTIDADE_POR_PRODUTO:
            return False, f"Máximo {self.MAX_QUANTIDADE_POR_PRODUTO} unidades por produto"
        
        if self.quantidade_total_itens + quantidade > self.MAX_ITENS_CARRINHO:
            return False, f"Máximo {self.MAX_ITENS_CARRINHO} itens no carrinho"
        
        return True, "OK"
    
    def limpar_itens_expirados(self) -> List[ItemCarrinho]:
        """Remove itens cuja reserva expirou"""
        expirados = [item for item in self.itens if item.esta_expirado()]
        self.itens = [item for item in self.itens if not item.esta_expirado()]
        return expirados


# use_cases/adicionar_ao_carrinho.py
class AdicionarAoCarrinhoUseCase:
    def __init__(
        self,
        repo_carrinho,
        repo_produtos,
        servico_estoque,
        servico_notificacao
    ):
        self.repo_carrinho = repo_carrinho
        self.repo_produtos = repo_produtos
        self.estoque = servico_estoque
        self.notificacao = servico_notificacao
    
    def executar(
        self,
        carrinho_id: str,
        produto_id: str,
        quantidade: int
    ) -> Carrinho:
        # Buscar carrinho
        carrinho = self.repo_carrinho.buscar(carrinho_id)
        if not carrinho:
            carrinho = Carrinho(id=carrinho_id, cliente_id=None)
        
        # Limpar expirados
        expirados = carrinho.limpar_itens_expirados()
        if expirados:
            self.notificacao.notificar_itens_expirados(carrinho, expirados)
            self.estoque.liberar_reservas([item.produto_id for item in expirados])
        
        # Validar quantidade
        pode, mensagem = carrinho.pode_adicionar_item(quantidade)
        if not pode:
            raise ValueError(mensagem)
        
        # Buscar produto
        produto = self.repo_produtos.buscar(produto_id)
        if not produto:
            raise ValueError("Produto não encontrado")
        
        if not produto.ativo:
            raise ValueError("Produto indisponível")
        
        # Verificar estoque
        estoque_disponivel = self.estoque.verificar_disponibilidade(produto_id)
        if estoque_disponivel < quantidade:
            raise ValueError(
                f"Estoque insuficiente. Máximo: {estoque_disponivel} unidades"
            )
        
        # Verificar se produto já está no carrinho
        item_existente = next(
            (i for i in carrinho.itens if i.produto_id == produto_id),
            None
        )
        
        if item_existente:
            nova_quantidade = item_existente.quantidade + quantidade
            if nova_quantidade > Carrinho.MAX_QUANTIDADE_POR_PRODUTO:
                raise ValueError(
                    f"Máximo {Carrinho.MAX_QUANTIDADE_POR_PRODUTO} unidades por produto"
                )
            item_existente.quantidade = nova_quantidade
            item_existente.reservado_ate = datetime.now() + timedelta(
                minutes=Carrinho.TEMPO_RESERVA_MINUTOS
            )
        else:
            # Criar novo item
            agora = datetime.now()
            item = ItemCarrinho(
                produto_id=produto_id,
                nome=produto.nome,
                preco=produto.preco,
                quantidade=quantidade,
                reservado_em=agora,
                reservado_ate=agora + timedelta(
                    minutes=Carrinho.TEMPO_RESERVA_MINUTOS
                )
            )
            carrinho.itens.append(item)
        
        # Reservar estoque
        self.estoque.reservar(produto_id, quantidade, carrinho.id)
        
        # Salvar carrinho
        carrinho.atualizado_em = datetime.now()
        self.repo_carrinho.salvar(carrinho)
        
        # Notificar
        self.notificacao.produto_adicionado(carrinho, produto, quantidade)
        
        return carrinho


# use_cases/aplicar_cupom.py
class AplicarCupomUseCase:
    def __init__(self, repo_carrinho, repo_cupons):
        self.repo_carrinho = repo_carrinho
        self.repo_cupons = repo_cupons
    
    def executar(self, carrinho_id: str, codigo_cupom: str) -> Carrinho:
        # Buscar carrinho
        carrinho = self.repo_carrinho.buscar(carrinho_id)
        if not carrinho:
            raise ValueError("Carrinho não encontrado")
        
        if not carrinho.itens:
            raise ValueError("Carrinho vazio")
        
        # Buscar cupom
        cupom = self.repo_cupons.buscar_por_codigo(codigo_cupom)
        if not cupom:
            raise ValueError("Cupom inválido")
        
        # Validar cupom
        valido, mensagem = cupom.esta_valido()
        if not valido:
            raise ValueError(mensagem)
        
        # Verificar valor mínimo
        if carrinho.subtotal < cupom.valor_minimo_pedido:
            faltam = cupom.valor_minimo_pedido - carrinho.subtotal
            raise ValueError(
                f"Valor mínimo não atingido. Adicione mais R$ {faltam:.2f}"
            )
        
        # Verificar limite por cliente
        if carrinho.cliente_id:
            usos_cliente = self.repo_cupons.contar_usos_cliente(
                codigo_cupom,
                carrinho.cliente_id
            )
            if usos_cliente >= cupom.limite_uso_cliente:
                raise ValueError("Você já usou este cupom o máximo de vezes")
        
        # Aplicar cupom
        carrinho.cupom = cupom
        carrinho.atualizado_em = datetime.now()
        self.repo_carrinho.salvar(carrinho)
        
        return carrinho


# tests/test_carrinho.py
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

def test_adicionar_produto_com_sucesso():
    # Arrange
    produto = criar_produto("Notebook", Decimal('3000'))
    carrinho = Carrinho(id="cart-123")
    estoque_mock = Mock(verificar_disponibilidade=Mock(return_value=10))
    
    use_case = AdicionarAoCarrinhoUseCase(
        repo_carrinho_mock,
        repo_produtos_mock,
        estoque_mock,
        notificacao_mock
    )
    
    # Act
    resultado = use_case.executar("cart-123", "prod-123", 2)
    
    # Assert
    assert len(resultado.itens) == 1
    assert resultado.itens[0].quantidade == 2
    assert resultado.subtotal == Decimal('6000')
    estoque_mock.reservar.assert_called_once()


def test_tentar_adicionar_mais_que_estoque():
    # Arrange
    estoque_mock = Mock(verificar_disponibilidade=Mock(return_value=5))
    use_case = AdicionarAoCarrinhoUseCase(..., estoque_mock, ...)
    
    # Act & Assert
    with pytest.raises(ValueError, match="Estoque insuficiente"):
        use_case.executar("cart-123", "prod-123", 10)


def test_aplicar_cupom_percentual():
    # Arrange
    carrinho = criar_carrinho_com_produtos(subtotal=Decimal('1000'))
    cupom = Cupom(
        codigo="DESC10",
        tipo="percentual",
        valor=Decimal('10'),
        valido_de=datetime.now() - timedelta(days=1),
        valido_ate=datetime.now() + timedelta(days=1),
        valor_minimo_pedido=Decimal('100'),
        limite_uso_cliente=5,
        limite_uso_total=1000
    )
    
    # Act
    desconto = cupom.calcular_desconto(carrinho.subtotal)
    
    # Assert
    assert desconto == Decimal('100')  # 10% de 1000


def test_cupom_expirado():
    # Arrange
    cupom = Cupom(
        codigo="VENCIDO",
        valido_de=datetime.now() - timedelta(days=10),
        valido_ate=datetime.now() - timedelta(days=1),  # Expirou ontem
        ...
    )
    
    # Act
    valido, mensagem = cupom.esta_valido()
    
    # Assert
    assert not valido
    assert "expirado" in mensagem.lower()


def test_itens_expirados_sao_removidos():
    # Arrange
    carrinho = Carrinho(id="cart-123")
    item_expirado = ItemCarrinho(
        produto_id="prod-1",
        nome="Produto 1",
        preco=Decimal('100'),
        quantidade=1,
        reservado_em=datetime.now() - timedelta(minutes=20),
        reservado_ate=datetime.now() - timedelta(minutes=5)  # Expirado
    )
    carrinho.itens.append(item_expirado)
    
    # Act
    expirados = carrinho.limpar_itens_expirados()
    
    # Assert
    assert len(expirados) == 1
    assert len(carrinho.itens) == 0
```

---

## Resumo dos Outputs

### ✅ O que o Sistema Gera Automaticamente:

1. **📖 Domain Storytelling** (5-10 páginas)
   - Atores identificados
   - Fluxos numerados
   - Entidades do domínio
   - Glossário de termos

2. **📋 User Stories** (10-20 stories)
   - Formato Como/Quero/Para
   - Critérios de aceitação
   - Definição de pronto
   - Priorização

3. **🧪 Cenários BDD/Gherkin** (30-50 cenários)
   - Casos de sucesso
   - Casos de falha
   - Edge cases
   - Esquemas de cenário

4. **💻 Código Python** (500-2000 linhas)
   - Entidades (dataclasses)
   - Use Cases
   - Step Definitions
   - Testes unitários
   - Mocks e stubs

5. **🔎 Relatório de Revisão**
   - Aderência às specs
   - Qualidade do código
   - Melhorias sugeridas
   - Riscos identificados

### ⏱️ Tempo de Geração

| Complexidade | Tempo Estimado | Tokens |
|--------------|----------------|--------|
| Simples (1-3 features) | 3-5 min | ~50k |
| Médio (5-10 features) | 10-15 min | ~200k |
| Complexo (10+ features) | 25-40 min | ~500k |

---

## 🎯 Dicas para Melhores Resultados

### ✅ Faça:
- Seja específico sobre regras de negócio
- Inclua valores numéricos (limites, prazos)
- Liste exceções e casos especiais
- Mencione integrações necessárias
- Especifique validações

### ❌ Evite:
- Descrições muito genéricas
- "Fazer sistema de X" sem detalhes
- Misturar múltiplos domínios
- Requisitos técnicos (use React, etc)
- Descrições muito longas (>10 páginas)

---

## 📞 Suporte

Dúvidas sobre os exemplos?
- 📖 Consulte o README.md
- 🐛 Abra uma issue no GitHub
- 💬 Pergunte no Discord

**Pronto para começar? Execute:** `streamlit run app_streamlit.py` 🚀