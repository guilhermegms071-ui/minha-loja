from datetime import datetime
from app.extensions import db


class BlingToken(db.Model):
    """Guarda o par access_token/refresh_token do OAuth2 do Bling.
    Linha única (id=1) — uma conta Bling integrada por instalação."""
    __tablename__ = "bling_token"

    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(2048), nullable=False)
    refresh_token = db.Column(db.String(2048), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Produto(db.Model):
    """Cache local do catálogo do Bling. Nunca é a fonte da verdade —
    é sincronizado periodicamente (ver app/blueprints/bling/sync.py)."""
    __tablename__ = "produto"

    id = db.Column(db.Integer, primary_key=True)
    bling_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(120))
    preco = db.Column(db.Numeric(10, 2), nullable=False)
    estoque = db.Column(db.Integer, default=0)
    imagem_url = db.Column(db.String(500))
    ativo = db.Column(db.Boolean, default=True)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Cliente(db.Model):
    __tablename__ = "cliente"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    telefone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255))
    bling_contato_id = db.Column(db.String(64))  # id do contato criado/lido no Bling
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Pedido(db.Model):
    __tablename__ = "pedido"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"), nullable=False)
    status = db.Column(
        db.String(30), default="aguardando_bling"
    )  # aguardando_bling | criado_bling | falhou_bling | cancelado | pago
    # "pago" = atendente confirmou manualmente o pagamento via WhatsApp (sem
    # gateway) e o botão "Marcar como pago" do admin avançou a situação do
    # pedido no Bling, disparando a baixa de estoque nativa de lá.
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    frete = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    bling_pedido_id = db.Column(db.String(64))
    erro_bling = db.Column(db.Text)  # guarda o motivo se a criação no Bling falhar
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    cliente = db.relationship("Cliente", backref="pedidos")
    itens = db.relationship("PedidoItem", backref="pedido", cascade="all, delete-orphan")


class PedidoItem(db.Model):
    __tablename__ = "pedido_item"

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Numeric(10, 2), nullable=False)  # snapshot no momento da compra

    produto = db.relationship("Produto")


class ConversaEstado(db.Model):
    """Máquina de estados simples por telefone — substitui o Typebot
    quando você optar pela versão sem essa peça extra."""
    __tablename__ = "conversa_estado"

    telefone = db.Column(db.String(20), primary_key=True)
    estado = db.Column(db.String(50), default="inicio")
    contexto = db.Column(db.JSON, default=dict)  # dados temporários da conversa
    # Canal original da conversa ("meta" ou "evolution") — precisa ficar
    # salvo por conversa (não só por mensagem) porque a resposta de um
    # agente no Chatwoot chega bem depois, fora do fluxo de request do
    # WhatsApp, e precisamos saber por qual canal reenviar pro cliente.
    canal = db.Column(db.String(20), default="evolution")
    # ID da conversa correspondente no Chatwoot, uma vez que a conversa foi
    # escalada pra atendimento humano — usado nos dois sentidos: pra saber
    # que já existe conversa (não criar outra a cada mensagem nova do
    # cliente) e pro webhook /webhook/chatwoot achar de volta qual telefone
    # responder quando um agente manda mensagem.
    chatwoot_conversation_id = db.Column(db.String(32), index=True, nullable=True)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConfiguracaoLoja(db.Model):
    """Configurações da loja editáveis pelo lojista no painel admin, sem
    precisar mexer em código nem reiniciar o servidor. Linha única (id=1),
    mesmo padrão de BlingToken — uma loja por instalação.

    Regra de fallback pros campos que JÁ existiam como variável de ambiente
    antes dessa tabela existir (atendente_pagamento_telefone, ia_habilitada):
    se o lojista nunca configurou o campo pelo painel (fica vazio/None), o
    valor do .env continua valendo — ver app/services/config_service.py.
    Isso evita quebrar quem já estava rodando com ATENDENTE_PAGAMENTO_TELEFONE
    ou AI_ENABLED configurados só por variável de ambiente. Uma vez que o
    lojista mexe no painel, o valor salvo aqui manda."""
    __tablename__ = "configuracao_loja"

    id = db.Column(db.Integer, primary_key=True)

    texto_saudacao = db.Column(db.String(1000))
    texto_menu_comprar = db.Column(db.String(1000))
    texto_menu_assistencia = db.Column(db.String(1000))
    texto_sobre_loja = db.Column(db.String(1000))
    horario_funcionamento = db.Column(db.String(255))  # texto livre, só exibido — sem lógica de aberto/fechado
    endereco_loja = db.Column(db.String(500))

    # Vazio/None = cai pro ATENDENTE_PAGAMENTO_TELEFONE do .env
    atendente_pagamento_telefone = db.Column(db.String(20))

    # None = cai pro AI_ENABLED do .env. Só um True/False explícito (setado
    # pelo painel) tem prioridade sobre o .env — por isso NÃO tem default
    # aqui: um default fixo (ex: False) sobrescreveria silenciosamente quem
    # já está rodando com AI_ENABLED=true no .env assim que essa tabela
    # fosse criada, o que seria uma regressão.
    ia_habilitada = db.Column(db.Boolean, nullable=True)

    pedido_minimo = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Desconto percentual ÚNICO aplicado a todo pedido, sobre o subtotal.
    # NÃO existe (ainda) desconto por categoria de cliente (VIP, atacado
    # etc.) — fica pra uma iteração futura; hoje é um valor único pra loja
    # inteira, simples de auditar.
    desconto_padrao_percentual = db.Column(db.Numeric(5, 2), nullable=False, default=0)

    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MensagemProcessada(db.Model):
    """Registra o ID de cada mensagem recebida via webhook (Meta ou Evolution).
    Meta e a própria Evolution reenviam eventos se não receberem 200 rápido —
    sem isso, o cliente pode receber a mesma resposta do bot duas vezes."""
    __tablename__ = "mensagem_processada"

    id_mensagem = db.Column(db.String(128), primary_key=True)
    canal = db.Column(db.String(20), nullable=False)
    processada_em = db.Column(db.DateTime, default=datetime.utcnow)
