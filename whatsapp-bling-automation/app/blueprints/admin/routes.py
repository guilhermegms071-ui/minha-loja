"""API pro painel do lojista — visão que o front do orderService.ts não tinha
(porque tudo ficava isolado no localStorage de cada cliente)."""
import re

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import ConfiguracaoLoja, Pedido
from app.blueprints.admin.auth import requer_admin
from app.services import config_service

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

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
@requer_admin
def listar_pedidos():
    pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).all()
    return jsonify([
        {
            "id": p.id,
            "numero": p.numero,
            "status": p.status,
            "erroBling": p.erro_bling,
            "blingPedidoId": p.bling_pedido_id,
            "total": float(p.total),
            "cliente": p.cliente.nome,
            "criadoEm": p.criado_em.isoformat(),
        }
        for p in pedidos
    ])


@bp.route("/configuracoes")
@requer_admin
def obter_configuracoes():
    return jsonify(_serialize_config(config_service.obter_configuracao()))


@bp.route("/configuracoes", methods=["PUT"])
@requer_admin
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
@requer_admin
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
