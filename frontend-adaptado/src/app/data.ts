import type { Product, Category } from "./types";

export const PRODUCTS: Product[] = [
  { id: 1,  sku: "BAT-IP11",   name: "Bateria iPhone 11 3110mAh",     category: "baterias",    price: 89.90,  inStock: true,  stockQty: 15 },
  { id: 2,  sku: "BAT-IPXR",   name: "Bateria iPhone XR 2942mAh",     category: "baterias",    price: 79.90,  inStock: true,  stockQty: 8  },
  { id: 3,  sku: "BAT-IP12",   name: "Bateria iPhone 12 2815mAh",     category: "baterias",    price: 39.90,  inStock: true,  stockQty: 22 },
  { id: 4,  sku: "BAT-SS20",   name: "Bateria Samsung S20 4000mAh",   category: "baterias",    price: 129.90, inStock: true,  stockQty: 5  },
  { id: 5,  sku: "BAT-IP13",   name: "Bateria iPhone 13 3227mAh",     category: "baterias",    price: 99.90,  inStock: false, stockQty: 0  },
  { id: 6,  sku: "BAT-IP14",   name: "Bateria iPhone 14 3279mAh",     category: "baterias",    price: 119.90, inStock: true,  stockQty: 7  },
  { id: 7,  sku: "TEL-IP11",   name: "Tela iPhone 11 (Incl. Touch)",  category: "displays",    price: 249.90, inStock: true,  stockQty: 7  },
  { id: 8,  sku: "TEL-IPXR",   name: "Tela iPhone XR OLED",           category: "displays",    price: 219.90, inStock: true,  stockQty: 4  },
  { id: 9,  sku: "TEL-SS20",   name: "Tela Samsung S20 AMOLED",       category: "displays",    price: 299.90, inStock: false, stockQty: 0  },
  { id: 10, sku: "TEL-IP12P",  name: "Tela iPhone 12 Pro",            category: "displays",    price: 349.90, inStock: true,  stockQty: 3  },
  { id: 11, sku: "TEL-MOT",    name: "Tela Motorola G60",             category: "displays",    price: 159.90, inStock: true,  stockQty: 6  },
  { id: 12, sku: "TEL-IP13",   name: "Tela iPhone 13 (Incl. Touch)",  category: "displays",    price: 289.90, inStock: true,  stockQty: 2  },
  { id: 13, sku: "CON-IP11",   name: "Conector de Carga iPhone 11",   category: "conectores",  price: 39.90,  inStock: true,  stockQty: 30 },
  { id: 14, sku: "CON-USBC",   name: "Conector USB-C Samsung Galaxy", category: "conectores",  price: 29.90,  inStock: true,  stockQty: 25 },
  { id: 15, sku: "CON-IPXR",   name: "Conector Lightning iPhone XR",  category: "conectores",  price: 34.90,  inStock: true,  stockQty: 18 },
  { id: 16, sku: "CAM-IP11T",  name: "Câmera Traseira iPhone 11",     category: "cameras",     price: 189.90, inStock: true,  stockQty: 4  },
  { id: 17, sku: "CAM-IPXRF",  name: "Câmera Frontal iPhone XR",      category: "cameras",     price: 89.90,  inStock: true,  stockQty: 9  },
  { id: 18, sku: "CAM-SS20U",  name: "Câmera Samsung S20 Ultra",      category: "cameras",     price: 249.90, inStock: false, stockQty: 0  },
  { id: 19, sku: "CAR-IP11P",  name: "Carcaça iPhone 11 Preta",       category: "carcacas",    price: 49.90,  inStock: true,  stockQty: 12 },
  { id: 20, sku: "CAR-SS20A",  name: "Carcaça Samsung S20 Azul",      category: "carcacas",    price: 44.90,  inStock: true,  stockQty: 8  },
  { id: 21, sku: "CAB-LGT1",   name: "Cabo Lightning MFi 1m",         category: "cabos",       price: 19.90,  inStock: true,  stockQty: 40 },
  { id: 22, sku: "CAB-UCC2",   name: "Cabo USB-C para USB-C 2m",      category: "cabos",       price: 24.90,  inStock: true,  stockQty: 35 },
  { id: 23, sku: "FER-PEN",    name: "Chave Pentalobe iPhone",        category: "ferramentas", price: 12.90,  inStock: true,  stockQty: 20 },
  { id: 24, sku: "FER-KIT9",   name: "Kit Ferramentas Reparo 9 pcs",  category: "ferramentas", price: 49.90,  inStock: true,  stockQty: 10 },
  { id: 25, sku: "FER-ESP",    name: "Espátula Abre Celular",         category: "ferramentas", price: 8.90,   inStock: true,  stockQty: 50 },
];

