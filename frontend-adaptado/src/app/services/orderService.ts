// ─── Order Service ────────────────────────────────────────────────────────
// Antes: fonte de verdade era localStorage (isolado por navegador), com
// "sucesso" retornado mesmo se a criação no Bling falhasse.
// Agora: fonte de verdade é o backend. O pedido não existe até o backend
// confirmar, e o status reflete o que realmente aconteceu no Bling.

import { api } from "./apiService";
import * as customerService from "./customerService";
import type { Order, CartItem, Customer } from "../types";

interface PedidoBackend {
  id: number;
  numero: string;
  status: "aguardando_bling" | "criado_bling" | "falhou_bling" | "cancelado" | "pago";
  erroBling: string | null;
  subtotal: number;
  frete: number;
  total: number;
  blingPedidoId: string | null;
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
    },
  };

  const pedido = await api.post<PedidoBackend>("/api/pedidos", payload);

  // Salva dados do cliente localmente só para pré-preencher o próximo pedido
  // (isso é uma conveniência de UI, não a fonte de verdade do pedido)
  customerService.saveCustomer(customer);

  const order = toOrder(pedido, items, customer);
  return { ...order, linkPagamento: pedido.linkPagamento };
}

/** Lista pedidos — usado no painel admin. Requer a chave de admin. */
export async function getOrders(adminKey: string): Promise<Order[]> {
  const pedidos = await api.get<
    {
      id: number; numero: string; status: PedidoBackend["status"]; erroBling: string | null;
      blingPedidoId: string | null; total: number; cliente: string; criadoEm: string;
    }[]
  >("/api/admin/pedidos", { "X-Admin-Key": adminKey });

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
  }));
}

/** Lista os pedidos de UM telefone específico — usado pela tela "Meus
 * pedidos" do próprio cliente. Rota pública (sem chave de admin); ver a
 * limitação de segurança documentada no backend em cart/routes.py — não é
 * autenticação de verdade, só filtragem por telefone. */
export async function getOrdersByPhone(telefone: string): Promise<Order[]> {
  const pedidos = await api.get<PedidoBackend[]>(
    `/api/pedidos/por-telefone?telefone=${encodeURIComponent(telefone)}`
  );
  return pedidos.map((p) =>
    toOrder(p, [], { name: p.cliente.nome, whatsapp: p.cliente.telefone } as Customer)
  );
}

export interface OrderSummary {
  total: number;
  count: number;
  pending: number;
  revenue: number;
  avgTicket: number;
}

/** Resumo para o painel admin. Requer a chave de admin. */
export async function getOrderSummary(adminKey: string): Promise<OrderSummary> {
  const resumo = await api.get<{
    totalPedidos: number;
    faturamento: number;
    pendentesBling: number;
    ticketMedio: number;
  }>("/api/admin/resumo", { "X-Admin-Key": adminKey });

  return {
    total: resumo.totalPedidos,
    count: resumo.totalPedidos,
    pending: resumo.pendentesBling,
    revenue: resumo.faturamento,
    avgTicket: resumo.ticketMedio,
  };
}

/** Reprocessa um pedido que falhou ao criar no Bling. */
export async function retryBling(orderId: string): Promise<void> {
  await api.post(`/api/pedidos/${orderId}/retentar-bling`);
}

/** Botão "Marcar como pago" do painel admin — usado quando o atendente
 * confirma manualmente pelo WhatsApp que o cliente pagou (não há gateway
 * de pagamento aqui). Avança a situação do pedido no Bling, o que dispara
 * a baixa de estoque nativa de lá. Requer o pedido já ter sido criado no
 * Bling (blingId preenchido) — o backend recusa se não tiver. */
export async function marcarComoPago(orderId: string, adminKey: string): Promise<void> {
  await api.post(`/api/pedidos/${orderId}/marcar-pago`, undefined, { "X-Admin-Key": adminKey });
}
