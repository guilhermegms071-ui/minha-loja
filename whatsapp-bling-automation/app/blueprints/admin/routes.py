"""API pro painel do lojista — visão que o front do orderService.ts não tinha
(porque tudo ficava isolado no localStorage de cada cliente)."""
import re

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import ConfiguracaoLoja, Pedido
from app.blueprints.admin.auth import requer_sessao
from app.blueprints.cart.routes import criar_pedido
from app.services import config_service

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ─── Login (sessão) ─────────────────────────────────────────────────────────
# Usuário/senha únicos, guardados em ADMIN_USERNAME/ADMIN_PASSWORD_HASH no
# .env — ver config.py e o comentário em app/blueprints/admin/auth.py sobre
# por que isso coexiste com ADMIN_API_KEY (chaves diferentes, chamadores
# diferentes) em vez de substituí-la.

@bp.route("/login", methods=["POST"])
def login():
    usuario_esperado = current_app.config.get("ADMIN_USERNAME")
    hash_esperado = current_app.config.get("ADMIN_PASSWORD_HASH")

    if not usuario_esperado or not hash_esperado:
        # Mesmo padrão do requer_admin: sem credencial configurada no .env,
        # o painel fica bloqueado por padrão, nunca aberto por esquecimento.
        return jsonify({"erro": "Login do admin não configurado no servidor"}), 503

    payload = request.get_json(force=True, silent=True) or {}
    usuario = payload.get("usuario", "")
    senha = payload.get("senha", "")

    # Senha NUNCA comparada em texto puro — check_password_hash confere o
    # hash salvo no .env contra a senha recebida (ver instruções de como
    # gerar esse hash no .env.example).
    if usuario != usuario_esperado or not check_password_hash(hash_esperado, senha):
        return jsonify({"erro": "Usuário ou senha inválidos"}), 401

    session.permanent = True  # ativa PERMANENT_SESSION_LIFETIME (8h, ver config.py)
    session["admin_logado"] = True
    return jsonify({"ok": True})


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_logado", None)
    return jsonify({"ok": True})


@bp.route("/me")
def me():
    """Sem @requer_sessao de propósito — é chamada justamente pra DESCOBRIR
    se há sessão válida (ex: ao abrir o painel), então precisa responder
    mesmo sem estar logado, só que com logado=False em vez de 401."""
    return jsonify({"logado": bool(session.get("admin_logado"))})


# ─── Venda balcão ───────────────────────────────────────────────────────────

@bp.route("/venda-balcao", methods=["POST"])
@requer_sessao
def venda_balcao():
    """Rota própria pro painel (exige sessão), separada de POST /api/pedidos
    (que continua público, sem login, pro checkout do cliente final) — as
    duas chamam a MESMA função criar_pedido por baixo (ver
    app/blueprints/cart/routes.py), então validação de estoque, cálculo de
    preço e integração com o Bling são idênticos nos dois fluxos, sem
    lógica duplicada. Só o payload difere: aqui vendaBalcao é sempre True,
    nunca decidido pelo corpo da requisição (evita depender do front mandar
    o campo certo pra valer a proteção de sessão)."""
    payload = request.get_json(force=True, silent=True) or {}
    payload["vendaBalcao"] = True
    resultado, status = criar_pedido(payload)
    return jsonify(resultado), status


# ─── Sincronização Bling (proxy autenticado por sessão) ────────────────────
# /bling/sync e /bling/sync-estoque em si continuam exigindo ADMIN_API_KEY
# (@requer_admin, ver app/blueprints/bling/routes.py) — de propósito, é o
# scheduler automático (app/__init__.py) quem chama elas direto, sem
# ninguém logado. O botão "Sincronizar" do painel, apertado por um humano,
# não deveria precisar saber/colar a ADMIN_API_KEY (isso venceria o
# propósito de ter só usuário/senha) — por isso passa por aqui: exige
# sessão de login normal, e só então repassa a chamada usando a
# ADMIN_API_KEY que já está no servidor (nunca exposta ao navegador),
# exatamente como o scheduler já fazia.
@bp.route("/sincronizar-catalogo", methods=["POST"])
@requer_sessao
def sincronizar_catalogo():
    return _proxy_sync("/bling/sync")


@bp.route("/sincronizar-estoque", methods=["POST"])
@requer_sessao
def sincronizar_estoque():
    return _proxy_sync("/bling/sync-estoque")


def _proxy_sync(caminho: str):
    import requests

    # Mesmo endereço fixo (localhost:5000, o processo Flask chamando a si
    # mesmo) que o scheduler automático já usa em app/__init__.py — repete
    # o padrão existente de propósito, em vez de introduzir BASE_URL aqui
    # (que pode apontar pro domínio público atrás de um proxy reverso, uma
    # rota diferente da que o próprio processo já garante alcançar).
    chave = current_app.config.get("ADMIN_API_KEY", "")
    try:
        resp = requests.post(
            f"http://localhost:5000{caminho}", headers={"X-Admin-Key": chave}, timeout=60
        )
        return jsonify(resp.json()), resp.status_code
    except requests.RequestException as e:
        return jsonify({"erro": f"Falha ao repassar sincronização: {e}"}), 502

