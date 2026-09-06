// ─── Order Service ────────────────────────────────────────────────────────
// Antes: fonte de verdade era localStorage (isolado por navegador), com
// "sucesso" retornado mesmo se a criação no Bling falhasse.
// Agora: fonte de verdade é o backend. O pedido não existe até o backend
// confirmar, e o status reflete o que realmente aconteceu no Bling.

import { api } from "./apiService";
import * as customerService from "./customerService";
import type { Order, CartItem, Customer, PaymentMethod } from "../types";
import { PAYMENT_METHOD_LABELS } from "../types";

/** Endereço de entrega formatado numa linha só — é assim que ele chega no
 * backend (campo endereco_entrega, ver models.py) e depois na mensagem de
 * resumo mandada pro atendente. Monta aqui, um lugar só, pra não repetir
 * a mesma concatenação em outro service no futuro. */
function formatarEndereco(c: Customer): string {
  const partes = [
    `${c.address}${c.number ? `, ${c.number}` : ""}${c.complement ? ` - ${c.complement}` : ""}`,
    c.neighborhood,
    c.city && c.state ? `${c.city}/${c.state}` : c.city || c.state,
    c.cep,
  ].filter(Boolean);
  return partes.join(" - ");
}

interface PedidoBackend {
  id: number;
  numero: string;
  status: "aguardando_bling" | "criado_bling" | "falhou_bling" | "cancelado" | "pago";
  erroBling: string | null;
  subtotal: number;
  frete: number;
  total: number;
  blingPedidoId: string | null;
  formaPagamento?: string | null;
  criadoEm: string;
  cliente: { nome: string; telefone: string };
  itens: { produtoId: number; nome: string; quantidade: number; precoUnitario: number }[];
  linkPagamento?: string | null;
}

function statusToFrontend(status: PedidoBackend["status"]): Order["status"] {
  switch (status) {
    case "criado_bling":
      return "confirmado";
    case "pago":
      return "pago"; // atendente confirmou pagamento via WhatsApp — baixa de estoque já disparada no Bling
    case "falhou_bling":
      return "pendente"; // visível no painel admin como algo que precisa de atenção
    case "cancelado":
      return "cancelado";
    default:
      return "em_analise";
  }
}

function toOrder(p: PedidoBackend, items: CartItem[], customer: Customer): Order {
  return {
    id: String(p.id),
    number: p.numero,
    items,
    customer,
    subtotal: p.subtotal,
    frete: p.frete,
    total: p.total,
    status: statusToFrontend(p.status),
    createdAt: p.criadoEm,
    blingId: p.blingPedidoId || undefined,
    paymentMethod: p.formaPagamento,
  };
}

/** Cria o pedido no backend. Nunca retorna "sucesso" se o Bling falhar —
 * o pedido é criado de qualquer forma (fica salvo), mas o status reflete
 * a realidade. O link de pagamento pronto vem junto na resposta. */
export async function createOrder(
  items: CartItem[],
  customer: Customer
): Promise<Order & { linkPagamento?: string | null }> {
  const payload = {
    itens: items.map((i) => ({ produtoId: i.product.id, quantidade: i.qty })),
    cliente: {
      nome: customer.name,
      telefone: customer.whatsapp,
      email: "",
      endereco: formatarEndereco(customer),
    },
    formaPagamento: PAYMENT_METHOD_LABELS[customer.paymentMethod],
  };

  const pedido = await api.post<PedidoBackend>("/api/pedidos", payload);

  // Salva dados do cliente localmente só para pré-preencher o próximo pedido
  // (isso é uma conveniência de UI, não a fonte de verdade do pedido)
  customerService.saveCustomer(customer);

  const order = toOrder(pedido, items, customer);
  return { ...order, linkPagamento: pedido.linkPagamento };
}

/** Venda balcão — funcionário registrando venda presencial no painel admin,
 * SEM os dados de entrega que o checkout normal exige (nome/telefone
 * viram opcionais no backend, ver cart/routes.py, só quando vendaBalcao
 * for true). Rota PRÓPRIA do admin (POST /api/admin/venda-balcao, exige
 * sessão de login) — diferente de POST /api/pedidos (que continua público,
 * sem login, só pro checkout do cliente final). As duas chamam a MESMA
 * função de criação de pedido no backend (criar_pedido), então validação
 * de estoque, cálculo de preço e integração com o Bling continuam
 * idênticos — nada duplicado, só a rota (e a autenticação) é outra. */
export async function criarVendaBalcao(
  itens: { produtoId: number; quantidade: number }[],
  metodoPagamento: PaymentMethod
): Promise<Order> {
  const payload = {
    vendaBalcao: true,
    itens,
    formaPagamento: PAYMENT_METHOD_LABELS[metodoPagamento],
  };
  const pedido = await api.post<PedidoBackend>("/api/admin/venda-balcao", payload, undefined, "include");
  return toOrder(pedido, [], { name: pedido.cliente.nome, whatsapp: pedido.cliente.telefone } as Customer);
}

/** Lista pedidos — usado no painel admin. Autenticado por sessão (cookie do
 * login, ver authService.ts). */
export async function getOrders(): Promise<Order[]> {
  const pedidos = await api.get<
    {
      id: number; numero: string; status: PedidoBackend["status"]; erroBling: string | null;
      blingPedidoId: string | null; formaPagamento?: string | null;
      total: number; cliente: string; criadoEm: string;
    }[]
  >("/api/admin/pedidos", undefined, "include");

  return pedidos.map((p) => ({
    id: String(p.id),
    number: p.numero,
    items: [],
    customer: { name: p.cliente } as Customer,
    subtotal: p.total,
    frete: 0,
    total: p.total,
    status: statusToFrontend(p.status),
    createdAt: p.criadoEm,
    blingId: p.blingPedidoId || undefined,
    paymentMethod: p.formaPagamento,
  }));
}

export interface OrderSummary {
  total: number;
  count: number;
  pending: number;
  revenue: number;
  avgTicket: number;
}

/** Resumo para o painel admin. Autenticado por sessão. */
export async function getOrderSummary(): Promise<OrderSummary> {
  const resumo = await api.get<{
    totalPedidos: number;
    faturamento: number;
    pendentesBling: number;
    ticketMedio: number;
  }>("/api/admin/resumo", undefined, "include");

  return {
    total: resumo.totalPedidos,
    count: resumo.totalPedidos,
    pending: resumo.pendentesBling,
    revenue: resumo.faturamento,
    avgTicket: resumo.ticketMedio,
  };
}

/** Reprocessa um pedido que falhou ao criar no Bling. Autenticado por
 * sessão — antes desta tarefa essa rota não exigia NENHUMA autenticação
 * (bug de segurança real: qualquer um de fora podia chamar e disparar
 * tentativa de criação de venda no Bling repetidamente). */
export async function retryBling(orderId: string): Promise<void> {
  await api.post(`/api/pedidos/${orderId}/retentar-bling`, undefined, undefined, "include");
}

/** Botão "Marcar como pago" do painel admin — usado quando o atendente
 * confirma manualmente pelo WhatsApp que o cliente pagou (não há gateway
 * de pagamento aqui). Avança a situação do pedido no Bling, o que dispara
 * a baixa de estoque nativa de lá. Requer o pedido já ter sido criado no
 * Bling (blingId preenchido) — o backend recusa se não tiver. Autenticado
 * por sessão. */
export async function marcarComoPago(orderId: string): Promise<void> {
  await api.post(`/api/pedidos/${orderId}/marcar-pago`, undefined, undefined, "include");
}
