// ─── WhatsApp Service ─────────────────────────────────────────────────────
// Antes: montava o link de pagamento inteiramente no navegador a partir do
// CONFIG.whatsapp.payment salvo em localStorage.
// Agora: o backend já devolve o link pronto (linkPagamento) na resposta de
// POST /api/pedidos, usando ATENDENTE_PAGAMENTO_TELEFONE do servidor — é a
// fonte de verdade. Isso aqui vira só um fallback, e o link do bot geral
// (que não tem dado sensível nenhum) continua vindo do CONFIG local.

import { CONFIG } from "../config";
import type { Order } from "../types";

function fmt(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function cleanNumber(num: string): string {
  return num.replace(/\D/g, "");
}

function buildPaymentMessage(order: Order): string {
  const itemLines = order.items
    .map((i) => `• ${i.qty}x ${i.product.name} — ${fmt(i.product.price * i.qty)}`)
    .join("\n");

  return [
    `Olá! Gostaria de finalizar o pagamento do pedido *${order.number}*.`,
    "",
    "*Resumo do pedido:*",
    itemLines,
    "",
    `Subtotal: ${fmt(order.subtotal)}`,
    `Frete (entrega): ${fmt(order.frete)}`,
    `*Total: ${fmt(order.total)}*`,
    "",
    `Cliente: ${order.customer.name}`,
    `WhatsApp: ${order.customer.whatsapp}`,
    "",
    "Aguardo orientações sobre o pagamento. 🙏",
  ].join("\n");
}

/**
 * Retorna o link de pagamento. Prioriza o link que o backend já mandou
 * pronto (order.linkPagamento) — só monta no navegador como fallback, caso
 * o backend não tenha ATENDENTE_PAGAMENTO_TELEFONE configurado ainda.
 */
export function getPaymentLink(order: Order & { linkPagamento?: string | null }): string {
  if (order.linkPagamento) return order.linkPagamento;

  // Fallback local — só usado se o backend não tiver o número configurado
  const number = cleanNumber(CONFIG.whatsapp.payment);
  const message = buildPaymentMessage(order);
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

/** Link wa.me para o bot geral — não envolve dado sensível, pode ficar local. */
export function getBotLink(message?: string): string {
  const number = cleanNumber(CONFIG.whatsapp.bot);
  if (message) {
    return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
  }
  return `https://wa.me/${number}`;
}

export function getPaymentAttendantLink(): string {
  const number = cleanNumber(CONFIG.whatsapp.payment);
  return `https://wa.me/${number}`;
}

export function isValidWhatsAppNumber(num: string): boolean {
  const clean = cleanNumber(num);
  return /^55\d{10,11}$/.test(clean);
}

export function formatNumber(num: string): string {
  const clean = cleanNumber(num).replace(/^55/, "");
  if (clean.length === 11) {
    return `(${clean.slice(0, 2)}) ${clean.slice(2, 7)}-${clean.slice(7)}`;
  }
  if (clean.length === 10) {
    return `(${clean.slice(0, 2)}) ${clean.slice(2, 6)}-${clean.slice(6)}`;
  }
  return num;
}