# Campos que o painel pode editar via PUT /api/admin/configuracoes, com o
# tipo esperado de cada um — usado tanto pra validar quanto pra converter o
# valor recebido. NUNCA inclui nada de credencial (Client Secret do Bling,
# chave de IA, token do WhatsApp): essas continuam só no .env do servidor,
# fora do alcance deste painel web, de propósito.
_CAMPOS_CONFIGURACAO_EDITAVEIS = {
    "texto_saudacao": str,
    "texto_menu_comprar": str,
    "texto_menu_assistencia": str,
    "texto_sobre_loja": str,
    "horario_funcionamento": str,
    "endereco_loja": str,
    "atendente_pagamento_telefone": str,
    "ia_habilitada": bool,
    "pedido_minimo": float,
    "desconto_padrao_percentual": float,
}


def _camel_para_snake(nome: str) -> str:
    """"atendentePagamentoTelefone" -> "atendente_pagamento_telefone". O
    front manda o payload em camelCase (mesmo padrão usado no resto do
    projeto, ver configService.ts), mas os nomes de coluna aqui — e a lista
    _CAMPOS_CONFIGURACAO_EDITAVEIS acima — são snake_case. Sem essa
    conversão, "campo not in payload" nunca batia com nada e o PUT
    silenciosamente não salvava NENHUM campo (bug real, confirmado rodando
    o PUT de verdade e conferindo o banco antes/depois)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", nome).lower()


@bp.route("/pedidos")
@requer_sessao
def listar_pedidos():
    pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).all()
    return jsonify([
        {
            "id": p.id,
            "numero": p.numero,
            "status": p.status,
            "erroBling": p.erro_bling,
            "blingPedidoId": p.bling_pedido_id,
            "formaPagamento": p.forma_pagamento,  # None em pedidos antigos — front trata como opcional
            "total": float(p.total),
            "cliente": p.cliente.nome,
            "criadoEm": p.criado_em.isoformat(),
        }
        for p in pedidos
    ])


@bp.route("/configuracoes")
@requer_sessao
def obter_configuracoes():
    return jsonify(_serialize_config(config_service.obter_configuracao()))


@bp.route("/configuracoes", methods=["PUT"])
@requer_sessao
def atualizar_configuracoes():
    """Atualiza só os campos enviados no corpo da requisição — campos
    omitidos mantêm o valor atual (não é preciso reenviar tudo a cada
    salvamento)."""
    payload_bruto = request.get_json(force=True, silent=True) or {}
    # Chaves recebidas em camelCase -> snake_case, uma vez, aqui — o resto
    # da função (e a lista de campos editáveis) continua igual, olhando só
    # pra nomes snake_case. Ver _camel_para_snake acima.
    payload = {_camel_para_snake(k): v for k, v in payload_bruto.items()}
    config = config_service.obter_configuracao()

    for campo, tipo in _CAMPOS_CONFIGURACAO_EDITAVEIS.items():
        if campo not in payload:
            continue
        valor = payload[campo]

        if campo == "ia_habilitada":
            # aceita True/False explícito, ou null pra "voltar a seguir o
            # AI_ENABLED do .env" (ver config_service.ia_esta_habilitada)
            setattr(config, campo, None if valor is None else bool(valor))
            continue

        try:
            setattr(config, campo, tipo(valor) if valor is not None else "")
        except (TypeError, ValueError):
            return jsonify({"erro": f"Valor inválido para o campo '{campo}'"}), 400

    db.session.commit()
    return jsonify(_serialize_config(config))


def _serialize_config(config: ConfiguracaoLoja) -> dict:
    return {
        "textoSaudacao": config.texto_saudacao,
        "textoMenuComprar": config.texto_menu_comprar,
        "textoMenuAssistencia": config.texto_menu_assistencia,
        "textoSobreLoja": config.texto_sobre_loja,
        "horarioFuncionamento": config.horario_funcionamento,
        "enderecoLoja": config.endereco_loja,
        "atendentePagamentoTelefone": config.atendente_pagamento_telefone,
        "iaHabilitada": config.ia_habilitada,
        "pedidoMinimo": float(config.pedido_minimo),
        "descontoPadraoPercentual": float(config.desconto_padrao_percentual),
    }


@bp.route("/resumo")
@requer_sessao
def resumo():
    pedidos = Pedido.query.all()
    falharam = [p for p in pedidos if p.status == "falhou_bling"]
    return jsonify({
        "totalPedidos": len(pedidos),
        "faturamento": sum(float(p.total) for p in pedidos if p.status != "cancelado"),
        "pendentesBling": len(falharam),
        "ticketMedio": (
            sum(float(p.total) for p in pedidos) / len(pedidos) if pedidos else 0
        ),
    })
