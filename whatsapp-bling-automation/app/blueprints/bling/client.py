"""
Cliente HTTP para a API v3 do Bling.

Responsabilidades:
- Trocar 'code' por tokens (fluxo OAuth2 Authorization Code)
- Renovar access_token automaticamente via refresh_token
- Expor métodos de alto nível: listar_produtos, buscar_ou_criar_contato, criar_pedido_venda

Erros da API do Bling (4xx/5xx, rate limit) são propagados como BlingAPIError
para quem chamar tratar explicitamente — nunca falhar silenciosamente aqui.
"""
import re
from datetime import datetime, timedelta

import requests
from flask import current_app

from app.extensions import db
from app.models import BlingToken


class BlingAPIError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def get_authorize_url(state: str) -> str:
    cfg = current_app.config
    return (
        "https://bling.com.br/Api/v3/oauth/authorize"
        f"?response_type=code&client_id={cfg['BLING_CLIENT_ID']}&state={state}"
    )


def exchange_code_for_token(code: str) -> BlingToken:
    cfg = current_app.config
    resp = requests.post(
        f"{cfg['BLING_OAUTH_BASE']}/oauth/token",
        auth=(cfg["BLING_CLIENT_ID"], cfg["BLING_CLIENT_SECRET"]),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["BLING_REDIRECT_URI"],
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise BlingAPIError("Falha ao trocar code por token", resp.status_code, resp.text)

    data = resp.json()
    return _save_tokens(data)


def _save_tokens(data: dict) -> BlingToken:
    token = BlingToken.query.get(1)
    if token is None:
        token = BlingToken(id=1)
        db.session.add(token)

    token.access_token = data["access_token"]
    token.refresh_token = data["refresh_token"]
    token.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 21600))
    db.session.commit()
    return token


