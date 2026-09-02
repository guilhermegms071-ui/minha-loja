"""
Configurações da loja editáveis pelo lojista pelo painel admin, sem precisar
mexer em código nem reiniciar o servidor — ver ConfiguracaoLoja em
app/models.py.

Regra de fallback (só vale pros dois campos que JÁ existiam como variável
de ambiente antes dessa tabela existir — atendente_pagamento_telefone e
ia_habilitada): enquanto o lojista nunca configurou o campo pelo painel
(fica vazio/None), o valor do .env continua valendo, pra não quebrar quem
já estava rodando configurado só por variável de ambiente. Depois que o
lojista mexe no painel, o valor salvo aqui manda — ver obter_telefone_atendente
e ia_esta_habilitada abaixo.

Os textos do menu (saudação, opção "comprar", opção "assistência") NÃO têm
equivalente no .env — eram texto puro já hardcoded no código. Pra esses, o
valor "padrão" já é escrito direto no banco na primeira vez que a
configuração é criada, usando o mesmo texto que já existia — assim o
comportamento no primeiro deploy dessa feature fica idêntico ao de antes
(a única mudança de conteúdo é a adição da opção "4" ao menu, pedida
explicitamente nesta tarefa)."""
from flask import current_app

from app.extensions import db
from app.models import ConfiguracaoLoja

# Mesmo texto que já estava hardcoded em webhook/routes.py — usado só na
# criação da primeira linha, pra não mudar nada do que já funcionava.
# Única mudança de conteúdo real: acrescenta a opção "4" (pergunta
# institucional), pedida nesta tarefa.
_TEXTO_SAUDACAO_PADRAO = (
    "Olá! 👋 Bem-vindo(a)!\nO que você deseja fazer hoje?\n\n"
    "1️⃣ Comprar peças/acessórios\n"
    "2️⃣ Assistência técnica\n"
    "3️⃣ Falar com atendente\n"
    "4️⃣ Horário e endereço da loja"
)
_TEXTO_MENU_COMPRAR_PADRAO = "Show!"  # só a abertura — o link do catálogo é sempre montado no código, nunca estático
_TEXTO_MENU_ASSISTENCIA_PADRAO = (
    "Para assistência técnica, me conta rapidinho qual é o problema do "
    "aparelho (modelo + defeito) que já te encaminho para um técnico. 🔧"
)


def obter_configuracao() -> ConfiguracaoLoja:
    """Retorna a linha única de configuração da loja, criando com valores
    padrão sensatos na primeira vez que for chamada — nunca deixa a
    ausência de configuração quebrar uma rota."""
    config = db.session.get(ConfiguracaoLoja, 1)
    if config is None:
        config = ConfiguracaoLoja(
            id=1,
            texto_saudacao=_TEXTO_SAUDACAO_PADRAO,
            texto_menu_comprar=_TEXTO_MENU_COMPRAR_PADRAO,
            texto_menu_assistencia=_TEXTO_MENU_ASSISTENCIA_PADRAO,
            texto_sobre_loja="",  # sem equivalente prévio — fica em branco até o lojista preencher
            horario_funcionamento="",
            endereco_loja="",
            atendente_pagamento_telefone="",  # vazio de propósito: cai pro .env (ver obter_telefone_atendente)
            ia_habilitada=None,  # None de propósito: cai pro .env (ver ia_esta_habilitada)
            pedido_minimo=0,
            desconto_padrao_percentual=0,
        )
        db.session.add(config)
        db.session.commit()
    return config


def obter_telefone_atendente() -> str:
    """Telefone do atendente que recebe o link de pagamento. Prioridade:
    valor configurado pelo lojista no painel > ATENDENTE_PAGAMENTO_TELEFONE
    do .env (fallback, só usado enquanto o lojista nunca configurou isso
    pelo painel)."""
    config = obter_configuracao()
    if config.atendente_pagamento_telefone:
        return config.atendente_pagamento_telefone
    return current_app.config.get("ATENDENTE_PAGAMENTO_TELEFONE", "") or ""


def ia_esta_habilitada() -> bool:
    """Liga/desliga a camada de IA no WhatsApp. Prioridade: toggle
    configurado pelo lojista no painel (True ou False explícitos) >
    AI_ENABLED do .env (fallback, só usado enquanto o campo no painel
    continua None, ou seja, o lojista nunca mexeu nele)."""
    config = obter_configuracao()
    if config.ia_habilitada is not None:
        return bool(config.ia_habilitada)
    return bool(current_app.config.get("AI_ENABLED"))
