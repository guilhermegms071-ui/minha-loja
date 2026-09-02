"""
Fake mínimo do Chatwoot — simula só as 3 chamadas que
sender.encaminhar_para_chatwoot faz (criar contato, criar conversa, enviar
mensagem), no formato de resposta confirmado na documentação oficial
(developers.chatwoot.com), pra testar o fluxo sem precisar subir o Chatwoot
de verdade (Docker) ainda.

Tudo em memória — reinicia zerado a cada execução, sem persistência.

Rodar: python scripts/chatwoot_fake.py
(sobe na porta 3000, a mesma que CHATWOOT_URL=http://localhost:3000 usa)

Rota extra /_debug/conversas (só neste fake, não existe na API real) deixa
inspecionar o que foi criado durante um teste manual.
"""
from flask import Flask, jsonify, request

app = Flask(__name__)

_contatos = {}       # identifier -> contato (dict)
_conversas = {}      # str(conversation_id) -> {"contact_id", "source_id", "inbox_id", "mensagens": [...]}
_proximo_contato_id = 1
_proximo_conversa_id = 1


@app.route("/api/v1/accounts/<account_id>/contacts", methods=["POST"])
def criar_contato(account_id):
    global _proximo_contato_id
    payload = request.get_json(force=True, silent=True) or {}
    identifier = payload.get("identifier")

    if identifier in _contatos:
        contato = _contatos[identifier]
    else:
        contato = {
            "id": _proximo_contato_id,
            "name": payload.get("name", ""),
            "identifier": identifier,
            "contact_inboxes": [
                {
                    "source_id": f"fake-source-{_proximo_contato_id}",
                    "inbox": {
                        "id": payload.get("inbox_id"),
                        "name": "Fake Inbox",
                        "channel_type": "Channel::Api",
                    },
                }
            ],
        }
        _contatos[identifier] = contato
        _proximo_contato_id += 1

    # Formato confirmado na pesquisa: resposta vem envelopada em "payload"
    # (lista) — sender.py já trata os dois formatos (lista ou objeto solto).
    return jsonify({"payload": [contato]}), 200


@app.route("/api/v1/accounts/<account_id>/conversations", methods=["POST"])
def criar_conversa(account_id):
    global _proximo_conversa_id
    payload = request.get_json(force=True, silent=True) or {}

    conversa_id = _proximo_conversa_id
    _proximo_conversa_id += 1
    _conversas[str(conversa_id)] = {
        "contact_id": payload.get("contact_id"),
        "source_id": payload.get("source_id"),
        "inbox_id": payload.get("inbox_id"),
        "mensagens": [],
    }

    return jsonify({
        "id": conversa_id,
        "inbox_id": payload.get("inbox_id"),
        "contact_id": payload.get("contact_id"),
        "status": "open",
    }), 200


@app.route("/api/v1/accounts/<account_id>/conversations/<conversation_id>/messages", methods=["POST"])
def criar_mensagem(account_id, conversation_id):
    payload = request.get_json(force=True, silent=True) or {}
    conversa = _conversas.get(conversation_id)
    if conversa is None:
        return jsonify({"error": "conversa não encontrada"}), 404

    mensagem = {
        "id": len(conversa["mensagens"]) + 1,
        "content": payload.get("content"),
        "message_type": payload.get("message_type"),
        "conversation_id": int(conversation_id),
    }
    conversa["mensagens"].append(mensagem)
    return jsonify(mensagem), 200


@app.route("/_debug/conversas")
def debug_conversas():
    return jsonify({"contatos": _contatos, "conversas": _conversas})


if __name__ == "__main__":
    app.run(port=3000, debug=False)
