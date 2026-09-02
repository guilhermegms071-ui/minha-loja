# Guia de Teste — do zero até o primeiro pedido real

Siga nesta ordem. Cada etapa só depende da anterior, nunca das seguintes —
dá pra parar em qualquer ponto e já ter algo validado.

## Etapa 1 — Backend sozinho, sem nada externo

```bash
cp .env.example .env
# edite o .env: defina ADMIN_API_KEY com um valor forte
#   (gere um com: openssl rand -hex 24)

pip install -r requirements.txt --break-system-packages
flask --app run.py db upgrade
python scripts/seed_fake_data.py     # popula 10 produtos fake
python run.py                        # sobe em http://localhost:5000
```

Confira em outro terminal:
```bash
curl http://localhost:5000/health
curl http://localhost:5000/api/produtos
curl -X POST http://localhost:5000/api/pedidos \
  -H "Content-Type: application/json" \
  -d '{"itens":[{"produtoId":1,"quantidade":1}],"cliente":{"nome":"Teste","telefone":"5511999998888"}}'
```
Se o último comando devolver `201` com um `linkPagamento`, a lógica de
pedido está funcionando de ponta a ponta — sem depender de Bling, Meta ou
WhatsApp nenhum ainda.

Teste também o bloqueio de estoque:
```bash
curl -X POST http://localhost:5000/api/pedidos \
  -H "Content-Type: application/json" \
  -d '{"itens":[{"produtoId":3,"quantidade":1}],"cliente":{"nome":"Teste","telefone":"5511999998888"}}'
# produtoId 3 = "Bateria iPhone 12" (estoque 0 no seed) — deve devolver 409
```

## Etapa 2 — Simular o WhatsApp sem WhatsApp nenhum

Antes de mexer na Meta, teste a máquina de estados do bot direto:
```bash
curl -X POST http://localhost:5000/webhook/evolution \
  -H "Content-Type: application/json" \
  -d '{"event":"messages.upsert","data":{"key":{"id":"m1","remoteJid":"5511988887777@s.whatsapp.net"},"message":{"conversation":"oi"}}}'

curl -X POST http://localhost:5000/webhook/evolution \
  -H "Content-Type: application/json" \
  -d '{"event":"messages.upsert","data":{"key":{"id":"m2","remoteJid":"5511988887777@s.whatsapp.net"},"message":{"conversation":"1"}}}'
```
A resposta vai pro log do servidor (não tem WhatsApp real ainda pra
mostrar), mas confirma que o menu avança e não quebra.

## Etapa 3 — Expor pro mundo com ngrok (teste com Meta real)

```bash
# instale o ngrok: https://ngrok.com/download
ngrok http 5000
```
Isso gera uma URL tipo `https://abc123.ngrok-free.app`. Use essa URL:
- No painel da Meta (developers.facebook.com), configure o webhook como
  `https://abc123.ngrok-free.app/webhook/meta`
- Verify Token = o mesmo valor de `META_VERIFY_TOKEN` no seu `.env`

A Meta oferece um número de teste gratuito no ambiente de desenvolvedor —
use ele primeiro, não o número real da loja. Manda mensagem de verdade pra
esse número e confirma que o menu do bot responde.

**Atenção:** toda vez que você reinicia o ngrok grátis, a URL muda — você
precisa reconfigurar no painel da Meta. É normal, é só ambiente de teste.

## Etapa 4 — Bling, com conta de teste

Repita o fluxo OAuth2 com uma conta Bling separada (trial, não a de
produção), cadastre 2-3 produtos fake nela, e valide:
```bash
# abra no navegador (troque a porta se estiver usando ngrok):
http://localhost:5000/bling/authorize
```
Depois de autorizar, sincronize e confira:
```bash
curl -X POST http://localhost:5000/bling/sync -H "X-Admin-Key: SUA_CHAVE"
curl -X POST http://localhost:5000/bling/sync-estoque -H "X-Admin-Key: SUA_CHAVE"
curl http://localhost:5000/api/produtos
```
Se os produtos da conta de teste aparecerem certos aqui, a integração real
está validada — só falta trocar as credenciais pela conta de produção.

## Etapa 5 — Painel admin

```bash
curl http://localhost:5000/api/admin/pedidos -H "X-Admin-Key: SUA_CHAVE"
curl http://localhost:5000/api/admin/resumo -H "X-Admin-Key: SUA_CHAVE"
```
Confirme que os pedidos de teste das etapas anteriores aparecem aqui —
essa é a visão que você vai usar no dia a dia pra saber o que precisa de
atenção (pedidos com `status: falhou_bling`, por exemplo).

## Checklist antes de trocar o número real da loja

- [ ] Backend rodando num VPS de verdade (não mais localhost/ngrok), com
      domínio próprio e HTTPS válido
- [ ] `ADMIN_API_KEY` forte, diferente da usada em teste
- [ ] Catálogo sincronizando com a conta Bling **real** (não mais fake/teste)
- [ ] Pelo menos 5 pedidos de teste completos, incluindo 1 caso de estoque
      insuficiente e 1 caso de falha proposital no Bling (ex: autorização
      revogada), pra confirmar que o sistema não quebra
- [ ] `ATENDENTE_PAGAMENTO_TELEFONE` configurado com o número certo — teste
      recebendo o `linkPagamento` de verdade nesse número
- [ ] Rodou pelo menos 2-3 dias com o número de teste da Meta antes de
      migrar pro número real da loja
