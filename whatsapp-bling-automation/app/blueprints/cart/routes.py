"""
API de pedidos — substitui orderService.ts do front.

Diferença crítica em relação ao protótipo React original:
- O status "criado_bling" só é setado se a chamada ao Bling REALMENTE
  funcionar. Se falhar, o pedido fica com status "aguardando_bling" ou
  "falhou_bling" e isso é visível pro cliente e pro lojista — nunca
  passamos "sucesso" silenciosamente como o orderService.ts fazia.
"""
import json
import random
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Cliente, Pedido, PedidoItem, Produto
from app.blueprints.bling import client as bling_client
from app.blueprints.admin.auth import requer_admin
from app.services import config_service
from app import limiter

bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")


@bp.route("", methods=["POST"])
@limiter.limit("10 per minute")
def criar():
    payload = request.get_json(force=True)
    config = config_service.obter_configuracao()

    itens_payload = payload.get("itens", [])
    cliente_payload = payload.get("cliente", {})

    if not itens_payload:
        return jsonify({"erro": "Carrinho vazio"}), 400
    if not cliente_payload.get("telefone"):
        return jsonify({"erro": "Telefone do cliente é obrigatório"}), 400

    # 1. Cliente local (upsert por telefone)
    cliente = Cliente.query.filter_by(telefone=cliente_payload["telefone"]).first()
    if cliente is None:
        cliente = Cliente(
            nome=cliente_payload.get("nome", ""),
            telefone=cliente_payload["telefone"],
            email=cliente_payload.get("email", ""),
        )
        db.session.add(cliente)
        db.session.flush()

    # 2. Valida itens e recalcula preço no servidor (nunca confia no preço vindo do front)
    itens_validados = []
    subtotal = 0
    for item in itens_payload:
        produto = Produto.query.get(item["produtoId"])
        if produto is None or not produto.ativo:
            return jsonify({"erro": f"Produto {item['produtoId']} indisponível"}), 400

        quantidade = int(item["quantidade"])
        if quantidade <= 0:
            return jsonify({"erro": f"Quantidade inválida para o produto {produto.nome}"}), 400
        if produto.estoque < quantidade:
            return jsonify({
                "erro": "estoque_insuficiente",
                "mensagem": f"'{produto.nome}' tem apenas {produto.estoque} em estoque (pedido: {quantidade})",
                "produtoId": produto.id,
                "estoqueDisponivel": produto.estoque,
            }), 409

        preco_unitario = produto.preco  # preço vem do cache local, não do front
        subtotal += float(preco_unitario) * quantidade

        itens_validados.append({
            "produto": produto,
            "quantidade": quantidade,
            "preco_unitario": preco_unitario,
        })

    # Pedido mínimo (configurável pelo lojista) — barra o pedido ANTES de
    # criar qualquer coisa no banco, com erro claro pro front mostrar.
    pedido_minimo = float(config.pedido_minimo or 0)
    if pedido_minimo > 0 and subtotal < pedido_minimo:
        return jsonify({
            "erro": "pedido_abaixo_do_minimo",
            "mensagem": f"O pedido mínimo é de R$ {pedido_minimo:.2f} (subtotal atual: R$ {subtotal:.2f})",
            "pedidoMinimo": pedido_minimo,
        }), 400

    frete = float(payload.get("frete", 6.0))

    # Desconto padrão da loja (percentual único, configurável pelo lojista),
    # aplicado sobre o subtotal — etapa separada e comentada de propósito,
    # pra ficar claro de onde vem a diferença entre subtotal e total.
    # NÃO existe (ainda) desconto por categoria de cliente — fica pra uma
    # iteração futura (ver comentário no model ConfiguracaoLoja).
    desconto_percentual = float(config.desconto_padrao_percentual or 0)
    valor_desconto = subtotal * (desconto_percentual / 100) if desconto_percentual > 0 else 0

    total = subtotal - valor_desconto + frete

    # 3. Cria o pedido local — SEMPRE, independente do Bling responder ou não
    pedido = Pedido(
        numero=_gerar_numero_pedido(),
        cliente_id=cliente.id,
        status="aguardando_bling",
        subtotal=subtotal,
        frete=frete,
        total=total,
    )
    db.session.add(pedido)
    db.session.flush()

    for iv in itens_validados:
        db.session.add(PedidoItem(
            pedido_id=pedido.id,
            produto_id=iv["produto"].id,
            quantidade=iv["quantidade"],
            preco_unitario=iv["preco_unitario"],
        ))
        # Reserva o estoque no cache local imediatamente — evita que dois
        # pedidos simultâneos vendam o mesmo último item entre um ciclo de
        # sincronização e outro. O próximo /bling/sync-estoque corrige o
        # valor real vindo do Bling de qualquer forma.
        iv["produto"].estoque = max(0, iv["produto"].estoque - iv["quantidade"])

    db.session.commit()

    # 4. Tenta criar no Bling — se falhar, o pedido continua existindo e visível,
    #    só que com status explícito de falha (nada de sucesso mentiroso)
    _tentar_criar_no_bling(pedido, cliente, itens_validados)

    resposta = _serialize(pedido)
    resposta["linkPagamento"] = _gerar_link_pagamento(pedido)
    return jsonify(resposta), 201


