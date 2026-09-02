"""
API de catálogo — o front-end (productService.ts) deve chamar isso
em vez de bater direto no Bling. Sempre lê do cache local (tabela produto),
nunca do Bling em tempo real numa requisição de usuário final.
"""
from flask import Blueprint, jsonify, request

from app.models import Produto

bp = Blueprint("catalog", __name__, url_prefix="/api/produtos")


@bp.route("")
def listar():
    categoria = request.args.get("categoria")
    busca = request.args.get("busca")

    query = Produto.query.filter_by(ativo=True)

    if categoria and categoria != "all":
        query = query.filter_by(categoria=categoria)
    if busca:
        query = query.filter(Produto.nome.ilike(f"%{busca}%"))

    produtos = query.order_by(Produto.categoria, Produto.nome).all()

    return jsonify([_serialize(p) for p in produtos])


@bp.route("/<int:produto_id>")
def detalhe(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    return jsonify(_serialize(produto))


def _serialize(p: Produto) -> dict:
    return {
        "id": p.id,
        "blingId": p.bling_id,
        "name": p.nome,
        "category": p.categoria,
        "price": float(p.preco),
        "inStock": p.estoque > 0,
        "stockQty": p.estoque,
        "imageUrl": p.imagem_url,
        "atualizadoEm": p.atualizado_em.isoformat() if p.atualizado_em else None,
    }
