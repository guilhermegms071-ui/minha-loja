# Backend — Automação WhatsApp + Catálogo + Bling

Substitui a lógica que estava no front-end React (`blingService.ts`,
`orderService.ts`, `productService.ts`) por uma API real. O front deixa de
falar direto com o Bling (o que expunha `clientSecret` no navegador) e passa
a falar com este backend.

## Setup rápido (dev local, sem Docker)

```bash
cp .env.example .env          # preencha as credenciais que já tiver
pip install -r requirements.txt --break-system-packages
flask --app run.py db upgrade # aplica as migrações reais (Alembic)
python run.py                 # sobe em http://localhost:5000
```

## Painel admin protegido

Toda rota `/api/admin/*` e `/bling/sync*` exige o header `X-Admin-Key` com o
valor de `ADMIN_API_KEY` do `.env`. Gere um valor forte antes de ir pra
produção (ex: `openssl rand -hex 24`). **Sem essa chave configurada, o
servidor bloqueia essas rotas por padrão** — nunca fica aberto por esquecimento.

## Setup completo (com Evolution API, Typebot, Chatwoot)

```bash
cp .env.example .env
docker compose up -d
docker compose exec web flask --app run.py db upgrade
```

## Fluxo real implementado (sua loja)

1. Cliente manda mensagem → bot pergunta intenção (menu: comprar peças /
   assistência técnica / falar com atendente)
2. **Comprar peças** → bot manda link do catálogo (lido do cache local,
   nunca do Bling em tempo real) → cliente monta o pedido no site
3. Ao confirmar, `/api/pedidos` cria o pedido, tenta lançar no Bling, e
   **sempre** devolve um `linkPagamento` (`wa.me` já com o resumo do pedido
   preenchido) pro número do funcionário configurado em
   `ATENDENTE_PAGAMENTO_TELEFONE` — é ali que o pagamento é fechado
4. **Assistência técnica** ou **falar com atendente** → encaminha direto
   pro Chatwoot (fila humana), sem passar pelo catálogo

## Rotas principais

| Rota | Método | O que faz |
|---|---|---|
| `/bling/authorize` | GET | Inicia o OAuth2 do Bling (abrir no navegador) |
| `/bling/callback` | GET | Recebe o retorno do Bling (configurar como Redirect URI no app Bling) |
| `/bling/status` | GET | Diz se o Bling está autorizado |
| `/bling/sync` 🔒 | POST | Sincroniza catálogo (nome/preço/categoria) — roda sozinho a cada `CATALOG_CACHE_TTL_MINUTES` |
| `/bling/sync-estoque` 🔒 | POST | Sincroniza SÓ o saldo de estoque dos produtos já cadastrados — roda sozinho a cada `STOCK_SYNC_INTERVAL_MINUTES` (ciclo mais curto, separado do catálogo) |
| `/api/produtos` | GET | Catálogo (cache local) — usar `?categoria=` e `?busca=` |
| `/api/pedidos` | POST | Cria pedido — valida preço no servidor, devolve `linkPagamento` pronto |
| `/api/pedidos/<id>` | GET | Detalhe de um pedido |
| `/api/pedidos/<id>/retentar-bling` | POST | Reprocessa um pedido que falhou ao criar no Bling |
| `/api/admin/pedidos` 🔒 | GET | Lista todos os pedidos (painel do lojista) |
| `/api/admin/resumo` 🔒 | GET | Faturamento, ticket médio, pendências no Bling |
| `/webhook/meta` | GET/POST | Webhook direto da Meta Cloud API |
| `/webhook/evolution` | POST | Webhook vindo da Evolution API |

🔒 = exige header `X-Admin-Key`

## O que foi corrigido em relação ao protótipo React analisado

1. **`clientSecret`/`access_token` do Bling nunca tocam o navegador** — só existem
   no backend (`app/blueprints/bling/client.py`).
2. **Pedido nunca é "sucesso" mentiroso.** Se a criação no Bling falhar, o pedido
   fica salvo com `status: falhou_bling` e `erroBling` preenchido — visível pro
   lojista via `/api/admin/pedidos`, com endpoint de retry manual.
3. **Preço do pedido é recalculado no servidor** a partir do cache local, nunca
   aceito cru do que o front mandou.
4. **Catálogo nunca é buscado do Bling na hora que um cliente acessa o site** —
   só lê do cache local (`Produto`), que é sincronizado por job periódico.
5. **Webhook + máquina de estados reais** (`app/blueprints/webhook/`), que não
   existiam no protótipo — é o que faltava pra fechar a arquitetura da proposta.

## Ainda falta (próximos passos, não fiz sozinho por decisão sua)

- Adaptar o front React do zip (`Análise_de_Projeto`) para chamar estas rotas
  em vez de `localStorage` + Bling direto — isso não fiz porque envolve
  reescrever os componentes visuais, uma decisão de UI que é sua.
- Preencher `BLING_CLIENT_ID`/`BLING_CLIENT_SECRET`/`ADMIN_API_KEY`/
  `ATENDENTE_PAGAMENTO_TELEFONE` reais no `.env` quando tiver acesso ao Bling
  e ao WhatsApp Business — até lá, o sistema roda normalmente em modo "Bling
  desautorizado" (pedidos ficam com `status: falhou_bling` até você autorizar).

## O que foi resolvido nesta rodada

1. **Sincronização de estoque separada da de catálogo** (`/bling/sync-estoque`),
   em lote de até 40 produtos por chamada, ciclo próprio mais curto — não
   estoura o rate limit do Bling nem mistura responsabilidades.
2. **Painel admin protegido por chave** (`X-Admin-Key`) — bloqueado por padrão
   se a chave não estiver configurada, nunca aberto por esquecimento.
3. **Migrações reais via Alembic** (`migrations/versions/`) — não é mais
   `db.create_all()`; `flask db upgrade` aplica o schema de forma versionada
   e reproduzível.
4. **Menu do bot ajustado ao seu fluxo real**: comprar peças / assistência
   técnica / falar com atendente — em vez do "solicitar orçamento" genérico
   da proposta original.
5. **Link de pagamento automático** (`linkPagamento` na resposta de
   `POST /api/pedidos`) — fecha o fluxo "bot cuida do catálogo, humano só
   fecha o pagamento" que você descreveu.
6. **Robustez de rede corrigida**: se a Evolution API, Meta ou Chatwoot
   estiverem fora do ar no momento de responder o cliente, o webhook não
   quebra mais com erro 500 — loga o erro e segue (achei isso testando de
   verdade, não estava nos planos originais).
