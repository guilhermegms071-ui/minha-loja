import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Bling
    BLING_CLIENT_ID = os.getenv("BLING_CLIENT_ID")
    BLING_CLIENT_SECRET = os.getenv("BLING_CLIENT_SECRET")
    BLING_REDIRECT_URI = os.getenv("BLING_REDIRECT_URI")
    BLING_API_BASE = os.getenv("BLING_API_BASE", "https://api.bling.com.br/Api/v3")
    # Host separado para OAuth (troca/renovação de token) — a Bling exige que
    # as chamadas de recurso (produtos, estoques...) passem por api.bling.com.br,
    # mas o fluxo OAuth em si roda em bling.com.br.
    BLING_OAUTH_BASE = os.getenv("BLING_OAUTH_BASE", "https://bling.com.br/Api/v3")
    # ID da situação "Atendido" (ou equivalente que dispare baixa de estoque)
    # do PEDIDO DE VENDA — específico de cada conta Bling, não é fixo entre
    # contas diferentes. Descubra rodando GET /bling/situacoes (autenticado
    # com X-Admin-Key) e cole o id retornado aqui.
    BLING_ID_SITUACAO_ATENDIDO = os.getenv("BLING_ID_SITUACAO_ATENDIDO", "")

    # Meta / WhatsApp Cloud API
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
    META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
    META_APP_SECRET = os.getenv("META_APP_SECRET")

    # Evolution API
    EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
    EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
    EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME")

    # Chatwoot
    CHATWOOT_URL = os.getenv("CHATWOOT_URL")
    # Token pessoal do agente/bot, gerado em Perfil > Access Token no painel
    # do Chatwoot — autentica as chamadas de criar contato/conversa/mensagem.
    CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")
    CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
    # ID numérico do Inbox tipo "API" (Configurações > Inboxes > o inbox
    # criado) — não confundir com o "Inbox Identifier" (esse é da API
    # pública, usada por widgets; aqui usamos a API de conta, com token).
    CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID")
    # Segredo do webhook (Configurações > Integrações > Webhooks > editar o
    # webhook criado) — usado pra validar X-Chatwoot-Signature em
    # /webhook/chatwoot. Sem isso, o webhook é recusado (nunca aceita
    # payload sem validar origem, mesmo padrão usado com o webhook da Bling).
    CHATWOOT_WEBHOOK_SECRET = os.getenv("CHATWOOT_WEBHOOK_SECRET", "")

    # Regra de negócio: por quanto tempo o catálogo em cache é considerado válido.
    # Defaults bem mais longos que antes (30min/10min) porque o webhook em
    # tempo real (/bling/webhook) passou a cobrir a maior parte das
    # atualizações — o polling aqui virou rede de segurança, não o mecanismo
    # principal. Ajustável por .env se quiser um ciclo mais curto/longo.
    CATALOG_CACHE_TTL_MINUTES = int(os.getenv("CATALOG_CACHE_TTL_MINUTES", "360"))  # 6h
    # Estoque muda mais rápido que cadastro de produto — ciclo próprio, mais curto
    STOCK_SYNC_INTERVAL_MINUTES = int(os.getenv("STOCK_SYNC_INTERVAL_MINUTES", "60"))  # 1h

    # Número do funcionário que finaliza o pagamento (fluxo real da loja)
    ATENDENTE_PAGAMENTO_TELEFONE = os.getenv("ATENDENTE_PAGAMENTO_TELEFONE", "")

    # Protege as rotas /api/admin/* — exigido no header X-Admin-Key
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

    # ── IA na conversa do WhatsApp (opcional) ───────────────────────
    # Camada de INTERPRETAÇÃO por cima do menu numérico — a IA só classifica
    # a intenção do texto livre do cliente, nunca inventa preço/estoque/prazo
    # (isso sempre vem do banco). Desligada por padrão: com AI_ENABLED=False
    # o sistema continua 100% funcional só com o menu estático, sem exigir
    # nenhuma chave configurada — a IA é aditiva, nunca obrigatória.
    AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() in ("1", "true", "yes")
    AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    # Haiku é o modelo Claude mais rápido/barato hoje — adequado pra um
    # classificador de intenção de texto curto, que roda a cada mensagem
    # recebida no webhook (custo por chamada importa aqui).
    AI_MODEL = os.getenv("AI_MODEL", "claude-haiku-4-5")

    # Origens permitidas a chamar a API pública (catálogo, pedidos).
    # Separadas por vírgula no .env. Em dev, deixe vazio para liberar tudo.
    ALLOWED_ORIGINS = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
