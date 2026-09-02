# Front-end adaptado — JSV CELL

Versão do catálogo/carrinho que fala com o backend Flask
(`whatsapp-bling-automation-backend.zip`) em vez de `localStorage` + Bling
direto do navegador. Projeto original: https://www.figma.com/design/ZmThEkIILVscrVYeI6PSnm/An%C3%A1lise-de-Projeto

## Rodar

```bash
cp .env.example .env
# edite VITE_API_BASE_URL se o backend não estiver em localhost:5000

npm install
npm run dev      # http://localhost:5173
```

Precisa do backend rodando em paralelo (`python run.py` no projeto do
backend) — sem ele, o catálogo fica vazio e o checkout falha.

## O que mudou em relação ao projeto original (zip que você enviou)

| Arquivo | O que mudou |
|---|---|
| `services/apiService.ts` | **Novo.** Cliente HTTP central pro backend. |
| `services/productService.ts` | Lê `/api/produtos` em vez de Bling direto/mock local. |
| `services/orderService.ts` | Cria pedido via `/api/pedidos`; lista pedidos via `/api/admin/pedidos` (exige chave admin). |
| `services/whatsappService.ts` | Usa o `linkPagamento` pronto que o backend gera; mantém fallback local. |
| `services/customerService.ts` | Sem mudanças — só pré-preenche formulário, não é dado sensível. |
| `services/blingService.ts` | **Removido.** Credenciais do Bling não devem existir no navegador. |
| `config.ts` | Removidos `clientId`/`clientSecret` do Bling. |
| `types.ts` | Adicionado `linkPagamento?` em `Order`. |
| `App.tsx` — `AdminView` | Troca credenciais Bling por uma chave de admin (`X-Admin-Key`); sync dispara `/bling/sync` e `/bling/sync-estoque` no backend. |
| `App.tsx` — `OrdersView` | Assíncrono (antes lia `localStorage` na hora); ver limitação abaixo. |

## Limitação conhecida (não resolvida, documentada no código)

A tela "Meus pedidos" hoje pede a mesma chave de admin do painel, porque o
backend não tem conceito de "conta do cliente" — `/api/admin/pedidos` lista
**todos** os pedidos da loja. Resolver isso de verdade exige autenticação
por cliente (ex: confirmar telefone por OTP e vincular pedidos a ele), que
não estava no escopo do que foi pedido até aqui.

## Validado nesta versão

- `npm run build` completo, sem erros (1608 módulos, build de produção)
- `npm run dev` sobe sem erro
- Nenhuma referência residual a `blingService`, `CONFIG.bling` ou métodos
  removidos (`getLastSyncTime`, `syncFromBling`) — conferido por grep

## Não testado ainda (próximo passo)

- Fluxo manual no navegador (catálogo → carrinho → checkout → link de
  pagamento) rodando os dois projetos juntos — o build passa, mas isso não
  substitui clicar de verdade na interface
