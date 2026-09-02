"""
Lógica de sincronização de catálogo compartilhada entre os DOIS caminhos que
atualizam o cache local (tabela Produto):
- polling (/bling/sync, agendado periodicamente — rede de segurança)
- webhook em tempo real (/bling/webhook — atualização imediata)

Os dois precisam upsertar produto exatamente do mesmo jeito, então essa
função mora aqui em vez de duplicada em cada um (extraída de bling/routes.py
quando o webhook foi adicionado)."""
from app.extensions import db
from app.models import Produto


def upsert_produto(p: dict):
    """Cria ou atualiza um produto no cache local a partir do payload do Bling.
    Ignora produtos inativos ou do tipo serviço.
    NÃO mexe no campo `estoque` — isso é responsabilidade exclusiva da
    sincronização de estoque (polling /bling/sync-estoque ou webhook de
    evento "stock"), que roda em ciclo/gatilho próprio."""
    if p.get("situacao") != "Ativo" and p.get("situacao") != "A":
        return
    if p.get("tipo") not in ("P", None):
        return

    bling_id = str(p["id"])
    produto = Produto.query.filter_by(bling_id=bling_id).first()

    if produto is None:
        produto = Produto(bling_id=bling_id)
        db.session.add(produto)

    produto.nome = p.get("nome", "")
    produto.preco = p.get("preco", 0)
    produto.categoria = (p.get("categoria") or {}).get("descricao", "outros")
    produto.imagem_url = p.get("imagemURL")
    produto.ativo = True

    # estoque exige chamada separada (rate-limited) — feito em job/evento
    # próprio, não aqui, para não estourar o limite de requisições durante
    # o sync de catálogo
    if produto.estoque is None:
        produto.estoque = 0  # produto novo: fica em 0 até o primeiro sync/evento de estoque
