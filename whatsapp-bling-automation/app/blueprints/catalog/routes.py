"""
API de catálogo — o front-end (productService.ts) deve chamar isso
em vez de bater direto no Bling. Sempre lê do cache local (tabela produto),
nunca do Bling em tempo real numa requisição de usuário final.
"""
from flask import Blueprint, jsonify, request

from app.extensions import cache
from app.models import Produto

bp = Blueprint("catalog", __name__, url_prefix="/api/produtos")


@bp.route("")
# query_string=True é ESSENCIAL aqui — sem isso, o Flask-Caching usa só o
# path (request.path) como chave, ignorando ?categoria=/?busca=, e uma
# busca ou filtro de categoria qualquer passaria a devolver o resultado
# cacheado de OUTRO filtro (ou do catálogo sem filtro nenhum). Com
# query_string=True, cada combinação de categoria/busca vira sua própria
# entrada de cache, e os filtros continuam se comportando exatamente como
# antes — só passam a ser servidos do cache por até 300s.
@cache.cached(timeout=300, query_string=True)
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
