// Antes: union fixa de categorias herdada do protótipo. Agora as categorias
// vêm dos produtos reais sincronizados do Bling (ver computeCategories em
// data.ts) — podem ser qualquer texto que o lojista cadastrou lá, por isso
// isso é `string`, não mais uma lista fechada. "all" é só o valor sentinela
// usado no filtro pra dizer "sem categoria selecionada".
export type Category = string;

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: Category;
  price: number;
  inStock: boolean;
  stockQty: number;
  imageUrl?: string; // preenchido quando Bling conectado
  atualizadoEm?: string; // última vez que o cache local foi sincronizado com o Bling
}

export interface CartItem {
  product: Product;
  qty: number;
}

export type PaymentMethod = "credito" | "debito" | "pix" | "dinheiro" | "entrega";

// Rótulo em português enviado ao backend (guardado e exibido como texto
// puro, sem tradução própria do lado de lá) e mostrado no seletor do
// checkout e no painel admin — um lugar só pros dois.
export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  credito: "Crédito",
  debito: "Débito",
  pix: "Pix",
  dinheiro: "Dinheiro",
  entrega: "Pagamento na entrega",
};

export interface Customer {
  name: string;
  whatsapp: string;
  cpfCnpj: string;
  cep: string;
  address: string;
  number: string;
  complement: string;
  neighborhood: string;
  city: string;
  state: string;
  // Vive aqui (não num tipo próprio) pra reaproveitar o mesmo estado/campo
  // "set()" que o resto do formulário de checkout já usa, sem reestruturar
  // nada. Pré-selecionado com "pix" (opção mais comum) — não é
  // obrigatório, só uma preferência informativa repassada ao atendente
  // que fecha o pagamento por WhatsApp; nunca bloqueia o envio do pedido.
  paymentMethod: PaymentMethod;
}

export interface Order {
  id: string;
  number: string;
  items: CartItem[];
  customer: Customer;
  subtotal: number;
  frete: number;
  total: number;
  status: "pendente" | "em_analise" | "confirmado" | "pago" | "entregue" | "cancelado";
  createdAt: string;
  blingId?: string;   // preenchido quando Bling criar o pedido no ERP
  blingOrderNum?: number; // número sequencial do pedido no Bling
  linkPagamento?: string | null; // link wa.me pronto, gerado pelo backend
  // string (não PaymentMethod) — vem já como rótulo pronto do backend (ver
  // orderService.createOrder). null/undefined em pedidos de antes desse
  // campo existir — tratado como "não informado" onde é exibido, nunca
  // como erro.
  paymentMethod?: string | null;
}
