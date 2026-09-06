"""Duas proteções DIFERENTES coexistindo de propósito, cada uma para um
tipo de chamador diferente — nenhuma substitui a outra:

- requer_admin: chave fixa (ADMIN_API_KEY no .env) enviada no header
  X-Admin-Key. Reservada a uso automático/interno (o scheduler que
  sincroniza o Bling sozinho, sem ninguém logado — ver
  app/__init__.py) e a uso manual via curl/Postman. Nunca usada pelo
  painel em si.
- requer_sessao: login por sessão (usuário/senha único, ver
  ADMIN_USERNAME/ADMIN_PASSWORD_HASH) — é o que protege todas as rotas
  que o painel admin chama de dentro do navegador. Um humano loga uma
  vez (POST /api/admin/login) e o cookie de sessão do Flask cobre as
  chamadas seguintes por até 8h (ver PERMANENT_SESSION_LIFETIME).

Ambas suficientes para um único operador, sem múltiplos usuários nem
permissões diferenciadas; se isso mudar no futuro, evoluir para
Flask-Login com usuários de verdade."""
from functools import wraps

from flask import current_app, jsonify, request, session


def requer_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        chave_esperada = current_app.config.get("ADMIN_API_KEY")

        if not chave_esperada:
            # Sem chave configurada no .env = painel admin fica bloqueado por padrão,
            # nunca aberto por esquecimento de configuração.
            return jsonify({"erro": "ADMIN_API_KEY não configurada no servidor"}), 503

        chave_recebida = request.headers.get("X-Admin-Key")
        if chave_recebida != chave_esperada:
            return jsonify({"erro": "Não autorizado"}), 401

        return f(*args, **kwargs)

    return wrapper


def requer_sessao(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logado"):
            return jsonify({"erro": "Não autorizado"}), 401
        return f(*args, **kwargs)

    return wrapper
