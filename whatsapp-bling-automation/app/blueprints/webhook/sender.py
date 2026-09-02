"""Envia mensagens de volta pro cliente e faz o handoff bot → humano."""
import requests
from flask import current_app


def enviar_mensagem(telefone: str, texto: str, canal: str = "evolution"):
    if canal == "meta":
        _enviar_via_meta(telefone, texto)
    else:
        _enviar_via_evolution(telefone, texto)


def _enviar_via_meta(telefone: str, texto: str):
    cfg = current_app.config
    url = f"https://graph.facebook.com/v20.0/{cfg['META_PHONE_NUMBER_ID']}/messages"
    headers = {"Authorization": f"Bearer {cfg['META_ACCESS_TOKEN']}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": texto},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code >= 400:
            current_app.logger.error(f"Falha ao enviar via Meta: {resp.status_code} {resp.text}")
    except requests.exceptions.RequestException as e:
        # Nunca deixa uma falha de rede (Meta fora do ar, DNS, timeout) derrubar
        # o webhook — a mudança de estado da conversa já foi salva no banco antes
        # desta chamada; a mensagem de resposta é que não chegou, e isso é logado.
        current_app.logger.error(f"Erro de conexão ao enviar via Meta: {e}")


def _enviar_via_evolution(telefone: str, texto: str):
    cfg = current_app.config
    url = f"{cfg['EVOLUTION_API_URL']}/message/sendText/{cfg['EVOLUTION_INSTANCE_NAME']}"
    headers = {"apikey": cfg["EVOLUTION_API_KEY"]}
    payload = {"number": telefone, "text": texto}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code >= 400:
            current_app.logger.error(f"Falha ao enviar via Evolution: {resp.status_code} {resp.text}")
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Erro de conexão ao enviar via Evolution: {e}")


def _chatwoot_base_url() -> str:
    cfg = current_app.config
    return f"{cfg['CHATWOOT_URL']}/api/v1/accounts/{cfg['CHATWOOT_ACCOUNT_ID']}"


def _chatwoot_headers() -> dict:
    return {"api_access_token": current_app.config["CHATWOOT_API_TOKEN"]}


def encaminhar_para_chatwoot(telefone: str, texto: str, conversation_id: str | None) -> str | None:
    """Encaminha uma mensagem do cliente pro Chatwoot (fila de atendimento
    humano), via API Channel (fluxo: criar contato → criar conversa → enviar
    mensagem). Se `conversation_id` já existir (conversa escalada antes,
    guardado em ConversaEstado.chatwoot_conversation_id), só posta a
    mensagem nela em vez de criar contato/conversa de novo a cada mensagem.

    Retorna o conversation_id (novo, se acabou de criar; ou o mesmo recebido)
    pra quem chamar guardar em ConversaEstado — nunca lança exceção: falha
    de configuração ou de rede é logada e devolve o conversation_id como
    estava antes, sem travar o webhook do WhatsApp."""
    cfg = current_app.config
    if not cfg.get("CHATWOOT_API_TOKEN") or not cfg.get("CHATWOOT_ACCOUNT_ID") or not cfg.get("CHATWOOT_INBOX_ID"):
        current_app.logger.warning("Chatwoot não configurado (falta URL/token/conta/inbox) — handoff ignorado")
        return conversation_id

    if not conversation_id:
        conversation_id = _criar_contato_e_conversa_chatwoot(telefone)
        if conversation_id is None:
            return None

    _enviar_mensagem_chatwoot(conversation_id, texto, tipo="incoming")
    return conversation_id


def _criar_contato_e_conversa_chatwoot(telefone: str) -> str | None:
    """Cria o contato (identificado pelo telefone) e a conversa associada no
    Inbox tipo API do Chatwoot. Não envia phone_number formatado — os
    telefones aqui vêm em formatos inconsistentes (com/sem código de país,
    dependendo do canal), e um phone_number mal formatado pode fazer o
    Chatwoot rejeitar a criação do contato inteira; `identifier` (que não
    tem exigência de formato) já é suficiente pra identificar o contato de
    forma única."""
    base = _chatwoot_base_url()
    headers = _chatwoot_headers()

    try:
        resp_contato = requests.post(
            f"{base}/contacts",
            headers=headers,
            json={
                "inbox_id": int(current_app.config["CHATWOOT_INBOX_ID"]),
                "name": telefone,
                "identifier": telefone,
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Erro de conexão ao criar contato no Chatwoot: {e}")
        return None

    if resp_contato.status_code >= 400:
        current_app.logger.error(f"Falha ao criar contato no Chatwoot: {resp_contato.status_code} {resp_contato.text}")
        return None

    dados_contato = resp_contato.json()
    contato = (dados_contato.get("payload") or dados_contato)
    if isinstance(contato, list):
        contato = contato[0] if contato else {}
    contact_id = contato.get("id")
    contact_inboxes = contato.get("contact_inboxes") or []

    if not contact_id or not contact_inboxes:
        current_app.logger.error(f"Resposta inesperada do Chatwoot ao criar contato: {dados_contato}")
        return None

    source_id = contact_inboxes[0]["source_id"]

    try:
        resp_conversa = requests.post(
            f"{base}/conversations",
            headers=headers,
            json={
                "source_id": source_id,
                "inbox_id": int(current_app.config["CHATWOOT_INBOX_ID"]),
                "contact_id": contact_id,
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Erro de conexão ao criar conversa no Chatwoot: {e}")
        return None

    if resp_conversa.status_code >= 400:
        current_app.logger.error(f"Falha ao criar conversa no Chatwoot: {resp_conversa.status_code} {resp_conversa.text}")
        return None

    return str(resp_conversa.json()["id"])


def _enviar_mensagem_chatwoot(conversation_id: str, texto: str, tipo: str = "incoming"):
    """tipo='incoming' pra mensagem do cliente (o normal aqui, já que quem
    manda mensagem de agente é o próprio Chatwoot, não a gente)."""
    base = _chatwoot_base_url()
    try:
        resp = requests.post(
            f"{base}/conversations/{conversation_id}/messages",
            headers=_chatwoot_headers(),
            json={"content": texto, "message_type": tipo},
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Erro de conexão ao enviar mensagem pro Chatwoot: {e}")
        return

    if resp.status_code >= 400:
        current_app.logger.error(f"Falha ao enviar mensagem pro Chatwoot: {resp.status_code} {resp.text}")
