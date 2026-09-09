from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from app.extensions import db, migrate, cache, compress

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    cache.init_app(app)
    compress.init_app(app)

    origens = app.config.get("ALLOWED_ORIGINS") or ["*"]
    # /api/admin/* precisa de uma regra CORS separada porque agora usa login
    # por sessão (cookie) — e cookie de sessão só é enviado/aceito em
    # requisição cross-origin com supports_credentials=True NO SERVIDOR e
    # credentials:"include" NO FETCH do front (ver apiService.ts), o que por
    # sua vez exige uma origem EXPLÍCITA aqui (navegador recusa a combinação
    # origem "*" + credenciais). Se ALLOWED_ORIGINS não estiver configurado
    # no .env, cai pro front local de dev — em produção, configure
    # ALLOWED_ORIGINS com o domínio real do front ou o login do admin não
    # vai funcionar (o navegador vai bloquear a resposta antes mesmo dela
    # chegar ao código do front).
    origens_admin = app.config.get("ALLOWED_ORIGINS") or ["http://localhost:5173"]
    # Duas rotas de /api/pedidos/* também passaram a exigir sessão
    # (@requer_sessao, ver cart/routes.py: marcar_pago e retentar_bling) —
    # mas vivem fora do prefixo /api/admin/*, então caíam no bloco genérico
    # abaixo (sem supports_credentials), e o navegador bloqueava a resposta
    # em produção ("Access-Control-Allow-Credentials header is '' which
    # must be 'true'..."). Isoladas aqui, no mesmo padrão (origem explícita
    # + supports_credentials=True) do bloco do admin — SEM mexer no resto
    # de /api/pedidos/* (criar pedido e GET detalhe continuam públicos, sem
    # sessão, na regra genérica de sempre).
    _rotas_pedidos_com_sessao = r"pedidos/\d+/(marcar-pago|retentar-bling)"
    # max_age=86400 (24h) faz o navegador CACHEAR a permissão de CORS depois
    # do primeiro preflight — sem isso, todo GET/POST cross-origin disparava
    # um OPTIONS de novo a cada carregamento (era boa parte do tempo de
    # resposta de GET /api/produtos, por exemplo). Só isso, mesma origem/
    # credentials de antes em cada bloco.
    CORS(app, resources={
        r"^/api/admin/.*$": {"origins": origens_admin, "supports_credentials": True, "max_age": 86400},
        rf"^/api/{_rotas_pedidos_com_sessao}$": {"origins": origens_admin, "supports_credentials": True, "max_age": 86400},
        rf"^/api/(?!admin/)(?!{_rotas_pedidos_com_sessao}).*$": {"origins": origens, "max_age": 86400},
    })

    _registrar_blueprints(app)
    _agendar_sincronizacao(app)

    return app


def _registrar_blueprints(app: Flask):
    from app.blueprints.bling.routes import bp as bling_bp
    from app.blueprints.bling.webhook_routes import bp as bling_webhook_bp
    from app.blueprints.catalog.routes import bp as catalog_bp
    from app.blueprints.cart.routes import bp as pedidos_bp
    from app.blueprints.webhook.routes import bp as webhook_bp
    from app.blueprints.admin.routes import bp as admin_bp

    app.register_blueprint(bling_bp)
    app.register_blueprint(bling_webhook_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}


def _agendar_sincronizacao(app: Flask):
    """Dois jobs independentes, agora como REDE DE SEGURANÇA (o webhook em
    tempo real de /bling/webhook cobre a maior parte das atualizações) —
    por isso os intervalos padrão ficaram bem mais longos do que quando o
    polling era o único mecanismo:
    - catálogo (nome/preço/categoria): ciclo mais longo, CATALOG_CACHE_TTL_MINUTES
    - estoque: ciclo mais curto, STOCK_SYNC_INTERVAL_MINUTES, porque muda mais rápido
    Rodam sozinhos em background — o cliente final nunca dispara chamada ao Bling."""
    if app.config.get("TESTING"):
        return

    scheduler = BackgroundScheduler()
    headers = {"X-Admin-Key": app.config.get("ADMIN_API_KEY", "")}

    def job_catalogo():
        with app.app_context():
            import requests
            try:
                requests.post("http://localhost:5000/bling/sync", headers=headers, timeout=60)
            except Exception as e:
                app.logger.error(f"Job de sincronização de catálogo falhou: {e}")

    def job_estoque():
        with app.app_context():
            import requests
            try:
                requests.post("http://localhost:5000/bling/sync-estoque", headers=headers, timeout=60)
            except Exception as e:
                app.logger.error(f"Job de sincronização de estoque falhou: {e}")

    scheduler.add_job(job_catalogo, "interval", minutes=app.config["CATALOG_CACHE_TTL_MINUTES"])
    scheduler.add_job(job_estoque, "interval", minutes=app.config["STOCK_SYNC_INTERVAL_MINUTES"])
    scheduler.start()
