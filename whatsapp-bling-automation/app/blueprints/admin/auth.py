"""Proteção simples das rotas /api/admin/*.

Não é um sistema de login completo (sem usuário/senha, sem sessão) —
é uma chave fixa (ADMIN_API_KEY no .env) enviada no header X-Admin-Key.
Suficiente para uso interno de um único lojista; se no futuro mais de
uma pessoa for acessar o painel com permissões diferentes, isso precisa
evoluir para Flask-Login com usuários de verdade."""
from functools import wraps

from flask import current_app, jsonify, request


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
