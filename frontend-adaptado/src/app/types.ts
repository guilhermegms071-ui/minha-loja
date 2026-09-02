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
}