def _refresh_token(token: BlingToken) -> BlingToken:
    cfg = current_app.config
    resp = requests.post(
        f"{cfg['BLING_OAUTH_BASE']}/oauth/token",
        auth=(cfg["BLING_CLIENT_ID"], cfg["BLING_CLIENT_SECRET"]),
        data={"grant_type": "refresh_token", "refresh_token": token.refresh_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise BlingAPIError("Falha ao renovar token do Bling", resp.status_code, resp.text)
    return _save_tokens(resp.json())


def _get_valid_token() -> str:
    token = BlingToken.query.get(1)
    if token is None:
        raise BlingAPIError("Bling ainda não foi autorizado. Acesse /bling/authorize primeiro.")

    # renova com folga de 2 minutos antes de expirar
    if token.expires_at <= datetime.utcnow() + timedelta(minutes=2):
        token = _refresh_token(token)

    return token.access_token


def _request(method: str, path: str, **kwargs) -> dict:
    cfg = current_app.config
    access_token = _get_valid_token()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"

    try:
        resp = requests.request(
            method, f"{cfg['BLING_API_BASE']}{path}", headers=headers, timeout=20, **kwargs
        )
    except requests.exceptions.RequestException as e:
        # Falha de CONEXÃO (timeout, DNS, Bling fora do ar) — sem isso, essa
        # exceção escapava sem virar BlingAPIError, quem chamou (ex:
        # _tentar_criar_no_bling) não sabia capturá-la, e o pedido ficava
        # travado pra sempre em "aguardando_bling" em vez de "falhou_bling"
        # com um motivo visível pro lojista.
        raise BlingAPIError(f"Falha de conexão com a Bling em {path}: {e}") from e

    if resp.status_code == 429:
        raise BlingAPIError("Rate limit do Bling atingido — tente novamente em instantes", 429)
    if resp.status_code >= 400:
        raise BlingAPIError(f"Erro Bling {resp.status_code} em {path}", resp.status_code, resp.text)

    return resp.json() if resp.text else {}


# ── Endpoints de alto nível ──────────────────────────────────────

def listar_produtos(pagina: int = 1, limite: int = 100) -> list[dict]:
    data = _request("GET", "/produtos", params={"pagina": pagina, "limite": limite})
    return data.get("data", [])


def consultar_produto(id_produto: str) -> dict:
    """Busca um produto específico por ID — usado pelo webhook em tempo real,
    que só recebe o ID do produto no evento (não os dados completos, ver
    bling/webhook_routes.py). Antes de usar isso, o webhook chama isso pra
    buscar o produto de novo e então reaproveita o mesmo upsert_produto()
    já usado pelo polling.

    ATENÇÃO: o path exato desse endpoint (GET /produtos/{id}) segue a
    convenção REST já confirmada em outros recursos desta mesma API (ex:
    GET/PATCH /pedidos/vendas/{id}) — não foi possível confirmar batendo
    direto na documentação oficial, porque a página de referência é
    renderizada via JavaScript e fica inacessível pra raspagem automática.
    Se isso devolver 404 num produto que existe de verdade, é sinal de que
    o path precisa ser ajustado — nesse caso o erro só é logado (o webhook
    sempre responde 200) e o próximo /bling/sync por polling corrige."""
    data = _request("GET", f"/produtos/{id_produto}")
    return data.get("data", data)


def obter_saldo_estoque(id_produto: str) -> int:
    data = _request("GET", "/estoques/saldos", params={"idsProdutos[]": id_produto})
    itens = data.get("data", [])
    if not itens:
        return 0
    saldos = itens[0].get("saldoFisicoTotal", 0)
    return int(saldos)


def obter_saldos_estoque_lote(ids_produtos: list[str]) -> dict[str, int]:
    """Consulta estoque de vários produtos numa única chamada.
    O Bling aceita múltiplos IDs no mesmo parâmetro repetido (idsProdutos[]=1&idsProdutos[]=2...).
    Divide em lotes de 40 para não estourar limite de URL/rate limit."""
    resultado: dict[str, int] = {}

    for lote in _dividir_em_lotes(ids_produtos, 40):
        params = [("idsProdutos[]", pid) for pid in lote]
        data = _request("GET", "/estoques/saldos", params=params)
        for item in data.get("data", []):
            produto_id = str(item.get("produto", {}).get("id", ""))
            if produto_id:
                resultado[produto_id] = int(item.get("saldoFisicoTotal", 0))

    return resultado


def _dividir_em_lotes(itens: list, tamanho: int) -> list[list]:
    return [itens[i:i + tamanho] for i in range(0, len(itens), tamanho)]


def _normalizar_telefone_br(telefone: str) -> str:
    """Normaliza telefone brasileiro pro formato que a Bling aceita no
    cadastro de contato: só dígitos, DDD + número, SEM código do país.

    Descoberto na prática: a Bling recusa o contato ('É necessário
    preencher corretamente o campo Telefone') quando o telefone vem com o
    "55" de código do país na frente — mas é exatamente assim que o
    telefone chega aqui, porque vem do WhatsApp (Meta/Evolution), que usa
    formato internacional com "55" incluso. Prática padrão em integrações
    Brasil → ERP (documentado por diversos guias de normalização de
    telefone e confirmado testando contra a própria Bling nesta sessão):
    tirar o "55" e qualquer formatação (parênteses, traço, espaço) antes
    de mandar pro ERP.

    Isso NÃO mexe no telefone guardado em Cliente.telefone/ConversaEstado
    (usado como chave de busca em todo o resto da aplicação) — só no valor
    que sai no payload pra Bling, aqui e em buscar_contato_por_telefone.

    Só remove o "55" quando sobra um total de 12 ou 13 dígitos (55 + DDD +
    8/9 dígitos) — nunca em números já com 10 ou 11 dígitos, pra não
    confundir com um DDD legítimo que começa com 55 (região do Rio Grande
    do Sul, ex: Santa Maria)."""
    apenas_digitos = re.sub(r"\D", "", telefone or "")

    if apenas_digitos.startswith("55") and len(apenas_digitos) in (12, 13):
        return apenas_digitos[2:]

    return apenas_digitos


def buscar_contato_por_telefone(telefone: str) -> dict | None:
    data = _request("GET", "/contatos", params={"pesquisa": _normalizar_telefone_br(telefone)})
    resultados = data.get("data", [])
    return resultados[0] if resultados else None


def criar_contato(nome: str, telefone: str, email: str = "") -> dict:
    payload = {
        "nome": nome,
        "telefone": _normalizar_telefone_br(telefone),
        "email": email,
        "tipo": "F",  # pessoa física
        "situacao": "A",  # ativo — campo obrigatório pra Bling validar o contato
    }
    data = _request("POST", "/contatos", json=payload)
    return data.get("data", {})


def listar_modulos() -> list[dict]:
    """Lista os módulos do sistema Bling (Pedido de Venda, Pedido de Compra etc).
    Passo 1 pra descobrir o idSituacao de 'Atendido' — os IDs de situação não
    são fixos, variam por conta Bling, então isso precisa ser consultado."""
    data = _request("GET", "/situacoes/modulos")
    return data.get("data", [])


def listar_situacoes_modulo(id_modulo_sistema: str) -> list[dict]:
    """Lista as situações disponíveis de um módulo (ex: as situações possíveis
    de um Pedido de Venda: Em aberto, Atendido, Cancelado...). Passo 2 —
    usa o id do módulo obtido em listar_modulos()."""
    data = _request("GET", f"/situacoes/modulos/{id_modulo_sistema}")
    return data.get("data", [])


def alterar_situacao_pedido(id_pedido_venda: str, id_situacao: str) -> None:
    """Avança a situação de um pedido de venda no Bling (ex: de 'Em aberto' pra
    'Atendido') — é isso que dispara a baixa de estoque nativa do Bling.
    Endpoint retorna 204 sem corpo em sucesso; erros vêm como BlingAPIError,
    tratados normalmente por _request."""
    _request("PATCH", f"/pedidos/vendas/{id_pedido_venda}/situacoes/{id_situacao}")


def criar_pedido_venda(cliente_bling_id: str, itens: list[dict], observacoes: str = "") -> dict:
    """
    itens: [{"produto_bling_id": "123", "quantidade": 1, "preco_unitario": 89.90}, ...]
    """
    payload = {
        "contato": {"id": cliente_bling_id},
        "data": datetime.now().strftime("%Y-%m-%d"),  # obrigatório pra Bling gerar as parcelas
        "itens": [
            {
                "produto": {"id": item["produto_bling_id"]},
                "quantidade": item["quantidade"],
                "valor": float(item["preco_unitario"]),
            }
            for item in itens
        ],
        "observacoes": observacoes,
    }
    data = _request("POST", "/pedidos/vendas", json=payload)
    return data.get("data", {})
