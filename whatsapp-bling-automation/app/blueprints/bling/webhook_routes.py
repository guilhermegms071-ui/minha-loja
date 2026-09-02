"""
Recebe webhooks da Bling (produto e estoque criado/atualizado/excluído) pra
atualizar o cache local (tabela Produto) em tempo real, em vez de esperar o
próximo ciclo de polling (/bling/sync, /bling/sync-estoque — mantidos como
rede de segurança, ver app/__init__.py).

Como registrar no painel da Bling (passo manual, não tem API pra isso):
1. developer.bling.com.br → Aplicativos → seu app → aba "Webhooks".
2. Adicionar servidor de recebimento: a URL pública de POST /bling/webhook
   (em produção, o domínio real; em teste local, precisa de um túnel tipo
   ngrok, porque a Bling não alcança localhost).
3. Escolher os recursos "Produtos" e "Estoques" e marcar as ações
   criado/atualizado/excluído.
4. Escolher a versão do payload e salvar.
A Bling também tem uma opção de disparar um evento de TESTE pelo próprio
painel — use isso pra validar contra um payload real, se quiser (o formato
abaixo já vem da documentação oficial, não depende mais desse teste).

Segurança: a Bling assina cada chamada com o header X-Bling-Signature-256
(HMAC-SHA256 do corpo bruto usando o Client Secret do app, no formato
"sha256=<hex>") — validado em _assinatura_valida antes de processar
qualquer coisa. Sem assinatura válida, a chamada é recusada com 401.

Formato do payload — CONFIRMADO na documentação oficial
(developer.bling.com.br/webhooks), não é mais suposição:
{
  "eventId": "...",      # identificador único do evento — usado pra idempotência
  "date": "...",         # ISO 8601
  "version": "...",
  "event": "produto.acao",  # recurso + ação separados por ponto, ex: "product.updated"
  "companyId": ...,
  "data": {...}          # payload específico do recurso/ação, varia por tipo
}
Recursos: order, product, stock, virtual_stock, product_supplier, invoice,
consumer_invoice. Ações: created, updated, deleted.

Duas regras de negócio da doc que o código abaixo trata explicitamente:
1. Idempotência OBRIGATÓRIA — "caso o Bling envie o mesmo webhook duas
   vezes, sua aplicação deve responder a ambas as requisições com um
   código HTTP 2xx". Dedup por eventId reaproveitando a tabela
   MensagemProcessada (mesmo padrão já usado no webhook do WhatsApp) —
   ver _evento_ja_processado/_marcar_evento_processado.
2. Entrega fora de ordem — "um webhook de atualização de produto pode ser
   recebido antes do de criação deste mesmo produto", e "alterar a
   situação de um recurso pra excluído gera um evento de updated" (não
   deleted). Por isso _processar_evento_produto trata "updated" como
   upsert de verdade — upsert_produto() já cria a linha se ela não
   existir, não assume que o produto já foi cadastrado antes."""
import hashlib
import hmac

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import MensagemProcessada, Produto
from app.blueprints.bling import client as bling_client
from app.blueprints.bling.sync_service import upsert_produto

bp = Blueprint("bling_webhook", __name__, url_prefix="/bling")


@bp.route("/webhook", methods=["POST"])
def webhook():
    corpo_bruto = request.get_data()
    assinatura = request.headers.get("X-Bling-Signature-256", "")
    segredo = current_app.config.get("BLING_CLIENT_SECRET", "")

    if not _assinatura_valida(corpo_bruto, assinatura, segredo):
        # Rejeita de verdade (não é um "erro interno" pra engolir e responder
        # 200) — isso é especificamente a validação de origem que impede
        # qualquer um forjar uma chamada fingindo ser a Bling.
        current_app.logger.warning("Webhook Bling recusado: assinatura ausente ou inválida")
        return jsonify({"erro": "assinatura inválida"}), 401

    try:
        payload = request.get_json(silent=True) or {}
        recurso, acao, dados, event_id = _extrair_evento(payload)

        # Idempotência OBRIGATÓRIA pela doc: mesmo evento reenviado tem que
        # responder 2xx de novo, sem reprocessar. Marca ANTES de processar
        # (não depois) — é a checagem de "esse eventId específico já foi
        # visto", independente de a primeira tentativa ter dado certo ou não.
        if event_id:
            if _evento_ja_processado(event_id):
                return jsonify({"status": "já processado"}), 200
            _marcar_evento_processado(event_id)

        id_recurso = _extrair_id_recurso(recurso, dados)

        if not recurso or not id_recurso:
            current_app.logger.warning(f"Webhook Bling com payload não reconhecido: {payload}")
        else:
            recurso_normalizado = recurso.strip().lower()

            if recurso_normalizado == "product":
                _processar_evento_produto(acao, id_recurso)
            elif recurso_normalizado == "stock":
                _processar_evento_estoque(id_recurso)
            elif recurso_normalizado == "virtual_stock":
                # De propósito ignorado: o app usa estoque FÍSICO como fonte
                # da verdade (mesmo campo que o polling já usa,
                # saldoFisicoTotal) — misturar com estoque virtual criaria
                # duas noções conflitantes de "quanto tem disponível pra
                # vender", e o app já reserva estoque localmente na criação
                # do pedido pra cobrir a janela entre um sync e outro.
                current_app.logger.info(f"Webhook Bling: evento de estoque virtual ignorado (id {id_recurso})")
            else:
                current_app.logger.info(f"Webhook Bling: recurso '{recurso}' não tratado, ignorado")

        db.session.commit()

    except Exception as e:
        # Nunca deixa o processamento derrubar a resposta pro Bling — loga e
        # segue. A Bling reenvia (com backoff, até 3 dias) qualquer chamada
        # que não receber 2xx, e desativa o webhook se continuar falhando;
        # como o polling continua rodando como rede de segurança, é melhor
        # sempre confirmar recebimento (200) e deixar o próximo ciclo de
        # polling corrigir o que o webhook não conseguiu processar, do que
        # arriscar o Bling desativar o webhook inteiro por um bug pontual.
        db.session.rollback()
        current_app.logger.error(f"Erro ao processar webhook Bling: {e}")

    return jsonify({"status": "recebido"}), 200