@bp.route("/por-telefone")
def listar_por_telefone():
    """Rota PÚBLICA (sem @requer_admin) — usada pela tela 'Meus pedidos' do
    próprio cliente, que não tem (e não deveria precisar de) a chave de
    admin da loja.

    LIMITAÇÃO DE SEGURANÇA CONHECIDA E ACEITA: isso NÃO é autenticação de
    verdade — é só uma filtragem por número de telefone, sem senha nem OTP.
    Qualquer pessoa que souber (ou adivinhar) o telefone de outro cliente
    consegue ver os pedidos dele por aqui (número, itens, valores — não
    expõe credencial nem dado de pagamento). Suficiente pro cliente ver os
    próprios pedidos sem precisar da chave de admin; evoluir pra login/OTP
    por telefone fica pra uma iteração futura, se a loja precisar de mais
    privacidade entre clientes."""
    telefone = (request.args.get("telefone") or "").strip()
    if not telefone:
        return jsonify({"erro": "Parâmetro 'telefone' é obrigatório"}), 400

    cliente = Cliente.query.filter_by(telefone=telefone).first()
    if cliente is None:
        return jsonify([])

    pedidos = (
        Pedido.query.filter_by(cliente_id=cliente.id)
        .order_by(Pedido.criado_em.desc())
        .all()
    )
    return jsonify([_serialize(p) for p in pedidos])


