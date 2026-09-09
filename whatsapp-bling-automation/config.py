import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ATENÇÃO: agora que existe login por sessão (ver ADMIN_USERNAME/
    # ADMIN_PASSWORD_HASH abaixo), SECRET_KEY passou a ser o que assina o
    # cookie de sessão do admin — com o valor padrão "dev" (ou qualquer
    # valor fraco/previsível), alguém poderia forjar um cookie de sessão
    # válido sem saber usuário/senha. Troque por um valor aleatório forte em
    # produção (ex: openssl rand -hex 32).
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    # Sessão do login do painel admin (ver app/blueprints/admin/auth.py) —
    # dura 8h a partir do login, depois disso o painel pede login de novo.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # "Lax" funciona quando front e back estão no mesmo "site" (mesmo
    # domínio registrável, mesmo em portas/subdomínios diferentes — é o caso
    # do localhost:5173 + localhost:5000 em dev). Se em produção o front e o
    # back ficarem em domínios REALMENTE diferentes (ex: loja.com.br e
    # api-outra-coisa.com.br), troque para "None" e SESSION_COOKIE_SECURE
    # para "true" (exige HTTPS) — sem isso o navegador não manda o cookie
    # de sessão entre domínios diferentes.
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cache de resposta (Flask-Caching) — hoje só usado em GET /api/produtos
    # (ver app/blueprints/catalog/routes.py). SimpleCache guarda em memória,
    # DENTRO DE CADA PROCESSO — em produção o Dockerfile sobe gunicorn com
    # --workers 2, então os dois processos têm cada um o seu próprio cache,
    # sem compartilhar nada entre si. cache.clear() (chamado ao fim de
    # /bling/sync, /bling/sync-estoque e do webhook da Bling) só limpa o
    # cache do worker que atendeu aquela requisição — o outro worker pode
    # continuar servindo uma resposta de até CACHE_DEFAULT_TIMEOUT segundos
    # desatualizada até seu próprio cache expirar sozinho. Fixo em código
    # (não por .env de propósito — não foi pedido pra ser configurável
    # ainda); se isso precisar ser consistente entre workers/processos no
    # futuro, o backend teria que trocar pra Redis (CACHE_TYPE=RedisCache).
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300

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

    # Protege /bling/sync, /bling/sync-estoque e /bling/situacoes — exigido
    # no header X-Admin-Key. Uso reservado a chamadas automáticas/internas
    # (o scheduler que sincroniza o Bling sozinho, em app/__init__.py) e a
    # uso manual via curl/Postman — o painel admin em si (usado por humano
    # no navegador) usa login por sessão (ver ADMIN_USERNAME abaixo), nunca
    # esta chave.
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

    # Login único do painel admin — um usuário/senha fixos, guardados aqui
    # do mesmo jeito que ADMIN_API_KEY já era (variável de ambiente, sem
    # tabela no banco: não há necessidade de múltiplos usuários nem de
    # permissões diferenciadas para um único operador). A senha NUNCA fica
    # em texto puro — ADMIN_PASSWORD_HASH guarda o hash gerado com
    # werkzeug.security.generate_password_hash (ver instruções no
    # .env.example), e o login compara com check_password_hash.
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

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
