"""
Camada de INTERPRETAÇÃO por linguagem natural, opcional, por cima do menu
numérico rígido do webhook (mesmo padrão de plataformas tipo Anota AI: a IA
só entende a intenção do texto livre do cliente, quem decide o que responder
de verdade continua sendo o código — catálogo, estoque e preço nunca passam
pela IA).

Regra de ouro: a IA classifica intenção e sugere uma frase curta de
acompanhamento — ela NUNCA gera preço, estoque, prazo ou qualquer dado real
de produto. Esses dados sempre vêm do banco (tabela Produto), nunca do texto
que a IA escreve.
"""
import json

import anthropic
from flask import current_app

from app.services import config_service

# Precisa bater com as categorias descritas no prompt de sistema abaixo —
# qualquer coisa fora disso (ou vinda malformada da IA) é tratada como
# "fora_de_escopo", que por sua vez cai no menu estático de fallback.
CATEGORIAS_VALIDAS = {
    "comprar_pecas",
    "assistencia_tecnica",
    "falar_atendente",
    "sobre_loja",
    "fora_de_escopo",
}

# Abaixo disso, preferimos o menu estático a arriscar uma classificação
# duvidosa — errar a intenção do cliente é pior do que perguntar de novo.
CONFIANCA_MINIMA = 0.6

# Timeout curto de propósito: isso roda dentro do webhook, sincronamente,
# enquanto o cliente espera resposta no WhatsApp. Sem retry automático aqui
# (max_retries=0) — numa falha transitória, preferimos cair no fallback na
# hora a fazer o cliente esperar o dobro do timeout por uma segunda tentativa.
TIMEOUT_SEGUNDOS = 8.0

SYSTEM_PROMPT = """Você é o classificador de intenção do atendimento automático de uma loja de peças e assistência técnica de celulares.

Sua ÚNICA tarefa é ler a mensagem do cliente e classificar a intenção dele. Você NUNCA deve informar preço, estoque, prazo de entrega ou qualquer outro dado real de produto — isso não está disponível pra você e sempre vem do sistema da loja, nunca da sua resposta.

Categorias possíveis (escolha exatamente uma):
- comprar_pecas: cliente quer comprar uma peça, acessório ou produto (bateria, tela, capinha, carregador, etc.), ou está perguntando sobre o catálogo/produtos em geral.
- assistencia_tecnica: cliente tem um aparelho com defeito e quer conserto/reparo/assistência técnica.
- falar_atendente: cliente pede explicitamente para falar com um humano/atendente, ou está claramente insatisfeito/frustrado com o bot.
- sobre_loja: pergunta institucional sobre a loja (horário de funcionamento, endereço, formas de pagamento aceitas, etc.) — não sobre um produto específico.
- fora_de_escopo: qualquer outro assunto, incluindo papo aleatório, spam, ou algo sem relação com a loja.

Responda SOMENTE com um JSON válido, sem markdown, sem texto antes ou depois, exatamente neste formato:
{"intencao": "<uma das categorias acima>", "resposta_sugerida": "<frase curta, natural e amigável de acompanhamento, em português, SEM inventar preço/estoque/prazo>", "confianca": <número entre 0 e 1>}
"""


def interpretar_mensagem(texto: str, contexto: dict) -> dict:
    """Classifica a intenção de uma mensagem livre do WhatsApp usando Claude.

    Sempre retorna um dict {"intencao", "resposta_sugerida", "confianca"} —
    nunca lança exceção pra quem chama. Qualquer problema (IA desligada,
    timeout, erro de rede, resposta mal formada, confiança baixa) volta como
    intencao="fora_de_escopo"/confianca=0.0, que é o sinal pra quem chamou
    (routes.py) cair no menu estático — o mesmo padrão de robustez já usado
    nas chamadas ao Bling: falha de IA nunca derruba o webhook.
    """
    cfg = current_app.config
    # Prioridade: toggle configurado pelo lojista no painel > AI_ENABLED do
    # .env (fallback) — ver app/services/config_service.py. O gate em
    # webhook/routes.py usa a MESMA função, pra nunca ter duas fontes de
    # verdade divergentes sobre se a IA está ligada ou não.
    if not config_service.ia_esta_habilitada():
        return _sem_ia()

    # Histórico curto (últimas trocas já salvas em ConversaEstado.contexto)
    # dá memória de curto prazo pra IA sem reenviar a conversa inteira a
    # cada mensagem — mantém o custo por chamada baixo e prevísivel.
    historico = (contexto or {}).get("historico", [])[-8:]
    mensagens = [{"role": item["role"], "content": item["texto"]} for item in historico]
    mensagens.append({"role": "user", "content": texto})

    try:
        client = anthropic.Anthropic(api_key=cfg["AI_API_KEY"])
        resposta = client.with_options(timeout=TIMEOUT_SEGUNDOS, max_retries=0).messages.create(
            model=cfg["AI_MODEL"],
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=mensagens,
        )

        bloco_texto = next((b.text for b in resposta.content if b.type == "text"), "")
        dados = json.loads(_limpar_possivel_markdown(bloco_texto))

        intencao = dados.get("intencao")
        confianca = float(dados.get("confianca", 0))
        resposta_sugerida = str(dados.get("resposta_sugerida", "")).strip()

        if intencao not in CATEGORIAS_VALIDAS or confianca < CONFIANCA_MINIMA:
            return _sem_ia()

        return {
            "intencao": intencao,
            "resposta_sugerida": resposta_sugerida,
            "confianca": confianca,
        }

    except Exception as e:
        # Captura ampla de propósito: timeout, erro de rede, chave inválida,
        # rate limit, JSON mal formado da IA, campo faltando etc. — nenhum
        # desses deve derrubar o webhook. Só loga e cai no fallback.
        current_app.logger.error(f"Falha ao interpretar mensagem via IA: {e}")
        return _sem_ia()


def _limpar_possivel_markdown(texto: str) -> str:
    """Claude às vezes envolve o JSON em ```json ... ``` mesmo quando o
    prompt pede pra não fazer isso — remove esse invólucro antes do parse."""
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.strip("`")
        if limpo.lower().startswith("json"):
            limpo = limpo[4:]
    return limpo.strip()


def _sem_ia() -> dict:
    """Sinal padrão de 'não use a IA aqui' — confiança 0 e intenção
    fora_de_escopo, que routes.py já trata como 'cai no menu estático'."""
    return {"intencao": "fora_de_escopo", "resposta_sugerida": "", "confianca": 0.0}