@bp.route("/<int:pedido_id>")
def detalhe(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    return jsonify(_serialize(pedido))


@bp.route("/<int:pedido_id>/retentar-bling", methods=["POST"])
def retentar_bling(pedido_id):
    """Permite reprocessar manualmente um pedido que falhou ao criar no Bling —
    usado pelo painel do lojista quando erro_bling não é None."""
    pedido = Pedido.query.get_or_404(pedido_id)
    cliente = pedido.cliente
    itens_validados = [
        {"produto": item.produto, "quantidade": item.quantidade, "preco_unitario": item.preco_unitario}
        for item in pedido.itens
    ]
    _tentar_criar_no_bling(pedido, cliente, itens_validados)
    return jsonify(_serialize(pedido))


@bp.route("/<int:pedido_id>/marcar-pago", methods=["POST"])
@requer_admin
def marcar_pago(pedido_id):
    """Botão 'Marcar como pago' do painel admin — usado quando o atendente
    confirma manualmente pelo WhatsApp que o cliente pagou (não há gateway
    de pagamento aqui, a confirmação é sempre humana). Avança a situação do
    pedido no Bling, o que dispara a baixa de estoque nativa de lá."""
    pedido = Pedido.query.get_or_404(pedido_id)

    if not pedido.bling_pedido_id:
        return jsonify({
            "erro": "Pedido ainda não foi criado no Bling — não é possível marcar como pago.",
        }), 400

    id_situacao = current_app.config.get("BLING_ID_SITUACAO_ATENDIDO")
    if not id_situacao:
        return jsonify({
            "erro": (
                "BLING_ID_SITUACAO_ATENDIDO não configurado no .env. "
                "Chame GET /bling/situacoes (com X-Admin-Key) pra descobrir o id certo."
            ),
        }), 503

    try:
        bling_client.alterar_situacao_pedido(pedido.bling_pedido_id, id_situacao)
        pedido.status = "pago"
        pedido.erro_bling = None

    except bling_client.BlingAPIError as e:
        if _bling_ja_esta_na_situacao(e):
            # A Bling recusou dizendo "a venda já possui essa situação" — não é
            # uma falha, é a Bling confirmando que o pedido JÁ está como
            # "Atendido" por lá (pode ter sido marcado direto no painel da
            # Bling, ou uma tentativa anterior que teve sucesso lá mas caiu
            # antes de terminar de salvar aqui). Sem esse tratamento, o pedido
            # ficava com status desatualizado pra sempre no nosso banco — um
            # retry repetiria o mesmo erro indefinidamente, sem nunca
            # sincronizar com a realidade. Aqui a gente trata como sucesso e
            # alinha nosso status com o que já é verdade na Bling.
            pedido.status = "pago"
            pedido.erro_bling = None
            db.session.commit()
            return jsonify(_serialize(pedido))

        # qualquer outro erro: mesmo padrão do resto do projeto, nunca falha silenciosamente
        pedido.erro_bling = f"{e} | detalhe: {e.payload}"
        db.session.commit()
        return jsonify({"erro": str(e), "status_code": e.status_code, "detalhe": e.payload}), 502

    db.session.commit()
    return jsonify(_serialize(pedido))


def _tentar_criar_no_bling(pedido: Pedido, cliente: Cliente, itens_validados: list):
    try:
        # garante contato no Bling (busca por telefone, cria se não existir)
        contato = bling_client.buscar_contato_por_telefone(cliente.telefone)
        if contato is None:
            contato = bling_client.criar_contato(cliente.nome, cliente.telefone, cliente.email or "")

        cliente.bling_contato_id = str(contato["id"])

        resultado = bling_client.criar_pedido_venda(
            cliente_bling_id=cliente.bling_contato_id,
            itens=[
                {
                    "produto_bling_id": iv["produto"].bling_id,
                    "quantidade": iv["quantidade"],
                    "preco_unitario": iv["preco_unitario"],
                }
                for iv in itens_validados
            ],
            observacoes=f"Pedido via catálogo web. Ref interna: {pedido.numero}",
        )

        pedido.bling_pedido_id = str(resultado.get("id"))
        pedido.status = "criado_bling"
        pedido.erro_bling = None

    except bling_client.BlingAPIError as e:
        # NUNCA falha silenciosamente — grava o motivo pro lojista ver e reprocessar.
        # Inclui e.payload (corpo de erro da Bling) além da mensagem genérica,
        # porque só "Erro Bling 400 em /contatos" não diz QUAL campo está inválido.
        pedido.status = "falhou_bling"
        pedido.erro_bling = f"{e} | detalhe: {e.payload}"

    db.session.commit()


def _bling_ja_esta_na_situacao(e: bling_client.BlingAPIError) -> bool:
    """Identifica o erro 'a venda possui a mesma situação' (código 50 da
    Bling, dentro de error.fields[]) — é o sinal de que o pedido JÁ está na
    situação que a gente tentou colocar ele, não uma falha de verdade.
    Casa pelo código estruturado do erro (não por texto da mensagem, que
    poderia mudar) — só esse código específico é tratado como 'já está pago';
    qualquer outro erro da Bling continua sendo reportado como falha real."""
    if e.status_code != 400:
        return False
    try:
        dados = json.loads(e.payload or "")
    except (TypeError, ValueError):
        return False
    campos = (dados.get("error") or {}).get("fields") or []
    return any(campo.get("code") == 50 for campo in campos)


def _gerar_numero_pedido() -> str:
    agora = datetime.utcnow()
    return f"#{agora.strftime('%y%m')}{random.randint(1000, 9999)}"


def _gerar_link_pagamento(pedido: Pedido) -> str | None:
    """Link wa.me pro funcionário que finaliza o pagamento, já com o resumo
    do pedido pré-preenchido — fecha o fluxo real da loja: bot cuida do
    catálogo, humano só entra pra combinar a forma de pagamento."""
    telefone_atendente = config_service.obter_telefone_atendente()
    if not telefone_atendente:
        return None

    linhas_itens = "\n".join(
        f"• {item.quantidade}x {item.produto.nome} — R$ {item.preco_unitario:.2f}"
        for item in pedido.itens
    )
    texto = (
        f"Olá! Gostaria de finalizar o pagamento do pedido {pedido.numero}.\n\n"
        f"{linhas_itens}\n\n"
        f"Subtotal: R$ {pedido.subtotal:.2f}\n"
        f"Frete: R$ {pedido.frete:.2f}\n"
        f"Total: R$ {pedido.total:.2f}"
    )
    return f"https://wa.me/{telefone_atendente}?text={quote(texto)}"


def _serialize(pedido: Pedido) -> dict:
    return {
        "id": pedido.id,
        "numero": pedido.numero,
        "status": pedido.status,
        "erroBling": pedido.erro_bling,
        "subtotal": float(pedido.subtotal),
        "frete": float(pedido.frete),
        "total": float(pedido.total),
        "blingPedidoId": pedido.bling_pedido_id,
        "criadoEm": pedido.criado_em.isoformat(),
        "cliente": {
            "nome": pedido.cliente.nome,
            "telefone": pedido.cliente.telefone,
        },
        "itens": [
            {
                "produtoId": item.produto_id,
                "nome": item.produto.nome,
                "quantidade": item.quantidade,
                "precoUnitario": float(item.preco_unitario),
            }
            for item in pedido.itens
        ],
    }
