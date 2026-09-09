from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_caching import Cache
from flask_compress import Compress

db = SQLAlchemy()
migrate = Migrate()
# SimpleCache (em memória, por processo) — cache local de resposta pra
# rotas de leitura pesada (ver GET /api/produtos). Suficiente aqui porque
# roda num único processo Flask; se um dia isso escalar pra múltiplos
# workers/processos, precisaria virar Redis pra todos compartilharem o
# mesmo cache (ver comentário em __init__.py sobre invalidação).
cache = Cache()
compress = Compress()