def _assinatura_valida(corpo_bruto: bytes, assinatura_header: str, segredo: str) -> bool:
    """HMAC-SHA256 do corpo bruto usando o Client Secret do app, comparado
    em tempo constante (hmac.compare_digest) pra não vazar informação por
    timing. Sem BLING_CLIENT_SECRET configurado, recusa por padrão — nunca
    aceita webhook sem ter como validar a origem."""
    if not segredo or not assinatura_header.startswith("sha256="):
        return False

    hash_recebido = assinatura_header.removeprefix("sha256=")
    hash_calculado = hmac.new(segredo.encode("utf-8"), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(hash_calculado, hash_recebido)


def _extrair_evento(payload: dict) -> tuple[str | None, str | None, dict, str | None]:
    """Extrai (recurso, acao, dados, event_id) do payload — formato
    CONFIRMADO na documentação oficial: {"eventId", "event": "recurso.acao",
    "data": {...}, ...}. Ver docstring do módulo pra estrutura completa."""
    event_id = payload.get("eventId")
    evento = payload.get("event") or ""
    recurso, _, acao = evento.partition(".")
    dados = payload.get("data") or {}
    return (recurso or None), (acao or None), dados, event_id


def _extrair_id_recurso(recurso: str | None, dados: dict) -> str | None:
    """O campo com o ID do recurso NÃO fica sempre no mesmo lugar — varia
    por tipo de evento, confirmado contra payloads reais:
    - "product.*": id vem direto em data.id.
    - "stock.*" / "virtual_stock.*": não existe "id" de estoque em si que
      interesse aqui; o que identifica QUAL produto o saldo pertence é
      data.produto.id (aninhado), junto dos saldos em data.saldoFisicoTotal
      / data.saldoVirtualTotal. Payload real confirmado (evento
      "stock.created"): {"data": {"produto": {"id": 16697779247},
      "saldoFisicoTotal": 1, ...}} — sem isso, todo evento de resource
      "stock" (criado OU atualizado, o bug não é específico de "created")
      cai em "id_recurso" vazio e é descartado como "payload não
      reconhecido", mesmo sendo um payload perfeitamente válido."""
    if not isinstance(dados, dict):
        return None

    if recurso and recurso.strip().lower() in ("stock", "virtual_stock"):
        produto_ref = dados.get("produto")
        valor = produto_ref.get("id") if isinstance(produto_ref, dict) else None
    else:
        valor = dados.get("id")

    return str(valor) if valor is not None else None


def _evento_ja_processado(event_id: str) -> bool:
    return db.session.get(MensagemProcessada, event_id) is not None


def _marcar_evento_processado(event_id: str):
    """Commita imediatamente, em transação própria — a marca de idempotência
    precisa sobreviver mesmo que o processamento do evento falhe depois e a
    transação principal seja desfeita (rollback no except do webhook)."""
    db.session.add(MensagemProcessada(id_mensagem=event_id, canal="bling"))
    db.session.commit()


def _processar_evento_produto(acao: str, id_produto: str):
    acao_normalizada = (acao or "").strip().lower()

    if acao_normalizada in ("deleted", "excluido", "excluído", "delete", "removido"):
        # Exclusão não precisa buscar nada de volta — só desativa localmente.
        produto = Produto.query.filter_by(bling_id=id_produto).first()
        if produto:
            produto.ativo = False
        return

    # Criado/atualizado: o evento não traz o produto completo, então busca
    # de volta na API e reaproveita o MESMO upsert do polling.
    p = bling_client.consultar_produto(id_produto)
    if p:
        upsert_produto(p)


def _processar_evento_estoque(id_produto: str):
    """Atualiza só o campo estoque — nunca nome/preço/categoria, mesmo
    cuidado de separação que já existe entre sync de catálogo e de estoque."""
    produto = Produto.query.filter_by(bling_id=id_produto).first()
    if produto is None:
        # Produto novo cadastrado no Bling: é comum o evento de ESTOQUE
        # ("stock.created") chegar pro produto sem que exista ainda nenhum
        # evento de "product.*" — o produto simplesmente ainda não está no
        # cache local. Sem isso, ficaria invisível no catálogo até o
        # próximo /bling/sync de catálogo (até CATALOG_CACHE_TTL_MINUTES
        # depois). Busca o produto completo — mesmo padrão já usado em
        # _processar_evento_produto — pra criar o registro local certo
        # (nome/preço/categoria), já que um evento de estoque sozinho não
        # traz esses dados.
        p = bling_client.consultar_produto(id_produto)
        if not p:
            return
        upsert_produto(p)
        produto = Produto.query.filter_by(bling_id=id_produto).first()
        if produto is None:
            return

    produto.estoque = bling_client.obter_saldo_estoque(id_produto)
