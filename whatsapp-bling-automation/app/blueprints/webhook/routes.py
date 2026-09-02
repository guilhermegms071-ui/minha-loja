"""
Dois pontos de entrada:

1. /webhook/meta      — usado SÓ se você falar direto com a Cloud API da Meta,
                         sem Evolution API no meio (setup mais simples/mais barato).
2. /webhook/evolution — usado quando a Evolution API está no meio (arquitetura
                         completa da proposta), ela reencaminha os eventos pra cá.

A máquina de estados da conversa (ConversaEstado) decide o que responder —
é o substituto do Typebot para quem optar pela versão sem essa peça extra.
"""
import hashlib
import hmac
import time

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import ConfiguracaoLoja, ConversaEstado, MensagemProcessada, Produto
from app.blueprints.webhook import sender, ai_handler
from app.services import config_service

bp = Blueprint("webhook", __name__, url_prefix="/webhook")

# Fallbacks de propósito, caso a linha de ConfiguracaoLoja exista mas o
# campo específico esteja vazio (ex: o lojista apagou o texto no painel sem
# querer) — nunca deixa a mensagem sair em branco pro cliente.
_TEXTO_SAUDACAO_FALLBACK = (
    "Olá! 👋 Bem-vindo(a)!\nO que você deseja fazer hoje?\n\n"
    "1️⃣ Comprar peças/acessórios\n"
    "2️⃣ Assistência técnica\n"
    "3️⃣ Falar com atendente\n"
    "4️⃣ Horário e endereço da loja"
)
_TEXTO_MENU_ASSISTENCIA_FALLBACK = (
    "Me conta rapidinho qual é o problema do aparelho (modelo + defeito) "
    "que já te encaminho para um técnico. 🔧"
)


# ── Meta Cloud API direto ──────────────────────────────────────────────

