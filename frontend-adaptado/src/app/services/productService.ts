// ─── Product Service ──────────────────────────────────────────────────────
// Antes: falava direto com o Bling do navegador (expondo credenciais) ou
// caía num mock local (data.ts) guardado em localStorage.
// Agora: sempre lê do backend (/api/produtos), que já lê de um cache
// sincronizado com o Bling do lado do servidor.

import { api } from "./apiService";
import { normalizarNomeProduto } from "../data";
import type { Product } from "../types";

interface ProdutoBackend {
  id: number;
  blingId: string;
  name: string;
  category: string;
  price: number;
  inStock: boolean;
  stockQty: number;
  imageUrl: string | null;
  atualizadoEm: string | null;
}

function toProduct(p: ProdutoBackend): Product {
  return {
    id: p.id,
    sku: p.blingId,
    // Normaliza aqui, na origem — o dado no Bling não é alterado, só a
    // exibição no front. Cobre todos os lugares que mostram nome de
    // produto de uma vez só (card, carrinho, checkout, confirmação),
    // sem precisar repetir a chamada em cada tela.
    name: normalizarNomeProduto(p.name),
    category: p.category || "outros",
    price: p.price,
    inStock: p.inStock,
    stockQty: p.stockQty,
    imageUrl: p.imageUrl || undefined,
    atualizadoEm: p.atualizadoEm || undefined,
  };
}

/** Busca o catálogo. `categoria` e `busca` são opcionais e filtram no servidor. */
export async function getProducts(opts?: { categoria?: string; busca?: string }): Promise<Product[]> {
  const params = new URLSearchParams();
  if (opts?.categoria && opts.categoria !== "all") params.set("categoria", opts.categoria);
  if (opts?.busca) params.set("busca", opts.busca);

  const query = params.toString() ? `?${params.toString()}` : "";
  const produtos = await api.get<ProdutoBackend[]>(`/api/produtos${query}`);
  return produtos.map(toProduct);
}

export async function getProduct(id: number): Promise<Product> {
  const produto = await api.get<ProdutoBackend>(`/api/produtos/${id}`);
  return toProduct(produto);
}
