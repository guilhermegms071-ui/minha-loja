"""
Lógica de sincronização de catálogo compartilhada entre os DOIS caminhos que
atualizam o cache local (tabela Produto):
- polling (/bling/sync, agendado periodicamente — rede de segurança)
- webhook em tempo real (/bling/webhook — atualização imediata)

Os dois precisam upsertar produto exatamente do mesmo jeito, então essa
função mora aqui em vez de duplicada em cada um (extraída de bling/routes.py
quando o webhook foi adicionado)."""
import unicodedata

from app.extensions import db
from app.models import Produto

# Classificação por palavra-chave — o cliente não usa o cadastro de
# categoria da Bling em todos os produtos (loja migrou de outro sistema
# sem recadastrar tudo), então a maioria caía em "outros" mesmo tendo um
# nome que já deixa claro do que se trata. Só entra em ação quando a
# Bling NÃO manda categoria nenhuma pro produto — nunca sobrepõe uma
# categoria real (ver uso em upsert_produto abaixo).
#
# Os nomes de categoria aqui são os mesmos que a própria conta Bling já
# usa nos poucos produtos que TÊM categoria cadastrada (conferido direto
# no banco: "baterias", "telas", "conectores", "carcacas", "cameras",
# "cabos" já existiam) — assim um produto reclassificado cai no mesmo
# grupo/ícone/cor que produtos "irmãos" já corretamente categorizados,
# em vez de inventar um nome de categoria novo pra mesma coisa.
# "acessorios" é a exceção: não havia nenhum produto com essa categoria
# ainda, mas capa/película/fone não cabem em nenhuma das outras.
#
# Ordem importa: a primeira categoria cuja lista de palavras bater
# primeiro no nome vence (ex: um nome com "cabo flex" bate em
# "conectores" antes de chegar em "cabos", pois flex normalmente indica
# peça de conector/tela, não fio solto — ajustável se a triagem real
# mostrar o contrário).
_CATEGORIAS_POR_PALAVRA_CHAVE: list[tuple[str, list[str]]] = [
    ("baterias", ["bateria"]),
    # "frontal" acrescentada depois de rodar contra os nomes reais do
    # catálogo — é o termo que o próprio lojista usa pra tela completa
    # (ex: "FRONTAL SAM A34 OLED..."), mais comum no nome real que
    # "tela"/"display" sozinhos; sem isso, cerca de 400 produtos de tela
    # ficavam de fora.
    ("telas", ["tela", "display", "touch", "frontal"]),
    ("conectores", ["conector", "flex"]),
    # "tampa" sozinha (sem precisar de "traseira" junto) — mesmo motivo:
    # nome real do catálogo costuma ser só "TAMPA MOTO E6S", sem a
    # palavra "traseira".
    ("carcacas", ["carcaca", "tampa", "chassi"]),
    ("cameras", ["camera", "lente"]),
    ("cabos", ["cabo", "carregador"]),
    ("acessorios", ["capa", "pelicula", "fone", "alto falante", "auto falante"]),
]


def _sem_acentos(texto: str) -> str:
    """Remove acentos pra comparação — "câmera"/"camera" e
    "película"/"pelicula" batem igual, sem precisar listar as duas formas."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _classificar_por_palavra_chave(nome: str) -> str | None:
    """Tenta adivinhar a categoria pelo NOME do produto — só chamada quando
    o produto não tem categoria nenhuma vinda da Bling (ver upsert_produto).
    Comparação ignora maiúsculas/minúsculas e acentos. Retorna None se
    nenhuma palavra-chave bater (fica em "outros", igual antes)."""
    nome_normalizado = _sem_acentos(nome or "").lower()
    for categoria, palavras in _CATEGORIAS_POR_PALAVRA_CHAVE:
        if any(_sem_acentos(palavra) in nome_normalizado for palavra in palavras):
            return categoria
    return None


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

    # Categoria real da Bling continua tendo prioridade total — a
    # classificação por palavra-chave só entra quando a Bling não manda
    # categoria nenhuma (produto sem categoria != "outros" digitado à mão
    # lá, é o caso de vir vazio/ausente no payload).
    categoria_bling = ((p.get("categoria") or {}).get("descricao") or "").strip()
    produto.categoria = categoria_bling or _classificar_por_palavra_chave(p.get("nome", "")) or "outros"

    produto.imagem_url = p.get("imagemURL")
    produto.ativo = True

    # estoque exige chamada separada (rate-limited) — feito em job/evento
    # próprio, não aqui, para não estourar o limite de requisições durante
    # o sync de catálogo
    if produto.estoque is None:
        produto.estoque = 0  # produto novo: fica em 0 até o primeiro sync/evento de estoque
