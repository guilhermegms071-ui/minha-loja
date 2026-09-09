"""
Rotas do Bling:
- /bling/authorize  → inicia o fluxo OAuth2 (redireciona pro Bling)
- /bling/callback   → recebe o 'code' de volta e troca por tokens
- /bling/status     → diz se a integração está autorizada e válida
- /bling/sync       → força sincronização do catálogo (chamado manualmente ou por job)
"""
import secrets

from flask import Blueprint, current_app, jsonify, redirect, request, session

from app.extensions import cache, db
from app.models import BlingToken, Produto
from app.blueprints.bling import client as bling_client
from app.blueprints.bling.sync_service import upsert_produto
from app.blueprints.admin.auth import requer_admin

bp = Blueprint("bling", __name__, url_prefix="/bling")


@bp.route("/authorize")
def authorize():
    state = secrets.token_urlsafe(16)
    session["bling_oauth_state"] = state
    return redirect(bling_client.get_authorize_url(state))


@bp.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = session.pop("bling_oauth_state", None)

    if not code:
        return jsonify({"erro": "Bling não retornou 'code'"}), 400
    if not expected_state or state != expected_state:
        return jsonify({"erro": "state inválido — possível CSRF, refaça a autorização"}), 400

    try:
        bling_client.exchange_code_for_token(code)
    except bling_client.BlingAPIError as e:
        return jsonify({"erro": str(e), "detalhe": e.payload}), 502

    return jsonify({"status": "Bling autorizado com sucesso. Pode fechar esta aba."})


@bp.route("/situacoes")
@requer_admin
def situacoes():
    """Ajuda a descobrir o id_situacao de 'Atendido' (ou equivalente) da SUA
    conta Bling — esses IDs não são fixos, variam de conta pra conta. Rode
    isso uma vez, veja o id da situação que dispara baixa de estoque e
    configure BLING_ID_SITUACAO_ATENDIDO no .env."""
    try:
        modulos = bling_client.listar_modulos()
        modulo_venda = next(
            (m for m in modulos if "venda" in (m.get("descricao") or "").lower()), None
        )
        if modulo_venda is None:
            return jsonify({"erro": "Módulo de Pedido de Venda não encontrado", "modulos": modulos}), 502

        situacoes = bling_client.listar_situacoes_modulo(modulo_venda["id"])
        return jsonify({"modulo": modulo_venda, "situacoes": situacoes})

    except bling_client.BlingAPIError as e:
        current_app.logger.error(f"Falha ao listar situações Bling: {e} | detalhe: {e.payload}")
        return jsonify({"erro": str(e), "status_code": e.status_code, "detalhe": e.payload}), 502


@bp.route("/status")
def status():
    token = BlingToken.query.get(1)
    if token is None:
        return jsonify({"autorizado": False})
    return jsonify({
        "autorizado": True,
        "expira_em": token.expires_at.isoformat(),
    })


@bp.route("/sync", methods=["POST"])
@requer_admin
def sync():
    """Puxa o catálogo completo do Bling e atualiza o cache local (tabela produto).
    Endpoint idempotente — pode ser chamado por cron/APScheduler ou manualmente."""
    try:
        pagina = 1
        total_sincronizados = 0

        while True:
            produtos_bling = bling_client.listar_produtos(
                pagina=pagina, limite=100)
            if not produtos_bling:
                break

            for p in produtos_bling:
                upsert_produto(p)
                total_sincronizados += 1

            db.session.commit()

            if len(produtos_bling) < 100:
                break
            pagina += 1

        # Limpa o cache de GET /api/produtos (ver catalog/routes.py) — sem
        # isso, o catálogo recém-sincronizado continuaria servindo a
        # resposta antiga (cacheada por até 300s) até o timeout expirar
        # sozinho. Só afeta o worker que atendeu esta requisição — ver
        # comentário sobre múltiplos workers em config.py.
        cache.clear()
        return jsonify({"status": "ok", "produtos_sincronizados": total_sincronizados})

    except bling_client.BlingAPIError as e:
        db.session.rollback()
        current_app.logger.error(
            f"Falha na sincronização Bling: {e} | detalhe: {e.payload}")
        return jsonify({"erro": str(e), "status_code": e.status_code, "detalhe": e.payload}), 502


@bp.route("/sync-estoque", methods=["POST"])
@requer_admin
def sync_estoque():
    """Sincroniza SOMENTE o saldo de estoque dos produtos já cadastrados no cache.
    Roda em ciclo mais curto que o /sync geral (estoque muda mais rápido que
    nome/preço/categoria). Não recadastra produto — só atualiza a coluna estoque."""
    try:
        produtos = Produto.query.filter_by(ativo=True).all()
        if not produtos:
            return jsonify({"status": "ok", "produtos_atualizados": 0})

        ids_bling = [p.bling_id for p in produtos]
        saldos = bling_client.obter_saldos_estoque_lote(ids_bling)

        atualizados = 0
        for produto in produtos:
            if produto.bling_id in saldos:
                produto.estoque = saldos[produto.bling_id]
                atualizados += 1

        db.session.commit()
        # Mesmo motivo do /sync acima — estoque é servido por GET
        # /api/produtos (campos inStock/stockQty), então também precisa
        # invalidar o cache pra não mostrar estoque desatualizado.
        cache.clear()
        return jsonify({"status": "ok", "produtos_atualizados": atualizados})

    except bling_client.BlingAPIError as e:
        db.session.rollback()
        current_app.logger.error(
            f"Falha na sincronização de estoque: {e} | detalhe: {e.payload}")
        return jsonify({"erro": str(e), "status_code": e.status_code, "detalhe": e.payload}), 502