@bp.route("/meta", methods=["GET"])
def meta_verify():
    """A Meta chama isso uma vez, na hora que você configura o webhook no painel."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == current_app.config["META_VERIFY_TOKEN"]:
        return challenge, 200
    return "Token de verificação inválido", 403


@bp.route("/meta", methods=["POST"])
def meta_receive():
    # Assinatura HMAC (X-Hub-Signature-256) — mesmo padrão já usado em
    # bling/webhook_routes.py (_assinatura_valida) e no webhook do Chatwoot
    # (_assinatura_chatwoot_valida) logo abaixo neste arquivo: sem isso,
    # qualquer um que descubra essa URL podia forjar uma mensagem fingindo
    # ser a Meta, e o servidor processava e respondia de verdade usando
    # nosso token/número real. corpo_bruto precisa ser lido ANTES de
    # qualquer parsing — a assinatura da Meta cobre os bytes crus do corpo,
    # não o JSON já interpretado.
    corpo_bruto = request.get_data()
    assinatura = request.headers.get("X-Hub-Signature-256", "")
    segredo = current_app.config.get("META_APP_SECRET", "")

    if not _assinatura_meta_valida(corpo_bruto, assinatura, segredo):
        current_app.logger.warning("Webhook Meta recusado: assinatura ausente ou inválida")
        return jsonify({"erro": "assinatura inválida"}), 401

    data = request.get_json(force=True, silent=True) or {}
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            valor = change.get("value", {})
            for msg in valor.get("messages", []):
                id_mensagem = msg.get("id")
                telefone = msg.get("from")
                texto = (msg.get("text") or {}).get("body", "")
                if not telefone or not texto:
                    continue
                if id_mensagem and _ja_processada(id_mensagem):
                    continue
                _processar_mensagem(telefone, texto, canal="meta")
                if id_mensagem:
                    _marcar_processada(id_mensagem, canal="meta")
    return jsonify({"status": "recebido"}), 200


def _assinatura_meta_valida(corpo_bruto: bytes, assinatura_header: str, segredo: str) -> bool:
    """HMAC-SHA256 do corpo bruto usando o App Secret do app Meta, header no
    formato "sha256=<hex>" — mesmo esquema de bling/webhook_routes.py
    (_assinatura_valida), sem timestamp (diferente do Chatwoot). Sem
    META_APP_SECRET configurado, recusa por padrão — nunca aceita webhook
    sem ter como validar a origem."""
    if not segredo or not assinatura_header.startswith("sha256="):
        return False

    hash_recebido = assinatura_header.removeprefix("sha256=")
    hash_calculado = hmac.new(segredo.encode("utf-8"), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(hash_calculado, hash_recebido)


# ── Evolution API (gateway) ────────────────────────────────────────────

@bp.route("/evolution", methods=["POST"])
def evolution_receive():
    data = request.get_json(force=True, silent=True) or {}

    evento = data.get("event")
    if evento != "messages.upsert":
        return jsonify({"status": "ignorado"}), 200

    msg_data = data.get("data", {})
    id_mensagem = (msg_data.get("key", {}) or {}).get("id")
    telefone = (msg_data.get("key", {}) or {}).get("remoteJid", "").split("@")[0]
    texto = (msg_data.get("message", {}) or {}).get("conversation", "")

    if telefone and texto:
        if id_mensagem and _ja_processada(id_mensagem):
            return jsonify({"status": "duplicada, ignorada"}), 200
        _processar_mensagem(telefone, texto, canal="evolution")
        if id_mensagem:
            _marcar_processada(id_mensagem, canal="evolution")

    return jsonify({"status": "recebido"}), 200


# ── Chatwoot (resposta do agente → volta pro WhatsApp) ─────────────────

@bp.route("/chatwoot", methods=["POST"])
def chatwoot_receive():
    """Configurar em: painel do Chatwoot > Configurações > Integrações >
    Webhooks > Adicionar > URL = .../webhook/chatwoot, evento "Message
    Created". Só reage a mensagem enviada por um AGENTE (message_type
    "outgoing", sender.type "user", não privada) — ignora tudo o mais,
    inclusive pra nunca ecoar de volta a própria mensagem do cliente que a
    gente encaminhou pro Chatwoot como "incoming"."""
    corpo_bruto = request.get_data()
    assinatura = request.headers.get("X-Chatwoot-Signature", "")
    timestamp = request.headers.get("X-Chatwoot-Timestamp", "")
    segredo = current_app.config.get("CHATWOOT_WEBHOOK_SECRET", "")

    if not _assinatura_chatwoot_valida(corpo_bruto, assinatura, timestamp, segredo):
        current_app.logger.warning("Webhook Chatwoot recusado: assinatura ausente ou inválida")
        return jsonify({"erro": "assinatura inválida"}), 401

    try:
        payload = request.get_json(silent=True) or {}

        eh_mensagem_de_agente = (
            payload.get("event") == "message_created"
            and payload.get("message_type") == "outgoing"
            and not payload.get("private")
            and (payload.get("sender") or {}).get("type") == "user"
        )

        if eh_mensagem_de_agente:
            conversation_id = str((payload.get("conversation") or {}).get("id") or "")
            texto = payload.get("content") or ""

            if conversation_id and texto:
                estado = ConversaEstado.query.filter_by(
                    chatwoot_conversation_id=conversation_id
                ).first()
                if estado is None:
                    current_app.logger.warning(
                        f"Webhook Chatwoot: conversa {conversation_id} sem telefone vinculado"
                    )
                else:
                    sender.enviar_mensagem(estado.telefone, texto, canal=estado.canal)

    except Exception as e:
        # Mesmo padrão de robustez do webhook do WhatsApp e do Bling: nunca
        # deixa o processamento derrubar a resposta — loga e segue.
        current_app.logger.error(f"Erro ao processar webhook Chatwoot: {e}")

    return jsonify({"status": "recebido"}), 200


def _assinatura_chatwoot_valida(corpo_bruto: bytes, assinatura: str, timestamp: str, segredo: str) -> bool:
    """HMAC-SHA256("{timestamp}.{corpo bruto}", segredo do webhook), com o
    hash prefixado "sha256=". Também rejeita timestamp velho (>5 min), pra
    dificultar reenvio de uma chamada capturada antes (replay).

    ATENÇÃO: existe um bug conhecido e documentado no próprio repositório
    do Chatwoot (issue #13809) onde o "secret" devolvido pela API às vezes
    não bate com o hmac_token usado de verdade pra assinar — se a validação
    aqui falhar sempre mesmo com o segredo certo copiado da tela de editar
    o webhook, pode ser esse bug. Nesse caso, considere restringir o acesso
    a essa rota por rede (fw/reverse proxy) em vez de por assinatura, e me
    avise pra eu revisar."""
    if not segredo or not assinatura.startswith("sha256=") or not timestamp:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False

    mensagem = f"{timestamp}.".encode("utf-8") + corpo_bruto
    hash_calculado = hmac.new(segredo.encode("utf-8"), mensagem, hashlib.sha256).hexdigest()
    return hmac.compare_digest(hash_calculado, assinatura.removeprefix("sha256="))


def _ja_processada(id_mensagem: str) -> bool:
    return db.session.get(MensagemProcessada, id_mensagem) is not None


def _marcar_processada(id_mensagem: str, canal: str):
    db.session.add(MensagemProcessada(id_mensagem=id_mensagem, canal=canal))
    db.session.commit()


# ── Máquina de estados (substitui o Typebot) ───────────────────────────

def _processar_mensagem(telefone: str, texto: str, canal: str):
    estado = ConversaEstado.query.get(telefone)
    if estado is None:
        estado = ConversaEstado(telefone=telefone, estado="inicio", contexto={})
        db.session.add(estado)

    config = config_service.obter_configuracao()
    texto_normalizado = texto.strip().lower()

    # Guardado por conversa (não só usado na hora) porque a resposta de um
    # agente do Chatwoot chega bem depois, fora deste request — o webhook
    # /webhook/chatwoot precisa saber por qual canal reenviar pro cliente.
    estado.canal = canal

    if estado.estado == "inicio":
        resposta = config.texto_saudacao or _TEXTO_SAUDACAO_FALLBACK
        estado.estado = "menu_principal"

    elif estado.estado == "menu_principal":
        if texto_normalizado in ("1", "comprar peças", "comprar", "peças", "pecas", "acessórios"):
            link = f"{current_app.config['BASE_URL']}/loja?tel={telefone}"
            abertura = config.texto_menu_comprar or "Show!"
            resposta = (
                f"{abertura} Aqui está o link do nosso catálogo — os preços e o estoque "
                f"são atualizados automaticamente:\n\n{link}\n\n"
                "Monte seu pedido lá e, quando for finalizar, você vai ser direcionado "
                "para um de nossos atendentes para combinar o pagamento. 💳"
            )
            estado.estado = "aguardando_pedido_web"
        elif texto_normalizado in ("2", "assistência técnica", "assistencia tecnica", "assistencia", "assistência"):
            resposta = config.texto_menu_assistencia or _TEXTO_MENU_ASSISTENCIA_FALLBACK
            estado.estado = "assistencia_tecnica"
            estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
                telefone, texto, estado.chatwoot_conversation_id
            )
        elif texto_normalizado in ("3", "falar com atendente", "atendente"):
            resposta = "Encaminhando você para um atendente humano. Aguarde só um instante 🙋"
            estado.estado = "encaminhado_humano"
            estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
                telefone, texto, estado.chatwoot_conversation_id
            )
        elif texto_normalizado in ("4", "horário", "horario", "endereço", "endereco", "sobre a loja", "sobre loja"):
            # Pergunta institucional pelo atalho fixo do menu — mesma resposta
            # que a IA usa pra intenção "sobre_loja" (ver _resposta_sobre_loja),
            # nunca inventa horário/endereço que o lojista não configurou.
            resposta = _resposta_sobre_loja(config)
        elif config_service.ia_esta_habilitada():
            # Texto livre que não bateu com nenhum atalho do menu — camada de IA
            # (opcional) tenta entender a intenção antes de desistir pro menu
            # estático. Direciona pro MESMO fluxo de sempre (mesmo link de
            # catálogo, mesmo handoff pro Chatwoot) — a IA só decide QUAL desses
            # fluxos usar, nunca substitui preço/estoque/prazo, que continuam
            # vindo só do banco.
            interpretacao = ai_handler.interpretar_mensagem(texto, estado.contexto)
            intencao = interpretacao["intencao"]
            abertura = interpretacao["resposta_sugerida"]

            if intencao == "comprar_pecas":
                link = f"{current_app.config['BASE_URL']}/loja?tel={telefone}"
                abertura_compra = abertura or (config.texto_menu_comprar or "Show!")
                resposta = (
                    f"{abertura_compra} Aqui está o link do nosso catálogo — os preços e o estoque "
                    f"são atualizados automaticamente:\n\n{link}\n\n"
                    "Monte seu pedido lá e, quando for finalizar, você vai ser direcionado "
                    "para um de nossos atendentes para combinar o pagamento. 💳"
                )
                estado.estado = "aguardando_pedido_web"
            elif intencao == "assistencia_tecnica":
                corpo = config.texto_menu_assistencia or _TEXTO_MENU_ASSISTENCIA_FALLBACK
                resposta = f"{abertura}\n\n{corpo}" if abertura else corpo
                estado.estado = "assistencia_tecnica"
                estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
                    telefone, texto, estado.chatwoot_conversation_id
                )
            elif intencao == "falar_atendente":
                resposta = (
                    (f"{abertura}\n\n" if abertura else "")
                    + "Encaminhando você para um atendente humano. Aguarde só um instante 🙋"
                )
                estado.estado = "encaminhado_humano"
                estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
                    telefone, texto, estado.chatwoot_conversation_id
                )
            elif intencao == "sobre_loja":
                corpo = _resposta_sobre_loja(config)
                resposta = f"{abertura}\n\n{corpo}" if abertura else corpo
            else:
                # "fora_de_escopo"/confiança baixa caem no mesmo menu estático de
                # sempre — nunca inventamos uma resposta sem dado real por trás.
                resposta = "Não entendi. Digite 1, 2, 3 ou 4 conforme o menu acima."
        else:
            resposta = "Não entendi. Digite 1, 2, 3 ou 4 conforme o menu acima."

    elif estado.estado == "aguardando_pedido_web":
        resposta = (
            "Assim que finalizar o pedido no site, um atendente vai te chamar por aqui "
            "para combinar o pagamento. Se precisar de ajuda, digite 'atendente'."
        )
        if texto_normalizado in ("atendente", "falar com atendente"):
            estado.estado = "encaminhado_humano"
            estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
                telefone, texto, estado.chatwoot_conversation_id
            )
            resposta = "Encaminhando você para um atendente humano 🙋"

    elif estado.estado == "assistencia_tecnica":
        # A partir daqui, o Chatwoot assume a conversa — o BOT não responde
        # mais, mas a mensagem do cliente ainda precisa chegar no agente
        # humano (senão a bidirecionalidade fica só de volta, nunca de ida).
        estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
            telefone, texto, estado.chatwoot_conversation_id
        )
        db.session.commit()
        return

    elif estado.estado == "encaminhado_humano":
        estado.chatwoot_conversation_id = sender.encaminhar_para_chatwoot(
            telefone, texto, estado.chatwoot_conversation_id
        )
        db.session.commit()
        return

    else:
        estado.estado = "inicio"
        resposta = "Vamos recomeçar. Digite 'oi' para ver o menu novamente."

    # Histórico curto pra IA ter memória de curto prazo na próxima mensagem
    # dessa mesma conversa — sem isso, cada mensagem seria interpretada isolada,
    # sem contexto do que já foi dito. Não roda nos estados que já retornaram
    # antes daqui (assistencia_tecnica/encaminhado_humano) porque a partir
    # deles quem responde é o Chatwoot, não a IA.
    _registrar_historico(estado, "user", texto)
    _registrar_historico(estado, "assistant", resposta)

    db.session.commit()
    sender.enviar_mensagem(telefone, resposta, canal=canal)


def _resposta_sobre_loja(config: ConfiguracaoLoja) -> str:
    """Monta a resposta institucional (horário/endereço) a partir da
    configuração da loja — nunca inventa dado que o lojista não preencheu.
    Usada tanto pelo atalho estático '4' quanto pela intenção 'sobre_loja'
    detectada pela IA."""
    partes = []
    if config.texto_sobre_loja:
        partes.append(config.texto_sobre_loja)
    if config.horario_funcionamento:
        partes.append(f"🕐 Horário de funcionamento: {config.horario_funcionamento}")
    if config.endereco_loja:
        partes.append(f"📍 Endereço: {config.endereco_loja}")

    if not partes:
        return (
            "No momento não tenho essas informações configuradas por aqui. "
            "Digite 3 pra falar com um atendente. 🙋"
        )
    return "\n".join(partes)


def _registrar_historico(estado: ConversaEstado, papel: str, texto: str):
    """Mantém só as últimas 4 trocas (8 mensagens) em ConversaEstado.contexto —
    suficiente pra IA entender o fio da conversa, sem inflar o tamanho da
    chamada (e o custo) a cada mensagem nova.
    Reatribui o dict inteiro (em vez de só mutar uma chave dele) de propósito:
    colunas JSON não são rastreadas como mutáveis pelo SQLAlchemy por padrão,
    então `estado.contexto["historico"] = ...` não seria detectado como
    alteração e o commit não salvaria nada."""
    historico = list((estado.contexto or {}).get("historico", []))
    historico.append({"role": papel, "texto": texto})
    estado.contexto = {**(estado.contexto or {}), "historico": historico[-8:]}
