// ─── Customer Service ─────────────────────────────────────────────────────────
// Persiste dados do cliente em localStorage para pre-fill no próximo pedido.

import type { Customer } from "../types";

const KEY = "jsvcell_customer";

export function emptyCustomer(): Customer {
  return {
    name: "", whatsapp: "", cpfCnpj: "",
    cep: "", address: "", number: "",
    complement: "", neighborhood: "", city: "", state: "",
  };
}

export function getCustomer(): Customer {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...emptyCustomer(), ...JSON.parse(raw) } : emptyCustomer();
  } catch {
    return emptyCustomer();
  }
}

export function saveCustomer(customer: Customer) {
  localStorage.setItem(KEY, JSON.stringify(customer));
}

export function clearCustomer() {
  localStorage.removeItem(KEY);
}