/** Deixa a primeira letra de cada palavra maiúscula — os dados de categoria
 * chegam como o lojista cadastrou no Bling (ou no seed local), às vezes tudo
 * minúsculo ("baterias"); a interface nunca deve exibir isso cru, sempre
 * capitalizado ("Baterias"), independente de como a fonte guardou o texto. */
function capitalizarPalavras(texto: string): string {
  return texto
    .split(" ")
    .map(palavra => (palavra ? palavra[0].toUpperCase() + palavra.slice(1) : palavra))
    .join(" ");
}

/** Categorias calculadas a partir dos produtos REAIS (sincronizados do
 * Bling) — nunca mais uma lista fixa no código. Se o lojista criar uma
 * categoria nova no Bling e ela sincronizar, a aba correspondente aparece
 * sozinha aqui, sem precisar de deploy. Sem produto nenhum ainda
 * sincronizado, `products` chega vazio e sobra só "Todos" — não quebra.
 * Cada categoria já vem com a contagem de produtos nela. */
export function computeCategories(products: Product[]): { id: Category; label: string; count: number }[] {
  const contagem = new Map<string, number>();
  for (const p of products) {
    contagem.set(p.category, (contagem.get(p.category) ?? 0) + 1);
  }

  const unicas = Array.from(contagem.keys()).sort((a, b) => a.localeCompare(b, "pt-BR"));

  return [
    { id: "all", label: "Todos", count: products.length },
    ...unicas.map(cat => ({ id: cat, label: capitalizarPalavras(cat), count: contagem.get(cat) ?? 0 })),
  ];
}

// Termos que, quando aparecem em CAIXA ALTA TOTAL num nome de produto vindo
// do Bling, têm uma grafia própria conhecida — não dá pra "adivinhar" isso
// só capitalizando a primeira letra (ex: "IPHONE" → "Iphone" estaria
// errado; o certo é "iPhone"). Lista pequena, com os termos mais comuns em
// nome de peça de celular; qualquer palavra em CAIXA ALTA que não estiver
// aqui cai no fallback simples (primeira letra maiúscula, resto minúsculo).
const EXCECOES_NOME_PRODUTO: Record<string, string> = {
  IPHONE: "iPhone",
  IPAD: "iPad",
  IPOD: "iPod",
  MACBOOK: "MacBook",
  "USB-C": "USB-C",
  USB: "USB",
  "WI-FI": "Wi-Fi",
  WIFI: "WiFi",
  BLUETOOTH: "Bluetooth",
  LED: "LED",
  OLED: "OLED",
  AMOLED: "AMOLED",
  LCD: "LCD",
  NFC: "NFC",
  GPS: "GPS",
  SIM: "SIM",
  MFI: "MFi",
};

/** Corrige nomes de produto vindos do Bling em CAIXA ALTA TOTAL (ex:
 * "BATERIA IPHONE") pra capitalização normal ("Bateria iPhone"). Só mexe em
 * palavras que estão INTEIRAMENTE em maiúsculas — uma palavra que já vem
 * com capitalização mista (como "iPhone" ou "USB-C" digitados certos, ou
 * um número de modelo tipo "3110mAh") não é candidata a correção e passa
 * intocada. Usa EXCECOES_NOME_PRODUTO pra termos/marcas conhecidas; fora
 * da lista, aplica só "primeira maiúscula, resto minúsculo" — não é
 * garantido cobrir toda sigla nova que apareça, mas é o fallback razoável
 * pro caso comum (ex: "SAMSUNG" → "Samsung"). */
export function normalizarNomeProduto(nome: string): string {
  return nome
    .split(" ")
    .map(palavra => {
      const temLetra = palavra !== palavra.toLowerCase() || palavra !== palavra.toUpperCase();
      const ehTotalmenteMaiuscula = temLetra && palavra === palavra.toUpperCase();
      if (!ehTotalmenteMaiuscula) return palavra; // já tem capitalização mista, ou não tem letra nenhuma — não mexe

      const excecao = EXCECOES_NOME_PRODUTO[palavra.toUpperCase()];
      if (excecao) return excecao;

      return palavra[0] + palavra.slice(1).toLowerCase();
    })
    .join(" ");
}

export const CAT_COLOR: Record<string, string> = {
  displays:    "bg-blue-50   text-blue-500",
  baterias:    "bg-emerald-50 text-emerald-600",
  conectores:  "bg-orange-50 text-orange-500",
  cameras:     "bg-purple-50 text-purple-500",
  carcacas:    "bg-slate-100 text-slate-500",
  cabos:       "bg-yellow-50 text-yellow-600",
  ferramentas: "bg-red-50    text-red-500",
  outros:      "bg-cyan-50   text-cyan-600",
};

export const FRETE = 6.00;
export const STORE_KEY = "jsvcell";
