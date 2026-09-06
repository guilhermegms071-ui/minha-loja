import { useState, useMemo, useEffect, useCallback, useRef, cloneElement } from "react";
import {
  BrowserRouter, Routes, Route, Link, Navigate, Outlet,
  useNavigate, useLocation, useOutletContext,
} from "react-router";
import { Toaster, toast } from "sonner";
import {
  Search, ShoppingCart, User, Menu, X,
  Minus, Plus, Trash2, Check, ChevronRight, ArrowLeft,
  Shield, Package, Smartphone, Zap, Plug, Camera,
  Wrench, Box, ClipboardList, Settings, AlertCircle,
  CheckCircle2, Eye, EyeOff, ExternalLink, Info,
  MapPin, Phone, FileText, RefreshCw,
  MessageCircle, Clock, TrendingUp, BarChart2, Wallet,
} from "lucide-react";

import type { Product, CartItem, Customer, Order, Category, PaymentMethod } from "./types";
import { PAYMENT_METHOD_LABELS } from "./types";
import { computeCategories, CAT_COLOR, FRETE } from "./data";
import { CONFIG, updateConfig } from "./config";
import { api, ApiError } from "./services/apiService";
import * as productService from "./services/productService";
import * as orderService   from "./services/orderService";
import * as configService  from "./services/configService";
import * as customerService from "./services/customerService";
import * as whatsappService from "./services/whatsappService";
import * as authService from "./services/authService";

// ─── Contexto compartilhado entre as páginas públicas (carrinho etc.) ──────────
// Rotas agora são URLs de verdade (react-router) em vez de um estado interno
// de "view" — o carrinho precisa sobreviver à navegação entre elas, e como o
// PublicLayout continua montado (só o <Outlet/> troca), ele guarda o estado
// do carrinho e repassa via contexto de rota, em vez de prop-drilling manual
// por cada página.
interface PublicContext {
  items: CartItem[];
  add: (p: Product) => void;
  setQty: (id: number, qty: number) => void;
  remove: (id: number) => void;
  clear: () => void;
  count: number;
  mobileMenu: boolean;
  setMobileMenu: (v: boolean) => void;
  // Busca e categoria ativa também moram aqui (não só dentro da página do
  // catálogo) porque agora o cabeçalho (Header, renderizado fora do
  // <Outlet/>, em toda página pública) precisa ler/escrever os MESMOS
  // valores que a página de catálogo usa pra filtrar — sem isso, a busca e
  // o botão "Categorias" do cabeçalho não teriam como afetar o catálogo.
  search: string;
  setSearch: (v: string) => void;
  activeCategory: Category;
  setActiveCategory: (c: Category) => void;
}

// ─── Utils ────────────────────────────────────────────────────────────────────

const R = (n: number) =>
  n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Mostra um toast de erro pra chamadas autenticadas do painel admin. Erros
 * 401 (chave errada/vazia) usam um ID fixo de toast — se mais de uma seção
 * do painel falhar quase ao mesmo tempo pela mesma causa (chave inválida),
 * o sonner atualiza o MESMO toast em vez de empilhar um novo por chamada. */
function mostrarErroAdmin(e: unknown, mensagemPadrao: string) {
  const mensagem = e instanceof Error ? e.message : mensagemPadrao;
  const ehAutenticacao = e instanceof ApiError && e.status === 401;
  toast.error(mensagem, ehAutenticacao ? { id: "admin-auth-error" } : undefined);
}

const CAT_ICON: Record<string, JSX.Element> = {
  displays:    <Smartphone size={28} />,
  baterias:    <Zap size={28} />,
  conectores:  <Plug size={28} />,
  cameras:     <Camera size={28} />,
  carcacas:    <Box size={28} />,
  cabos:       <Package size={28} />,
  ferramentas: <Wrench size={28} />,
  outros:      <Box size={28} />,
};

// ─── Hooks ────────────────────────────────────────────────────────────────────

function useCart() {
  const [items, setItems] = useState<CartItem[]>(() => {
    try { return JSON.parse(localStorage.getItem("jsvcell_cart") ?? "[]"); }
    catch { return []; }
  });

  useEffect(() => {
    localStorage.setItem("jsvcell_cart", JSON.stringify(items));
  }, [items]);

  const add = useCallback((product: Product) => {
    setItems(prev => {
      const found = prev.find(i => i.product.id === product.id);
      const next  = found
        ? prev.map(i => i.product.id === product.id ? { ...i, qty: i.qty + 1 } : i)
        : [...prev, { product, qty: 1 }];
      toast.success(`${product.name.split(" ").slice(0, 3).join(" ")} adicionado`, {
        duration: 1800,
      });
      return next;
    });
  }, []);

  const setQty = useCallback((id: number, qty: number) => {
    if (qty <= 0) setItems(prev => prev.filter(i => i.product.id !== id));
    else setItems(prev => prev.map(i => i.product.id === id ? { ...i, qty } : i));
  }, []);

  const remove = useCallback((id: number) => {
    setItems(prev => prev.filter(i => i.product.id !== id));
    toast.info("Item removido do carrinho", { duration: 1500 });
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const count    = items.reduce((s, i) => s + i.qty, 0);
  const subtotal = items.reduce((s, i) => s + i.product.price * i.qty, 0);

  return { items, add, setQty, remove, clear, count, subtotal };
}

// ─── Logo ─────────────────────────────────────────────────────────────────────

// Logo real da marca (arquivo em public/assets/ — ver instruções de troca
// no relatório desta tarefa). "compact" é usado só no topo da gaveta de
// categorias no mobile (espaço menor); no cabeçalho normal usa o tamanho
// cheio. Vinda de public/, funciona igual em qualquer rota (não passa pelo
// bundler, é servida como arquivo estático — cai em /assets/logo.svg tanto
// em dev quanto no build de produção).
function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <img src="/assets/logo.png" alt="JSV CELL" draggable={false}
      className={`select-none ${compact ? "h-8" : "h-9 sm:h-10"} w-auto`} />
  );
}

// ─── Header ───────────────────────────────────────────────────────────────────

function Header({ cartCount, onMenuClick }: {
  cartCount: number; onMenuClick: () => void;
}) {
  // Header simplificado pra só 3 elementos (pedido explícito desta tarefa):
  // hambúrguer à esquerda, logo centralizada, carrinho à direita. A busca
  // saiu daqui — agora vive só dentro da própria página do catálogo (ver
  // CatalogView), num card branco full-width, como pedido; "Categorias" e
  // "Minha conta" saíram do header (categorias agora são chips sempre
  // visíveis na página, e a tela de "Minha conta"/pedidos por telefone foi
  // removida nesta mesma tarefa — ver relatório). onMenuClick continua
  // chamando exatamente a mesma função de antes (abre a gaveta de
  // categorias no mobile, ver CategorySidebar) — não mudei o que ela faz,
  // só tirei os outros itens ao redor dela.
  return (
    <header className="bg-brand text-white sticky top-0 z-50 shadow-lg">
      {/* grid de 3 colunas (não flex) — só assim a coluna do meio (a logo)
          fica de verdade centralizada no header inteiro, mesmo os dois
          lados tendo larguras diferentes de conteúdo. */}
      <div className="max-w-7xl mx-auto px-4 py-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center">
          <button className="md:hidden text-white/70 hover:text-white transition-colors" onClick={onMenuClick} aria-label="Abrir categorias">
            <Menu size={22} />
          </button>
        </div>

        <Logo />

        <div className="flex items-center justify-end">
          <Link to="/carrinho" className="relative text-white/80 hover:text-white transition-colors" aria-label="Carrinho">
            <ShoppingCart size={22} />
            {cartCount > 0 && (
              <span className="absolute -top-2 -right-2.5 bg-green-500 text-white text-[9px] rounded-full w-[18px] h-[18px] flex items-center justify-center font-bold">
                {cartCount}
              </span>
            )}
          </Link>
        </div>
      </div>
    </header>
  );
}

// ─── Category Sidebar ─────────────────────────────────────────────────────────

function CategorySidebar({ categories, active, onChange, mobileOpen, onClose }: {
  categories: { id: Category; label: string; count: number }[];
  active: Category; onChange: (c: Category) => void;
  mobileOpen: boolean; onClose: () => void;
}) {
  const nav = (
    <nav className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {categories.map(cat => (
        <button key={cat.id} onClick={() => { onChange(cat.id); onClose(); }}
          className={`w-full text-left px-4 py-2.5 text-sm transition-all border-l-[3px] flex items-center justify-between gap-2 ${
            active === cat.id
              ? "border-l-green-600 bg-green-50 text-green-700 font-bold"
              : "border-l-transparent text-gray-600 hover:bg-gray-50 hover:text-gray-900"
          }`}>
          <span>{cat.label}</span>
          <span className="text-xs text-gray-400">({cat.count})</span>
        </button>
      ))}
    </nav>
  );

  // O <aside> vertical de desktop que existia aqui foi removido — as
  // categorias em chips horizontais (ver CatalogView) substituem a lista
  // vertical em TODAS as telas agora, pedido explícito desta tarefa. Esse
  // componente virou só a gaveta mobile (mesma lógica/estado de antes,
  // hambúrguer do header continua abrindo exatamente isso, sem mudança).
  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={onClose} />
          <div className="relative z-10 w-64 bg-white h-full shadow-2xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-4 border-b border-gray-100 bg-brand">
              <Logo compact />
              <button onClick={onClose} className="text-white/60 hover:text-white"><X size={20} /></button>
            </div>
            <div className="flex-1 overflow-y-auto py-2">{nav}</div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Product Skeleton ─────────────────────────────────────────────────────────

function ProductSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-pulse">
      <div className="h-36 bg-gray-100" />
      <div className="p-3.5 space-y-2.5">
        <div className="h-3.5 bg-gray-100 rounded w-4/5" />
        <div className="h-3.5 bg-gray-100 rounded w-3/5" />
        <div className="h-3 bg-gray-100 rounded w-2/5" />
        <div className="h-8 bg-gray-100 rounded mt-3" />
      </div>
    </div>
  );
}

// ─── Product Card ─────────────────────────────────────────────────────────────

function ProductCard({ product, onAdd, inCart }: {
  product: Product; onAdd: () => void; inCart: boolean;
}) {
  const color = CAT_COLOR[product.category] ?? "bg-gray-50 text-gray-400";
  const icon  = CAT_ICON[product.category]  ?? <Box size={28} />;
  // Ícone reduzido só aqui (não no CAT_ICON compartilhado, que também é
  // usado na miniatura do carrinho) — no placeholder de 144px de altura
  // (h-36) do card, o ícone original de 28px ocupava espaço demais sem
  // agregar informação; cloneElement troca só o tamanho, sem duplicar a
  // definição do ícone por categoria.
  const iconePlaceholder = cloneElement(icon, { size: 20 });

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 flex flex-col group">
      <div className={`h-36 flex items-center justify-center ${color} relative overflow-hidden`}>
        {product.imageUrl ? (
          <img src={product.imageUrl} alt={product.name}
            className="w-full h-full object-contain p-2" />
        ) : (
          <div className="opacity-60 group-hover:opacity-90 transition-opacity">{iconePlaceholder}</div>
        )}
        {inCart && (
          <span className="absolute top-2 right-2 bg-green-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">
            No carrinho
          </span>
        )}
      </div>

      <div className="p-3.5 flex flex-col flex-1 gap-1.5">
        {/* Preço é o elemento mais forte do card (maior + mais peso); nome
            vira secundário (menor peso, cor mais suave) — mesmo texto, só
            hierarquia visual invertida em relação ao que era antes (os dois
            tinham peso parecido). */}
        <p className="text-sm font-medium text-gray-500 leading-snug line-clamp-2 min-h-[2.5rem]">
          {product.name}
        </p>
        <p className="text-lg font-bold text-gray-900">{R(product.price)}</p>

        {/* Etiqueta de estoque — 2 estados só (pedido explícito desta
            tarefa, no lugar dos 3 estados que existiam antes: "Em estoque"
            verde / "Últimas unidades" laranja / "Fora de estoque" cinza).
            Usa o MESMO campo product.inStock que já vinha do Bling, sem
            nenhuma lógica nova — só a etiqueta/cor mudou. */}
        <p className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${
          product.inStock ? "bg-green-50 text-green-700" : "bg-[#fee2e2] text-[#b91c1c]"
        }`}>
          {product.inStock
            ? <><Check size={11} strokeWidth={3} className="shrink-0" /> Em estoque</>
            : <><Clock size={11} strokeWidth={3} className="shrink-0" /> Sob encomenda</>}
        </p>

        {/* min-h-11 (44px) garante área de toque mínima recomendada em
            mobile; md:min-h-0 desfaz esse piso a partir de 768px, mantendo
            o botão exatamente como era no desktop (só padding/py-2 define
            a altura lá, sem imposição de mínimo). */}
        <button disabled={!product.inStock} onClick={onAdd}
          className={`mt-auto min-h-11 md:min-h-0 flex items-center justify-center text-sm font-bold py-2 rounded-lg transition-colors ${
            !product.inStock
              ? "bg-gray-100 text-gray-400 cursor-not-allowed"
              : "bg-brand hover:bg-brand-dark active:bg-brand-dark text-white"
          }`}>
          Adicionar
        </button>
      </div>
    </div>
  );
}

// ─── Catalog View ─────────────────────────────────────────────────────────────

function CatalogView({ cart, onAdd, activeCategory, setActiveCategory, mobileMenuOpen, setMobileMenuOpen, search, setSearch }: {
  cart: CartItem[]; onAdd: (p: Product) => void;
  activeCategory: Category; setActiveCategory: (c: Category) => void;
  mobileMenuOpen: boolean; setMobileMenuOpen: (v: boolean) => void;
  // Busca agora vem de fora (PublicContext) em vez de estado local — é o
  // MESMO valor que o campo de busca do cabeçalho (Header) lê/escreve, pra
  // digitar em qualquer um dos dois filtrar o catálogo igual.
  search: string; setSearch: (v: string) => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading,  setLoading ] = useState(true);
  const [sortBy,   setSortBy  ] = useState<"relevancia" | "preco-asc" | "preco-desc" | "nome-asc">("relevancia");

  useEffect(() => {
    setLoading(true);
    productService.getProducts()
      .then(setProducts)
      .catch(() => toast.error("Erro ao carregar produtos"))
      .finally(() => setLoading(false));
  }, []);

  // Categorias vêm dos produtos REAIS carregados, nunca de uma lista fixa —
  // se o Bling sincronizar uma categoria nova, ela aparece aqui sozinha.
  // Sem produto nenhum ainda (loading ou catálogo vazio), sobra só "Todos".
  const categories = useMemo(() => computeCategories(products), [products]);

  const filtered = useMemo(() => {
    let list = activeCategory === "all" ? products : products.filter(p => p.category === activeCategory);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(p => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q));
    }

    if (sortBy === "preco-asc")  list = [...list].sort((a, b) => a.price - b.price);
    if (sortBy === "preco-desc") list = [...list].sort((a, b) => b.price - a.price);
    if (sortBy === "nome-asc")   list = [...list].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));

    return list;
  }, [products, activeCategory, search, sortBy]);

  const categoryLabel = categories.find(c => c.id === activeCategory)?.label ?? "Produtos";

  return (
    <>
      {/* Gaveta de categorias mobile — mesma lógica/estado de sempre
          (hambúrguer do header abre isso); virou só isso agora que a
          sidebar vertical de desktop foi removida do próprio componente
          (ver CategorySidebar) — as chips logo abaixo são a via principal
          de trocar categoria em qualquer tamanho de tela. */}
      <CategorySidebar categories={categories} active={activeCategory} onChange={setActiveCategory}
        mobileOpen={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />

      {/* Busca — full-width, card branco, agora em TODAS as telas (antes só
          existia essa versão no mobile, escondida no desktop; o cabeçalho
          também tinha uma cópia própria só pra desktop — removida, ver
          relatório desta tarefa). Mesmo estado (search/setSearch) e mesma
          lógica de filtro de sempre, só virou visível sempre e ganhou o
          estilo de card. */}
      <div className="flex items-center bg-white rounded-xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
        {/* text-base (16px) — abaixo disso o Safari no iOS dá zoom automático
            ao focar o campo; md:text-sm volta ao tamanho normal no desktop. */}
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar produtos..."
          className="flex-1 px-4 py-3 text-base md:text-sm text-gray-800 outline-none" />
        <Search size={18} className="mr-4 text-gray-400 shrink-0" />
      </div>

      {/* Categorias em chips horizontais roláveis — substitui a lista
          vertical (sidebar) que existia antes em desktop; chama a MESMA
          função de filtro (setActiveCategory) de sempre, só o visual/
          estrutura do seletor mudou. Em todas as telas agora, não só mobile. */}
      <div className="flex gap-2 overflow-x-auto pb-1 mb-4 -mx-1 px-1">
        {categories.map(cat => (
          <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
            className={`shrink-0 px-4 py-2 rounded-full text-sm font-semibold whitespace-nowrap border transition-colors ${
              activeCategory === cat.id
                ? "bg-brand border-brand text-white"
                : "bg-white border-gray-200 text-gray-600 hover:border-brand/40 hover:text-brand"
            }`}>
            {cat.label} ({cat.count})
          </button>
        ))}
      </div>

      {/* Breadcrumb — só faz sentido mostrar quando uma categoria
          específica está ativa (em "Todos" seria redundante). */}
      {activeCategory !== "all" && (
        <p className="text-xs text-gray-400 mb-2">
          Catálogo <ChevronRight size={11} className="inline mx-0.5 -mt-0.5" /> {categoryLabel}
        </p>
      )}

      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h2 className="text-lg font-bold text-gray-800">{categoryLabel}</h2>
        {!loading && (
          <span className="text-xs text-gray-400">
            {filtered.length} produto{filtered.length !== 1 ? "s" : ""}
          </span>
        )}
        <select value={sortBy} onChange={e => setSortBy(e.target.value as typeof sortBy)}
          className="ml-auto text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 outline-none focus:border-green-500 bg-white">
          <option value="relevancia">Relevância</option>
          <option value="preco-asc">Menor preço</option>
          <option value="preco-desc">Maior preço</option>
          <option value="nome-asc">Nome (A-Z)</option>
        </select>
      </div>

      {/* Grid: 2 colunas no mobile, 4 no desktop — pedido explícito desta
          tarefa (antes eram 4 passos: 1/2/3/4 colunas conforme a largura).
          Skeleton usa a MESMA grid do resultado carregado, pra não ter
          salto de layout. */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <ProductSkeleton key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Package size={40} className="text-gray-300" />
          <p className="text-gray-400 font-medium text-sm">
            {search
              ? "Nenhum produto encontrado pra essa busca"
              : activeCategory === "all"
                ? "Nenhum produto disponível no momento"
                : "Nenhum produto disponível nesta categoria no momento"}
          </p>
          {search && (
            <button onClick={() => setSearch("")}
              className="text-green-600 text-sm font-semibold hover:text-green-700">
              Limpar busca
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {filtered.map(product => (
            <ProductCard key={product.id} product={product}
              onAdd={() => onAdd(product)}
              inCart={cart.some(i => i.product.id === product.id)} />
          ))}
        </div>
      )}
    </>
  );
}

// ─── Cart View ────────────────────────────────────────────────────────────────

function CartView({ items, setQty, remove, onCheckout, onBack }: {
  items: CartItem[]; setQty: (id: number, qty: number) => void;
  remove: (id: number) => void; onCheckout: () => void; onBack: () => void;
}) {
  const subtotal = items.reduce((s, i) => s + i.product.price * i.qty, 0);
  const total    = subtotal + FRETE;

  if (items.length === 0) return (
    <div className="flex flex-col items-center justify-center gap-4 py-24">
      <ShoppingCart size={52} className="text-gray-200" />
      <p className="text-gray-400 text-lg font-medium">Seu carrinho está vazio</p>
      <button onClick={onBack}
        className="text-green-600 hover:text-green-700 text-sm font-semibold flex items-center gap-1.5">
        <ArrowLeft size={15} /> Continuar comprando
      </button>
    </div>
  );

  return (
    <div>
      <button onClick={onBack}
        className="text-green-600 hover:text-green-700 flex items-center gap-1.5 text-sm font-semibold mb-5">
        <ArrowLeft size={15} /> Continuar comprando
      </button>
      <h2 className="text-xl font-bold text-gray-900 mb-5">
        Meu carrinho ({items.reduce((s, i) => s + i.qty, 0)} itens)
      </h2>

      <div className="flex flex-col lg:flex-row gap-5">
        <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="hidden md:grid grid-cols-[2fr_1fr_auto_1fr_auto] gap-4 px-5 py-3 bg-gray-50 border-b border-gray-100">
            {["Produto","Preço","Qtd","Subtotal","Ações"].map(h => (
              <span key={h} className="text-xs text-gray-500 font-semibold uppercase tracking-wide">{h}</span>
            ))}
          </div>

          {items.map(item => {
            const color = CAT_COLOR[item.product.category] ?? "bg-gray-50 text-gray-400";
            const icon  = CAT_ICON[item.product.category]  ?? <Box size={16} />;
            return (
              <div key={item.product.id}
                className="grid grid-cols-[1fr_auto] md:grid-cols-[2fr_1fr_auto_1fr_auto] gap-4 items-center px-5 py-4 border-b border-gray-100 last:border-0">
                <div className="flex items-center gap-3">
                  <div className={`w-11 h-11 rounded-lg flex items-center justify-center shrink-0 ${color}`} style={{ fontSize: "0.75em" }}>
                    {item.product.imageUrl
                      ? <img src={item.product.imageUrl} alt="" className="w-full h-full object-contain rounded-lg" />
                      : icon}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 leading-tight">{item.product.name}</p>
                    <p className="text-sm text-green-600 font-bold md:hidden mt-0.5">{R(item.product.price)}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 md:hidden">
                  <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
                    <button onClick={() => setQty(item.product.id, item.qty - 1)} className="p-1.5 hover:bg-gray-50 text-gray-600"><Minus size={13} /></button>
                    <span className="w-7 text-center text-sm font-bold">{item.qty}</span>
                    <button onClick={() => setQty(item.product.id, item.qty + 1)} className="p-1.5 hover:bg-gray-50 text-gray-600"><Plus size={13} /></button>
                  </div>
                  <button onClick={() => remove(item.product.id)} className="text-gray-300 hover:text-red-400 transition-colors"><Trash2 size={15} /></button>
                </div>

                <span className="hidden md:block text-sm text-gray-600">{R(item.product.price)}</span>
                <div className="hidden md:flex items-center border border-gray-200 rounded-lg overflow-hidden w-fit">
                  <button onClick={() => setQty(item.product.id, item.qty - 1)} className="p-1.5 hover:bg-gray-50 text-gray-600"><Minus size={13} /></button>
                  <span className="w-8 text-center text-sm font-bold">{item.qty}</span>
                  <button onClick={() => setQty(item.product.id, item.qty + 1)} className="p-1.5 hover:bg-gray-50 text-gray-600"><Plus size={13} /></button>
                </div>
                <span className="hidden md:block text-sm font-bold text-gray-900">{R(item.product.price * item.qty)}</span>
                <button onClick={() => remove(item.product.id)} className="hidden md:block text-gray-300 hover:text-red-400 transition-colors"><Trash2 size={16} /></button>
              </div>
            );
          })}

          <div className="px-5 py-3 border-t border-gray-100">
            <button onClick={onBack} className="text-green-600 hover:text-green-700 text-sm font-semibold flex items-center gap-1.5">
              <ArrowLeft size={14} /> Continuar comprando
            </button>
          </div>
        </div>

        <div className="w-full lg:w-72 shrink-0">
          <div className="bg-white rounded-xl border border-gray-200 p-5 sticky top-24">
            <h3 className="font-bold text-gray-900 mb-4">Resumo do pedido</h3>
            <div className="space-y-2.5 text-sm">
              <div className="flex justify-between text-gray-500">
                <span>Subtotal ({items.reduce((s,i)=>s+i.qty,0)} itens)</span>
                <span className="font-semibold text-gray-800">{R(subtotal)}</span>
              </div>
              <div className="flex justify-between text-gray-500">
                <span>Frete (Entrega)</span>
                <span className="font-semibold text-gray-800">{R(FRETE)}</span>
              </div>
              <div className="flex justify-between items-center font-bold text-base border-t border-gray-100 pt-3">
                <span className="text-gray-900">Total</span>
                <span className="text-green-600 text-lg">{R(total)}</span>
              </div>
            </div>
            {/* hidden lg:flex — no mobile o resumo/botão viram a barra fixa
                embaixo (ver abaixo); mesmo onClick (onCheckout, mesma rota
                de sempre) só que reaproveitado lá. Desktop sem mudança. */}
            <button onClick={onCheckout}
              className="mt-5 w-full hidden lg:flex bg-green-600 hover:bg-green-700 active:bg-green-800 text-white font-bold py-3 rounded-xl transition-colors items-center justify-center gap-2">
              Continuar <ChevronRight size={18} />
            </button>
            <div className="mt-3 hidden lg:flex items-center justify-center gap-1.5 text-xs text-gray-400">
              <Shield size={13} /> <span>Ambiente seguro e protegido</span>
            </div>
          </div>
        </div>
      </div>

      {/* Resumo fixo embaixo (mobile) — pedido explícito desta tarefa:
          subtotal/entrega/total sempre visíveis + botão "Continuar", sem
          precisar rolar. Mesmo onCheckout de sempre (mesma rota /checkout),
          só reaproveitado aqui. pb-20 no <main> do PublicLayout já reserva
          espaço embaixo pra essa barra não cobrir conteúdo. */}
      <div className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-gray-200 px-4 py-3 shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Subtotal</span><span>{R(subtotal)}</span>
        </div>
        <div className="flex justify-between text-xs text-gray-500 mb-2">
          <span>Entrega</span><span>{R(FRETE)}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="shrink-0">
            <p className="text-[11px] text-gray-500 leading-none">Total</p>
            <p className="text-base font-bold text-green-600 leading-tight">{R(total)}</p>
          </div>
          <button onClick={onCheckout}
            className="flex-1 min-h-11 bg-green-600 hover:bg-green-700 active:bg-green-800 text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2">
            Continuar <ChevronRight size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

// Seletor de forma de pagamento — extraído aqui (nível do módulo) porque é
// usado em DOIS lugares: o checkout normal (CheckoutView) e a Venda Balcão
// do painel admin (VendaBalcaoSection). Mesmo componente, mesmas opções
// (PAYMENT_METHOD_LABELS), evita ter a mesma lista de botões duplicada.
function PaymentMethodSelector({ value, onChange }: {
  value: PaymentMethod; onChange: (metodo: PaymentMethod) => void;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map(metodo => (
        <button key={metodo} type="button" onClick={() => onChange(metodo)}
          className={`px-3 py-2.5 rounded-lg text-sm font-semibold border transition-colors ${
            value === metodo
              ? "bg-green-600 border-green-600 text-white"
              : "bg-white border-gray-200 text-gray-600 hover:border-green-300 hover:text-gray-900"
          }`}>
          {PAYMENT_METHOD_LABELS[metodo]}
        </button>
      ))}
    </div>
  );
}

// ─── Checkout View ────────────────────────────────────────────────────────────

// Campo de formulário controlado do checkout — definido no nível do módulo
// (fora de CheckoutView) de propósito. Antes vivia DENTRO do corpo de
// CheckoutView, sendo recriado a cada re-render (ou seja, a cada tecla
// digitada, já que digitar atualiza o estado do form): o React via isso
// como um componente de tipo diferente a cada vez, desmontava o <input>
// antigo e montava um novo, perdendo o foco a cada caractere. Recebe
// value/onChange como props diretas (componente controlado comum) em vez
// de fechar sobre "set"/"form" do escopo de CheckoutView — única forma de
// ficar fora do componente pai e continuar funcionando.
function CheckoutField({ label, value, onChange, error, placeholder, type = "text", valid = false }: {
  label: string; value: string; onChange: (v: string) => void;
  error?: string; placeholder?: string; type?: string;
  // "válido" é só um espelho visual das MESMAS regras que validate() já
  // usa pra decidir cada erro (ex: !!form.name.trim()) — calculado pelo
  // chamador, não uma validação nova; só acende a borda verde, nunca
  // decide sozinho se o formulário pode ser enviado.
  valid?: boolean;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-600 mb-1">{label}</label>
      <input type={type} value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        // text-base (16px) em mobile — abaixo disso o Safari iOS dá zoom
        // automático ao focar o input; md:text-sm volta ao tamanho
        // original a partir de 768px, sem mudar a aparência no desktop.
        className={`w-full px-3 py-2.5 text-base md:text-sm border rounded-lg outline-none transition-colors ${
          error
            ? "border-red-400 bg-red-50"
            : valid
              ? "border-green-500"
              : "border-gray-200 focus:border-green-500 focus:ring-1 focus:ring-green-200"
        }`} />
      {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
    </div>
  );
}

function CheckoutView({ items, savedCustomer, onConfirm, onBack, isSubmitting }: {
  items: CartItem[]; savedCustomer: Customer;
  onConfirm: (c: Customer, paymentWindow: Window | null) => void; onBack: () => void; isSubmitting: boolean;
}) {
  const [form,       setForm      ] = useState<Customer>(savedCustomer);
  const [loadingCep, setLoadingCep] = useState(false);
  const [errors,     setErrors    ] = useState<Partial<Record<keyof Customer, string>>>({});

  const subtotal = items.reduce((s, i) => s + i.product.price * i.qty, 0);
  const total    = subtotal + FRETE;

  const set = (k: keyof Customer, v: string) => {
    setForm(f => ({ ...f, [k]: v }));
    setErrors(e => ({ ...e, [k]: undefined }));
  };

  const lookupCep = async (cep: string) => {
    const clean = cep.replace(/\D/g, "");
    if (clean.length !== 8) return;
    setLoadingCep(true);
    try {
      const res  = await fetch(`https://viacep.com.br/ws/${clean}/json/`);
      const data = await res.json();
      if (!data.erro) {
        setForm(f => ({
          ...f,
          address:      data.logradouro || f.address,
          neighborhood: data.bairro     || f.neighborhood,
          city:         data.localidade || f.city,
          state:        data.uf         || f.state,
        }));
      } else {
        toast.error("CEP não encontrado");
      }
    } catch {
      toast.error("Erro ao buscar CEP");
    } finally {
      setLoadingCep(false);
    }
  };

  const validate = (): boolean => {
    const e: Partial<Record<keyof Customer, string>> = {};
    if (!form.name.trim())     e.name     = "Nome obrigatório";
    if (!form.whatsapp.trim()) e.whatsapp = "WhatsApp obrigatório";
    if (!form.cep.trim())      e.cep      = "CEP obrigatório";
    if (!form.address.trim())  e.address  = "Endereço obrigatório";
    if (!form.number.trim())   e.number   = "Número obrigatório";
    if (!form.city.trim())     e.city     = "Cidade obrigatória";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  // Abre a aba do WhatsApp DENTRO do mesmo gesto de clique do usuário —
  // window.open("", "_blank") síncrono aqui ainda conta como iniciado por
  // clique real pro navegador, então não é bloqueado como pop-up. A URL só
  // é definida depois (em CheckoutPage, quando o POST /api/pedidos volta
  // com sucesso e o linkPagamento fica disponível) — nesse ponto o clique
  // original já terminou, mas a aba em si já existia, então setar location
  // nela não conta mais como "abrir pop-up novo". Sem isso, esperar o
  // POST assíncrono terminar antes de chamar window.open() seria bloqueado
  // pela maioria dos navegadores (mobile principalmente).
  const handleSubmit = () => {
    if (!validate()) return;
    const paymentWindow = window.open("", "_blank");
    onConfirm(form, paymentWindow);
  };

  return (
    <div className="max-w-3xl mx-auto">
      <button onClick={onBack}
        className="text-green-600 hover:text-green-700 flex items-center gap-1.5 text-sm font-semibold mb-5">
        <ArrowLeft size={15} /> Voltar ao carrinho
      </button>

      {/* Barra de progresso — só visual (pedido explícito desta tarefa: não
          é um wizard de verdade, continua sendo uma tela só; os mesmos 3
          rótulos de antes, "Cadastro" sempre marcado como etapa atual). */}
      <div className="mb-7">
        <div className="flex items-center justify-between text-xs font-semibold mb-1.5">
          {["Carrinho", "Cadastro", "Confirmação"].map((step, i) => (
            <span key={step} className={i <= 1 ? "text-brand" : "text-gray-400"}>{step}</span>
          ))}
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-brand rounded-full transition-all" style={{ width: "66%" }} />
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-5">
        <div className="flex-1 space-y-4">
          {/* Personal */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-bold text-gray-900 mb-4 text-sm flex items-center gap-2">
              <User size={15} className="text-green-600" /> Dados pessoais
            </h3>
            <div className="space-y-3">
              <CheckoutField label="Nome completo *" value={form.name} onChange={v => set("name", v)}
                error={errors.name} valid={!!form.name.trim()} placeholder="Seu nome completo" />
              <div className="grid grid-cols-2 gap-3">
                <CheckoutField label="WhatsApp *" value={form.whatsapp} onChange={v => set("whatsapp", v)}
                  error={errors.whatsapp} valid={!!form.whatsapp.trim()} placeholder="(11) 99999-9999" type="tel" />
                <CheckoutField label="CPF / CNPJ" value={form.cpfCnpj} onChange={v => set("cpfCnpj", v)}
                  placeholder="000.000.000-00" />
              </div>
            </div>
          </div>

          {/* Address */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-bold text-gray-900 mb-4 text-sm flex items-center gap-2">
              <MapPin size={15} className="text-green-600" /> Endereço de entrega
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">CEP *</label>
                <div className="relative">
                  <input type="text" value={form.cep}
                    onChange={e => set("cep", e.target.value)}
                    onBlur={() => lookupCep(form.cep)}
                    placeholder="00000-000"
                    className={`w-full px-3 py-2.5 text-base md:text-sm border rounded-lg outline-none transition-colors pr-9 ${
                      errors.cep
                        ? "border-red-400 bg-red-50"
                        : form.cep.trim()
                          ? "border-green-500"
                          : "border-gray-200 focus:border-green-500 focus:ring-1 focus:ring-green-200"
                    }`} />
                  {loadingCep && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
                  )}
                </div>
                {errors.cep && <p className="text-red-500 text-xs mt-1">{errors.cep}</p>}
              </div>
              <CheckoutField label="Endereço *" value={form.address} onChange={v => set("address", v)}
                error={errors.address} valid={!!form.address.trim()} placeholder="Rua, Avenida..." />
              <div className="grid grid-cols-2 gap-3">
                <CheckoutField label="Número *" value={form.number} onChange={v => set("number", v)}
                  error={errors.number} valid={!!form.number.trim()} placeholder="123" />
                <CheckoutField label="Complemento" value={form.complement} onChange={v => set("complement", v)}
                  placeholder="Apto, Bloco..." />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <CheckoutField label="Bairro" value={form.neighborhood} onChange={v => set("neighborhood", v)}
                  placeholder="Bairro" />
                <CheckoutField label="Cidade *" value={form.city} onChange={v => set("city", v)}
                  error={errors.city} valid={!!form.city.trim()} placeholder="Cidade" />
              </div>
              <CheckoutField label="Estado" value={form.state} onChange={v => set("state", v)} placeholder="SP" />
            </div>
          </div>

          {/* Forma de pagamento — só uma preferência informativa (nunca
              bloqueia o envio do pedido, ver validate() acima que não
              inclui este campo): o pagamento em si é sempre fechado
              depois, por WhatsApp, com um atendente humano — não há
              cobrança nem gateway aqui. Pré-selecionado com "pix" (opção
              mais comum), então a mensagem de resumo nunca sai com "Não
              informado" a menos que o cliente troque e volte, o que não
              acontece nesse componente. */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-bold text-gray-900 mb-4 text-sm flex items-center gap-2">
              <Wallet size={15} className="text-green-600" /> Forma de pagamento
            </h3>
            <PaymentMethodSelector value={form.paymentMethod} onChange={v => set("paymentMethod", v)} />
          </div>

          <div className="p-4 bg-blue-50 rounded-xl border border-blue-100 flex gap-3">
            <Info size={15} className="text-blue-500 shrink-0 mt-0.5" />
            <p className="text-xs text-blue-700 leading-relaxed">
              O pagamento é finalizado com um atendente via WhatsApp após a confirmação.
              Não solicitamos dados de cartão ou Pix nesta etapa.
            </p>
          </div>
        </div>

        {/* Summary */}
        <div className="w-full lg:w-64 shrink-0">
          <div className="bg-white rounded-xl border border-gray-200 p-5 sticky top-24">
            <h4 className="font-bold text-gray-900 mb-3 text-sm">Resumo</h4>
            <div className="space-y-1 text-xs text-gray-500 mb-3 max-h-40 overflow-y-auto">
              {items.map(item => (
                <div key={item.product.id} className="flex justify-between">
                  <span className="truncate mr-2">{item.qty}x {item.product.name}</span>
                  <span className="shrink-0 font-medium text-gray-700">{R(item.product.price * item.qty)}</span>
                </div>
              ))}
            </div>
            <div className="border-t border-gray-100 pt-2.5 space-y-1 text-sm">
              <div className="flex justify-between text-gray-500 text-xs">
                <span>Frete</span><span>{R(FRETE)}</span>
              </div>
              <div className="flex justify-between font-bold">
                <span className="text-gray-900">Total</span>
                <span className="text-green-600">{R(total)}</span>
              </div>
            </div>
            {/* hidden lg:flex — no mobile esse botão fica só na barra fixa
                embaixo (ver abaixo), pra não duplicar o CTA na tela;
                desktop mantém exatamente como estava (sidebar sticky já
                cumpre o papel de "sempre visível" lá). Mesmo onClick/
                disabled/isSubmitting de sempre, só a visibilidade mudou. */}
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="mt-4 w-full hidden lg:flex bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-bold py-3 rounded-xl transition-colors text-sm items-center justify-center gap-2">
              {isSubmitting ? (
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Confirmando...</>
              ) : (
                <>Confirmar no WhatsApp <ChevronRight size={16} /></>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Botão fixo embaixo (mobile) — pedido explícito desta tarefa: total
          + "Confirmar no WhatsApp" sempre visíveis, sem precisar rolar até
          o fim do formulário. Chama a MESMA função de submit de sempre
          (validate() + onConfirm(form)) — nada de lógica nova, só reaproveita
          o handler que já existia no botão inline (agora escondido no
          mobile, ver acima). pb-24 no <main> do PublicLayout já reserva
          espaço embaixo pra essa barra não cobrir conteúdo. */}
      <div className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-gray-200 px-4 py-3 flex items-center gap-3 shadow-[0_-2px_8px_rgba(0,0,0,0.06)]">
        <div className="shrink-0">
          <p className="text-[11px] text-gray-500 leading-none">Total</p>
          <p className="text-base font-bold text-green-600 leading-tight">{R(total)}</p>
        </div>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="flex-1 min-h-11 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-bold rounded-xl transition-colors text-sm flex items-center justify-center gap-2">
          {isSubmitting ? (
            <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Confirmando...</>
          ) : (
            <>Confirmar no WhatsApp <ChevronRight size={16} /></>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Confirmation View ────────────────────────────────────────────────────────

function ConfirmationView({ order, onContinue }: {
  order: Order; onContinue: () => void;
}) {
  return (
    <div className="max-w-xl mx-auto py-6">
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
        {/* Header */}
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 border-b border-green-100 px-6 pt-7 pb-6 flex items-start gap-4">
          <div className="w-14 h-14 bg-green-500 rounded-full flex items-center justify-center shrink-0 shadow-md">
            <Check size={28} className="text-white" strokeWidth={3} />
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-gray-900">Pedido confirmado!</h2>
            <p className="text-sm text-gray-500 mt-1 leading-relaxed">
              Recebemos seu pedido e ele já está sendo analisado pela nossa equipe.
            </p>
            <div className="mt-3 inline-flex items-center gap-2 bg-white border border-green-200 rounded-full px-3 py-1">
              <FileText size={12} className="text-green-600" />
              <span className="text-green-700 font-bold text-sm">{order.number}</span>
            </div>
          </div>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* O WhatsApp já foi aberto automaticamente ao confirmar o pedido
              (ver handleConfirmOrder em CheckoutPage) — sem botão aqui pra
              não pedir um segundo clique pra uma ação que já aconteceu. */}
          <p className="text-center text-xs text-gray-400">
            Um atendente irá confirmar os detalhes e a forma de pagamento.
          </p>

          {/* Customer info */}
          <div className="p-3.5 bg-gray-50 rounded-xl text-sm space-y-1">
            <p className="font-semibold text-gray-800">{order.customer.name}</p>
            <p className="text-gray-500 flex items-center gap-1.5"><Phone size={12} /> {order.customer.whatsapp}</p>
            {order.customer.address && (
              <p className="text-gray-500 flex items-center gap-1.5">
                <MapPin size={12} /> {order.customer.address}, {order.customer.number} — {order.customer.city}/{order.customer.state}
              </p>
            )}
          </div>

          {/* Items */}
          <div className="border border-gray-100 rounded-xl overflow-hidden">
            {order.items.map(item => (
              <div key={item.product.id}
                className="flex justify-between items-center px-4 py-3 border-b border-gray-50 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 bg-green-100 text-green-700 rounded-full text-xs font-bold flex items-center justify-center shrink-0">
                    {item.qty}
                  </span>
                  <span className="text-sm text-gray-700">{item.product.name}</span>
                </div>
                <span className="text-sm font-semibold text-gray-900">{R(item.product.price * item.qty)}</span>
              </div>
            ))}
            <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 space-y-1">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Entrega:</span><span>{R(order.frete)}</span>
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>Pagamento:</span><span>Via WhatsApp com atendente</span>
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>Previsão:</span><span>60~70 minutos</span>
              </div>
              <div className="flex justify-between font-bold text-base border-t border-gray-200 pt-2 mt-1">
                <span className="text-gray-900">TOTAL</span>
                <span className="text-green-600">{R(order.total)}</span>
              </div>
            </div>
          </div>

          {/* Linha do tempo — só representação visual do status (o pedido
              acabou de ser criado, então só "Recebido" já aconteceu de
              verdade); não existe tracking de verdade por trás disso hoje,
              não inventei nenhum. Substitui a lista "Próximos passos" que
              existia antes, mesma informação, só apresentada como timeline
              horizontal em vez de checklist vertical. */}
          <div className="bg-gray-50 rounded-xl p-4">
            <h4 className="font-bold text-gray-800 mb-4 text-sm">Status do pedido</h4>
            <div className="flex items-start">
              {["Recebido", "Pagamento", "Separação", "Enviado"].map((etapa, i) => (
                <div key={etapa} className="flex-1 flex flex-col items-center text-center relative">
                  {i > 0 && (
                    <div className={`absolute top-3 right-1/2 w-full h-0.5 ${i === 1 ? "bg-green-600" : "bg-gray-200"}`} />
                  )}
                  <span className={`relative z-10 w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                    i === 0 ? "bg-green-600 text-white" : "bg-gray-200 text-gray-400"
                  }`}>
                    {i === 0 ? <Check size={12} strokeWidth={3} /> : i + 1}
                  </span>
                  <span className={`mt-1.5 text-[11px] font-semibold ${i === 0 ? "text-green-700" : "text-gray-400"}`}>
                    {etapa}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <button onClick={onContinue}
            className="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl transition-colors text-sm">
            Continuar comprando
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Orders View ──────────────────────────────────────────────────────────────

const STATUS_INFO: Record<Order["status"], { label: string; color: string }> = {
  pendente:   { label: "Pendente",   color: "bg-yellow-100 text-yellow-700" },
  em_analise: { label: "Em análise", color: "bg-blue-100   text-blue-700"   },
  confirmado: { label: "Confirmado", color: "bg-green-100  text-green-700"  },
  pago:       { label: "Pago",       color: "bg-teal-100   text-teal-700"  },
  entregue:   { label: "Entregue",   color: "bg-emerald-100 text-emerald-700"},
  cancelado:  { label: "Cancelado",  color: "bg-red-100    text-red-700"    },
};

// ─── Admin: lista de pedidos + marcar como pago ────────────────────────────────
// Ver todos os pedidos da loja e marcar pagamento são ações do lojista,
// protegidas pela chave de admin — por isso mora só aqui, dentro do painel
// interno (não existe mais tela pública equivalente pro cliente ver os
// próprios pedidos — removida, ver relatório desta tarefa).

const PEDIDOS_POR_PAGINA = 10;

function PedidosAdminSection() {
  const [orders,       setOrders      ] = useState<Order[]>([]);
  const [loading,      setLoading     ] = useState(true);
  const [expanded,     setExpanded    ] = useState<string | null>(null);
  const [marking,      setMarking     ] = useState<string | null>(null);
  const [retrying,     setRetrying    ] = useState<string | null>(null);
  const [filtroStatus, setFiltroStatus] = useState<Order["status"] | "todos">("todos");
  const [buscaCliente, setBuscaCliente] = useState("");
  const [pagina,       setPagina      ] = useState(1);

  const load = useCallback(() => {
    setLoading(true);
    orderService.getOrders()
      .then(setOrders)
      .catch((e: unknown) => mostrarErroAdmin(e, "Erro ao carregar pedidos"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Atendente confirmou manualmente pelo WhatsApp que o cliente pagou (sem
  // gateway) — avança a situação do pedido no Bling, disparando a baixa de
  // estoque nativa de lá.
  const handleMarcarPago = async (orderId: string) => {
    setMarking(orderId);
    try {
      await orderService.marcarComoPago(orderId);
      setOrders(prev => prev.map(o => o.id === orderId ? { ...o, status: "pago" } : o));
      toast.success("Pedido marcado como pago — baixa de estoque disparada no Bling.");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao marcar pedido como pago");
    } finally {
      setMarking(null);
    }
  };

  // "pendente" no front = "falhou_bling" no backend (ver statusToFrontend em
  // orderService.ts) — retenta a mesma rota já usada manualmente por curl.
  const handleTentarNovamente = async (orderId: string) => {
    setRetrying(orderId);
    try {
      await orderService.retryBling(orderId);
      toast.success("Reprocessado — atualizando lista...");
      load();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao tentar novamente");
    } finally {
      setRetrying(null);
    }
  };

  // Pedidos que falharam no Bling vêm primeiro (não podem passar
  // despercebidos), o resto mantém a ordem que já vinha da API (mais
  // recente primeiro). Filtro/busca rodam antes da paginação.
  const filtrados = useMemo(() => {
    let lista = [...orders].sort((a, b) => {
      if (a.status === "pendente" && b.status !== "pendente") return -1;
      if (b.status === "pendente" && a.status !== "pendente") return 1;
      return 0;
    });

    if (filtroStatus !== "todos") lista = lista.filter(o => o.status === filtroStatus);
    if (buscaCliente.trim()) {
      const q = buscaCliente.trim().toLowerCase();
      lista = lista.filter(o => o.customer.name.toLowerCase().includes(q));
    }
    return lista;
  }, [orders, filtroStatus, buscaCliente]);

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / PEDIDOS_POR_PAGINA));
  const paginaAtual = Math.min(pagina, totalPaginas);
  const visiveis = filtrados.slice(
    (paginaAtual - 1) * PEDIDOS_POR_PAGINA,
    paginaAtual * PEDIDOS_POR_PAGINA
  );

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-bold text-gray-900 text-sm flex items-center gap-2">
          <ClipboardList size={15} className="text-green-600" /> Pedidos
        </h3>
        <button onClick={load} className="text-gray-400 hover:text-green-600 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        Lista completa de pedidos da loja. Expanda um pedido pra marcá-lo como pago.
      </p>

      {/* Filtro + busca */}
      <div className="flex flex-col sm:flex-row gap-2 mb-3">
        <select value={filtroStatus}
          onChange={e => { setFiltroStatus(e.target.value as Order["status"] | "todos"); setPagina(1); }}
          className="text-xs border border-gray-200 rounded-lg px-2 py-2 text-gray-600 outline-none focus:border-green-500 bg-white">
          <option value="todos">Todos os status</option>
          {Object.entries(STATUS_INFO).map(([valor, info]) => (
            <option key={valor} value={valor}>{info.label}</option>
          ))}
        </select>
        <input value={buscaCliente}
          onChange={e => { setBuscaCliente(e.target.value); setPagina(1); }}
          placeholder="Buscar por nome do cliente..."
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-green-500" />
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><RefreshCw size={20} className="text-gray-300 animate-spin" /></div>
      ) : filtrados.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-6">Nenhum pedido encontrado</p>
      ) : (
        <>
          <div className="space-y-2">
            {visiveis.map(order => {
              const st        = STATUS_INFO[order.status];
              const open      = expanded === order.id;
              const comFalha  = order.status === "pendente"; // falhou_bling
              return (
                <div key={order.id}
                  className={`border rounded-lg overflow-hidden ${comFalha ? "border-red-200 bg-red-50/40" : "border-gray-100"}`}>
                  <button className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
                    onClick={() => setExpanded(open ? null : order.id)}>
                    <div className="flex items-center gap-2">
                      {comFalha && <AlertCircle size={16} className="text-red-500 shrink-0" />}
                      <div>
                        <p className="font-bold text-gray-900 text-sm">{order.number}</p>
                        <p className="text-xs text-gray-400">{order.customer.name} · {new Date(order.createdAt).toLocaleString("pt-BR")}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-green-600 text-sm">{R(order.total)}</span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${st.color}`}>{st.label}</span>
                    </div>
                  </button>
                  {open && (
                    <div className="border-t border-gray-100 px-4 py-3 space-y-2">
                      {/* paymentMethod é opcional — pedidos de antes desse
                          campo existir vêm com null/undefined do backend;
                          "Não informado" cobre esse caso sem quebrar nada. */}
                      <p className="text-xs text-gray-500 flex items-center gap-1.5">
                        <Wallet size={12} /> <strong className="text-gray-700">Forma de pagamento:</strong>{" "}
                        {order.paymentMethod || "Não informado"}
                      </p>
                      {comFalha && (
                        <button onClick={() => handleTentarNovamente(order.id)} disabled={retrying === order.id}
                          className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-bold py-2 rounded-lg transition-colors text-sm">
                          <RefreshCw size={14} className={retrying === order.id ? "animate-spin" : ""} />
                          {retrying === order.id ? "Tentando novamente..." : "Tentar novamente"}
                        </button>
                      )}
                      {order.status !== "pago" && order.blingId && (
                        <button onClick={() => handleMarcarPago(order.id)} disabled={marking === order.id}
                          className="w-full flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-bold py-2 rounded-lg transition-colors text-sm">
                          {marking === order.id ? (
                            <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Marcando...</>
                          ) : (
                            <><Check size={15} strokeWidth={3} /> Marcar como pago</>
                          )}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Paginação — client-side, sobre o que já veio da API */}
          {totalPaginas > 1 && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
              <button onClick={() => setPagina(p => Math.max(1, p - 1))} disabled={paginaAtual === 1}
                className="text-xs font-semibold text-gray-500 disabled:opacity-30 hover:text-green-600 transition-colors">
                ← Anterior
              </button>
              <span className="text-xs text-gray-400">Página {paginaAtual} de {totalPaginas}</span>
              <button onClick={() => setPagina(p => Math.min(totalPaginas, p + 1))} disabled={paginaAtual === totalPaginas}
                className="text-xs font-semibold text-gray-500 disabled:opacity-30 hover:text-green-600 transition-colors">
                Próxima →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Admin: Venda Balcão ────────────────────────────────────────────────────────

interface ItemVendaBalcao { product: Product; qty: number }

/** Registro rápido de venda presencial pelo funcionário — SEM os dados de
 * entrega que o fluxo do WhatsApp/catálogo exige (nome, telefone, endereço).
 * Reaproveita: a mesma busca de produtos do catálogo (productService), o
 * mesmo seletor de forma de pagamento do checkout (PaymentMethodSelector),
 * e as MESMAS duas rotas já existentes e validadas (POST /api/pedidos com
 * vendaBalcao:true, depois POST .../marcar-pago) — nada de lógica de
 * pedido/Bling/estoque reescrita aqui, só orquestração de UI. */
function VendaBalcaoSection() {
  const [busca,        setBusca       ] = useState("");
  const [resultados,   setResultados  ] = useState<Product[]>([]);
  const [buscando,     setBuscando    ] = useState(false);
  const [carrinho,     setCarrinho    ] = useState<ItemVendaBalcao[]>([]);
  const [metodo,       setMetodo      ] = useState<PaymentMethod>("dinheiro");
  const [finalizando,  setFinalizando ] = useState(false);

  // Busca com debounce (catálogo real tem milhares de produtos — sem
  // debounce seria uma chamada de API por tecla digitada).
  useEffect(() => {
    if (!busca.trim()) { setResultados([]); return; }
    setBuscando(true);
    const timer = setTimeout(() => {
      productService.getProducts({ busca })
        .then(produtos => setResultados(produtos.slice(0, 8))) // só os 8 primeiros — é busca rápida de balcão, não o catálogo inteiro
        .catch(() => toast.error("Erro ao buscar produtos"))
        .finally(() => setBuscando(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [busca]);

  const adicionar = (produto: Product) => {
    setCarrinho(c => {
      const existente = c.find(i => i.product.id === produto.id);
      if (existente) {
        return c.map(i => i.product.id === produto.id ? { ...i, qty: i.qty + 1 } : i);
      }
      return [...c, { product: produto, qty: 1 }];
    });
    setBusca("");
    setResultados([]);
  };

  const alterarQtd = (produtoId: number, qty: number) => {
    if (qty <= 0) { setCarrinho(c => c.filter(i => i.product.id !== produtoId)); return; }
    setCarrinho(c => c.map(i => i.product.id === produtoId ? { ...i, qty } : i));
  };

  const remover = (produtoId: number) => setCarrinho(c => c.filter(i => i.product.id !== produtoId));

  const total = carrinho.reduce((s, i) => s + i.product.price * i.qty, 0);

  // Duas chamadas HTTP em sequência (criar pedido -> marcar como pago),
  // reaproveitando as duas rotas já existentes sem alterar nenhuma das
  // duas — do ponto de vista do funcionário é UM clique, UM resultado.
  // Cada etapa que pode falhar tem sua própria mensagem específica, pra
  // nunca deixar o funcionário sem saber o que realmente aconteceu.
  const finalizarVenda = async () => {
    if (carrinho.length === 0) return;
    setFinalizando(true);
    try {
      const itens = carrinho.map(i => ({ produtoId: i.product.id, quantidade: i.qty }));
      const pedido = await orderService.criarVendaBalcao(itens, metodo);

      if (!pedido.blingId) {
        // _tentar_criar_no_bling falhou lá no backend — o pedido local
        // existe (visível em Pedidos), mas marcar-pago recusaria (exige
        // blingId) — nem tenta, evita um segundo erro sem sentido.
        toast.error(
          `Pedido ${pedido.number} criado, mas houve erro ao criar no Bling — verifique manualmente o pedido ${pedido.number} no painel de Pedidos.`,
          { duration: 8000 }
        );
        setCarrinho([]);
        return;
      }

      try {
        await orderService.marcarComoPago(pedido.id);
        toast.success(`Venda ${pedido.number} registrada — estoque baixado no Bling!`);
        setCarrinho([]);
      } catch {
        toast.error(
          `Pedido ${pedido.number} criado e registrado no Bling, mas houve erro ao marcar como pago — verifique manualmente o pedido ${pedido.number} no painel de Pedidos.`,
          { duration: 8000 }
        );
        setCarrinho([]);
      }
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao registrar a venda");
    } finally {
      setFinalizando(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="font-bold text-gray-900 mb-1 text-sm flex items-center gap-2">
        <ShoppingCart size={15} className="text-green-600" /> Venda Balcão
      </h3>
      <p className="text-xs text-gray-400 mb-4">
        Venda presencial rápida, sem dados de entrega — cria o pedido e já
        marca como pago, disparando a baixa de estoque no Bling.
      </p>

      {/* Busca de produto */}
      <div className="relative mb-3">
        <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
          <Search size={15} className="ml-3 text-gray-400 shrink-0" />
          <input value={busca} onChange={e => setBusca(e.target.value)}
            placeholder="Buscar produto por nome..."
            className="flex-1 px-2.5 py-2.5 text-sm outline-none" />
        </div>
        {(resultados.length > 0 || buscando) && (
          <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
            {buscando ? (
              <p className="px-3 py-2.5 text-xs text-gray-400">Buscando...</p>
            ) : resultados.map(produto => (
              <button key={produto.id} onClick={() => adicionar(produto)} disabled={!produto.inStock}
                className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed border-b border-gray-50 last:border-0">
                <span className="truncate">{produto.name}</span>
                <span className="shrink-0 font-semibold text-gray-600">{R(produto.price)}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Carrinho rápido */}
      {carrinho.length === 0 ? (
        <p className="text-xs text-gray-400 py-6 text-center">Nenhum item adicionado ainda.</p>
      ) : (
        <div className="space-y-2 mb-4">
          {carrinho.map(item => (
            <div key={item.product.id} className="flex items-center gap-2 py-2 border-b border-gray-50 last:border-0">
              <span className="flex-1 text-sm text-gray-800 truncate">{item.product.name}</span>
              <span className="text-xs text-gray-400 shrink-0">{R(item.product.price)}</span>
              <input type="number" min={1} value={item.qty}
                onChange={e => alterarQtd(item.product.id, Number(e.target.value))}
                className="w-14 px-1.5 py-1 text-sm text-center border border-gray-200 rounded-lg outline-none focus:border-green-500 shrink-0" />
              <span className="w-16 text-right text-sm font-bold text-gray-900 shrink-0">{R(item.product.price * item.qty)}</span>
              <button onClick={() => remover(item.product.id)}
                className="text-gray-300 hover:text-red-400 transition-colors shrink-0">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Forma de pagamento — reaproveita o mesmo componente do checkout */}
      <p className="text-xs font-semibold text-gray-600 mb-2">Forma de pagamento</p>
      <PaymentMethodSelector value={metodo} onChange={setMetodo} />

      <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
        <div>
          <p className="text-xs text-gray-500">Total</p>
          <p className="text-xl font-bold text-green-600">{R(total)}</p>
        </div>
        <button onClick={finalizarVenda} disabled={carrinho.length === 0 || finalizando}
          className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-bold py-3 px-6 rounded-xl transition-colors text-sm flex items-center gap-2">
          {finalizando ? (
            <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Registrando...</>
          ) : (
            <><Check size={16} strokeWidth={3} /> Finalizar Venda</>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Admin: configurações da loja ──────────────────────────────────────────────

function ConfiguracoesLojaForm() {
  const [config, setConfig] = useState<configService.Configuracoes | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    configService.getConfiguracoes()
      .then(setConfig)
      .catch((e: unknown) => mostrarErroAdmin(e, "Erro ao carregar configurações"));
  }, []);

  const set = <K extends keyof configService.Configuracoes>(
    campo: K, valor: configService.Configuracoes[K]
  ) => setConfig(c => (c ? { ...c, [campo]: valor } : c));

  const salvar = async () => {
    if (!config) return;
    setSaving(true);
    try {
      const atualizado = await configService.atualizarConfiguracoes(config);
      setConfig(atualizado);
      toast.success("Configurações da loja salvas!");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao salvar configurações");
    } finally {
      setSaving(false);
    }
  };

  const inputClass = "w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg outline-none focus:border-green-500 transition-colors";

  if (!config) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <p className="text-sm text-gray-400">Carregando configurações...</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="font-bold text-gray-900 mb-1 text-sm flex items-center gap-2">
        <Settings size={15} className="text-green-600" /> Configurações da loja
      </h3>
      <p className="text-xs text-gray-400 mb-4">
        Textos do bot, horário/endereço, pedido mínimo, desconto e a IA do
        WhatsApp — editáveis aqui, sem precisar mexer em código nem
        reiniciar o servidor. Nenhuma credencial (Bling, IA, WhatsApp) fica
        neste painel — essas continuam só no .env do servidor.
      </p>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">
            Mensagem de saudação (início da conversa)
          </label>
          <textarea value={config.textoSaudacao} onChange={e => set("textoSaudacao", e.target.value)}
            rows={4} className={inputClass} />
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">
            Abertura da opção "Comprar peças"
          </label>
          <input value={config.textoMenuComprar} onChange={e => set("textoMenuComprar", e.target.value)}
            className={inputClass} />
          <p className="text-xs text-gray-400 mt-1">
            Só a frase de abertura — o link do catálogo é sempre gerado automaticamente logo depois.
          </p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">
            Mensagem da opção "Assistência técnica"
          </label>
          <textarea value={config.textoMenuAssistencia} onChange={e => set("textoMenuAssistencia", e.target.value)}
            rows={2} className={inputClass} />
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">
            Texto institucional (opção "Horário e endereço da loja")
          </label>
          <textarea value={config.textoSobreLoja} onChange={e => set("textoSobreLoja", e.target.value)}
            rows={2} placeholder="Ex: Somos a JSV CELL, especialistas em peças e assistência!"
            className={inputClass} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Horário de funcionamento</label>
            <input value={config.horarioFuncionamento} onChange={e => set("horarioFuncionamento", e.target.value)}
              placeholder="Seg-Sáb, 9h-18h" className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Endereço da loja</label>
            <input value={config.enderecoLoja} onChange={e => set("enderecoLoja", e.target.value)}
              placeholder="Rua Exemplo, 123 - Centro" className={inputClass} />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">Telefone do atendente de pagamento</label>
          <input value={config.atendentePagamentoTelefone}
            onChange={e => set("atendentePagamentoTelefone", e.target.value)}
            placeholder="5511911111111" className={`${inputClass} font-mono`} />
          <p className="text-xs text-gray-400 mt-1">
            Se deixar vazio, usa o ATENDENTE_PAGAMENTO_TELEFONE do .env do servidor.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Pedido mínimo (R$)</label>
            <input type="number" min={0} step="0.01" value={config.pedidoMinimo}
              onChange={e => set("pedidoMinimo", Number(e.target.value))} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">Desconto padrão (%)</label>
            <input type="number" min={0} max={100} step="0.01" value={config.descontoPadraoPercentual}
              onChange={e => set("descontoPadraoPercentual", Number(e.target.value))} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">IA no WhatsApp</label>
            <select
              value={config.iaHabilitada === null ? "env" : config.iaHabilitada ? "on" : "off"}
              onChange={e => {
                const v = e.target.value;
                set("iaHabilitada", v === "env" ? null : v === "on");
              }}
              className={inputClass}>
              <option value="env">Seguir .env (padrão)</option>
              <option value="on">Ligada</option>
              <option value="off">Desligada</option>
            </select>
          </div>
        </div>
      </div>

      <button onClick={salvar} disabled={saving}
        className="mt-4 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-bold py-2.5 px-5 rounded-lg text-sm transition-colors">
        {saving ? "Salvando..." : "Salvar configurações"}
      </button>
    </div>
  );
}

// ─── Admin View ───────────────────────────────────────────────────────────────

function AdminView() {
  const [waBot,      setWaBot     ] = useState(CONFIG.whatsapp.bot);
  const [waPayment,  setWaPayment ] = useState(CONFIG.whatsapp.payment);
  // null = ainda checando (chamada em andamento pro backend); só depois
  // disso responder é que sabemos se mostra o formulário de login ou o
  // painel — evita um "flash" do formulário de login pra quem já está numa
  // sessão válida (cookie de até 8h, ver PERMANENT_SESSION_LIFETIME).
  const [logado,     setLogado    ] = useState<boolean | null>(null);
  const [usuario,    setUsuario   ] = useState("");
  const [senha,      setSenha     ] = useState("");
  const [showSenha,  setShowSenha ] = useState(false);
  const [entrando,   setEntrando  ] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [syncing,    setSyncing   ] = useState(false);
  const [summary,    setSummary   ] = useState<orderService.OrderSummary | null>(null);
  const [loadError,  setLoadError ] = useState<string | null>(null);
  const [ultimaSync, setUltimaSync] = useState<string | null>(null);

  useEffect(() => {
    authService.getSessionStatus()
      .then(r => setLogado(r.logado))
      .catch(() => setLogado(false));
  }, []);

  const handleLogin = async () => {
    setEntrando(true);
    setLoginError(null);
    try {
      await authService.login(usuario, senha);
      setLogado(true);
      setSenha(""); // não deixa a senha parada em memória/DOM depois de usada
    } catch (e: unknown) {
      setLoginError(e instanceof Error ? e.message : "Usuário ou senha inválidos");
    } finally {
      setEntrando(false);
    }
  };

  const handleLogout = async () => {
    try {
      await authService.logout();
    } catch {
      // mesmo se a chamada falhar (ex: já expirado), trata como deslogado —
      // não faz sentido travar o usuário numa sessão que o servidor já não
      // reconhece mais.
    }
    setLogado(false);
    setSummary(null);
  };

  // "Última sincronização com o Bling" — não existe endpoint dedicado pra
  // isso; usa o `atualizadoEm` mais recente entre os produtos do cache
  // local (que só muda quando um /bling/sync ou /bling/sync-estoque roda).
  useEffect(() => {
    productService.getProducts()
      .then(produtos => {
        const maisRecente = produtos
          .map(p => p.atualizadoEm)
          .filter((d): d is string => !!d)
          .sort()
          .at(-1);
        setUltimaSync(maisRecente ?? null);
      })
      .catch(() => {}); // não crítico — se falhar, só não mostra o indicador
  }, []);

  useEffect(() => {
    if (!logado) return;
    setLoadError(null);
    orderService.getOrderSummary()
      .then(setSummary)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : "Erro ao carregar resumo"));
  }, [logado]);

  const saveWhatsApp = () => {
    updateConfig({ whatsapp: { bot: waBot, payment: waPayment } });
    toast.success("Números de WhatsApp salvos!");
  };

  // Passa pela sessão do painel (não pela ADMIN_API_KEY) — quem aperta esse
  // botão é um humano logado no navegador, nunca deveria precisar saber ou
  // colar a chave de admin pra isso. As rotas /bling/sync e
  // /bling/sync-estoque em si continuam exigindo ADMIN_API_KEY (usadas pelo
  // scheduler automático); estas aqui são um proxy autenticado por sessão
  // que repassa a chamada usando a chave já configurada no servidor — ver
  // app/blueprints/admin/routes.py.
  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.post("/api/admin/sincronizar-catalogo", undefined, undefined, "include");
      await api.post("/api/admin/sincronizar-estoque", undefined, undefined, "include");
      toast.success("Catálogo e estoque sincronizados com o Bling!");
    } catch (e: unknown) {
      mostrarErroAdmin(e, "Erro ao sincronizar");
    } finally {
      setSyncing(false);
    }
  };

  if (logado !== true) {
    return (
      <div className="max-w-sm mx-auto">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 bg-[#0f1e0f] rounded-xl flex items-center justify-center shrink-0">
            <Settings size={20} className="text-green-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">Painel Admin</h2>
            <p className="text-sm text-gray-500">Faça login para continuar.</p>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="font-bold text-gray-900 mb-1 text-sm flex items-center gap-2">
            <Shield size={15} className="text-green-600" /> Login
          </h3>
          <p className="text-xs text-gray-400 mb-3">
            Usuário e senha configurados no servidor (ADMIN_USERNAME/ADMIN_PASSWORD_HASH).
          </p>
          <div className="space-y-2">
            <input value={usuario} onChange={e => setUsuario(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleLogin(); }}
              placeholder="Usuário"
              className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg outline-none focus:border-green-500" />
            <div className="relative">
              <input type={showSenha ? "text" : "password"}
                value={senha} onChange={e => setSenha(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") handleLogin(); }}
                placeholder="Senha"
                className="w-full px-3 py-2.5 pr-10 text-sm border border-gray-200 rounded-lg outline-none focus:border-green-500" />
              <button type="button" onClick={() => setShowSenha(s => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showSenha ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
          <button onClick={handleLogin} disabled={entrando || !usuario.trim() || !senha}
            className="mt-3 w-full bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-bold py-2.5 rounded-lg text-sm transition-colors">
            {entrando ? "Entrando..." : "Entrar"}
          </button>
          {loginError && (
            <p className="mt-2 text-xs text-red-600">{loginError}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-[#0f1e0f] rounded-xl flex items-center justify-center shrink-0">
            <Settings size={20} className="text-green-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">Painel Admin</h2>
            <p className="text-sm text-gray-500">Configure WhatsApp e monitore pedidos.</p>
          </div>
        </div>
        <button onClick={handleLogout}
          className="text-sm text-gray-400 hover:text-red-600 font-semibold transition-colors shrink-0">
          Sair
        </button>
      </div>

      {loadError && (
        <p className="text-xs text-red-600">{loadError}</p>
      )}

      {/* Stats */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Total de pedidos", value: summary.total,        icon: <ClipboardList size={16} />, color: "text-blue-600 bg-blue-50"   },
            { label: "Pendentes no Bling", value: summary.pending,    icon: <Clock size={16} />,         color: "text-amber-600 bg-amber-50" },
            { label: "Receita total",    value: R(summary.revenue),   icon: <TrendingUp size={16} />,    color: "text-green-600 bg-green-50" },
            { label: "Ticket médio",     value: R(summary.avgTicket), icon: <BarChart2 size={16} />,     color: "text-purple-600 bg-purple-50"},
          ].map(s => (
            <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${s.color}`}>{s.icon}</div>
              <p className="text-lg font-bold text-gray-900">{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Venda Balcão — ao lado de Pedidos, mesmo padrão visual (card
          branco, mesmas cores) das demais seções deste painel. */}
      <VendaBalcaoSection />

      {/* Lista de pedidos + marcar como pago */}
      <PedidosAdminSection />

      {/* WhatsApp config */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-bold text-gray-900 mb-1 text-sm flex items-center gap-2">
          <MessageCircle size={15} className="text-green-500" /> Números de WhatsApp
        </h3>
        <p className="text-xs text-gray-400 mb-4">Configure os dois números do sistema.</p>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">
              Número 1 — Bot geral (Evolution API)
            </label>
            <div className="flex gap-2">
              <input value={waBot} onChange={e => setWaBot(e.target.value)}
                placeholder="5511900000000"
                className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-lg outline-none focus:border-green-500 font-mono" />
              <a href={`https://wa.me/${waBot.replace(/\D/g,"")}`} target="_blank" rel="noreferrer"
                className="flex items-center justify-center w-10 h-10 border border-gray-200 rounded-lg text-gray-400 hover:text-green-600 hover:border-green-300 transition-colors">
                <ExternalLink size={15} />
              </a>
            </div>
            <p className="text-xs text-gray-400 mt-1">Recebe mensagens, responde menu, envia link do catálogo.</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1">
              Número 2 — Atendente de pagamento (humano)
            </label>
            <div className="flex gap-2">
              <input value={waPayment} onChange={e => setWaPayment(e.target.value)}
                placeholder="5511911111111"
                className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-lg outline-none focus:border-green-500 font-mono" />
              <a href={`https://wa.me/${waPayment.replace(/\D/g,"")}`} target="_blank" rel="noreferrer"
                className="flex items-center justify-center w-10 h-10 border border-gray-200 rounded-lg text-gray-400 hover:text-green-600 hover:border-green-300 transition-colors">
                <ExternalLink size={15} />
              </a>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Este número aqui é só o exibido na interface. Quem realmente
              recebe o link de pagamento é o número configurado em
              ATENDENTE_PAGAMENTO_TELEFONE no servidor — mantenha os dois iguais.
            </p>
          </div>
        </div>

        <button onClick={saveWhatsApp}
          className="mt-4 bg-green-600 hover:bg-green-700 text-white font-bold py-2.5 px-5 rounded-lg text-sm transition-colors">
          Salvar números
        </button>
      </div>

      {/* Configurações da loja */}
      <ConfiguracoesLojaForm />

      {/* Bling — credenciais vivem só no servidor agora */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-bold text-gray-900 text-sm flex items-center gap-2">
            <Shield size={15} className="text-green-600" /> Integração Bling ERP
          </h3>
        </div>
        <p className="text-xs text-gray-400 mb-4">
          As credenciais (Client ID/Secret) do Bling ficam só no servidor
          (arquivo .env do backend) — nunca no navegador. Aqui você só
          dispara a sincronização manual, se quiser antecipar o próximo ciclo
          automático.
        </p>

        <div className="flex items-start gap-2 p-3 bg-blue-50 border border-blue-100 rounded-lg mb-4">
          <Info size={14} className="text-blue-500 shrink-0 mt-0.5" />
          <p className="text-xs text-blue-700 leading-relaxed">
            Para autorizar o Bling pela primeira vez, acesse{" "}
            <code className="bg-white px-1 rounded">/bling/authorize</code>{" "}
            direto no servidor (fora deste painel) e conclua o login.
          </p>
        </div>

        <button onClick={handleSync} disabled={syncing}
          className="flex items-center gap-1.5 px-4 py-2.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg transition-colors text-sm font-semibold">
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Sincronizando..." : "Sincronizar catálogo e estoque agora"}
        </button>

        <p className="mt-3 text-xs text-gray-400 flex items-center gap-1.5">
          <Clock size={12} />
          {ultimaSync
            ? <>Última sincronização: {new Date(ultimaSync).toLocaleString("pt-BR")}</>
            : "Última sincronização: sem dados ainda"}
        </p>
      </div>
    </div>
  );
}

// ─── Barra de navegação inferior (mobile) ───────────────────────────────────────
// Início / Categorias / Carrinho (com badge) / Pedidos foi o pedido original,
// mas a tela de "Pedidos" (busca por telefone) foi removida na Parte 2 desta
// MESMA tarefa — não sobrou destino nenhum pra esse 4º item, então fica só
// com os 3 que continuam existindo. "Categorias" reaproveita exatamente a
// mesma lógica que já existia no botão de Categorias do header antigo (zerar
// o filtro pra "all" + navegar pra "/" se necessário), só realocada pra cá.
// ─── Layout público (catálogo/carrinho/checkout/pedidos) ───────────────────────
// Fica montado o tempo todo enquanto o visitante navega dentro do site
// público — só o <Outlet/> troca de página. É aqui que mora o carrinho
// (useCart), pra sobreviver à navegação entre catálogo → carrinho → checkout.
// Não tem NENHUM link/ícone pro painel interno — ver Header e o rodapé abaixo.

function PublicLayout() {
  const [mobileMenu, setMobileMenu] = useState(false);
  const { items, add, setQty, remove, clear, count } = useCart();
  // Vivem aqui (não dentro da página do catálogo) pra sobreviver à
  // navegação e ficarem visíveis também pro Header, que é renderizado fora
  // do <Outlet/> — ver comentário na interface PublicContext.
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<Category>("all");

  const context: PublicContext = {
    items, add, setQty, remove, clear, count, mobileMenu, setMobileMenu,
    search, setSearch, activeCategory, setActiveCategory,
  };

  return (
    <div className="min-h-screen bg-[#f1f5f1] flex flex-col" style={{ fontFamily: "'Inter', sans-serif" }}>
      <Toaster position="bottom-right" richColors closeButton />

      <Header cartCount={count} onMenuClick={() => setMobileMenu(true)} />

      {/* pb-20 no mobile abre espaço pras barras fixas de ação (carrinho/
          checkout) não cobrirem o fim do conteúdo (md:pb-6 volta ao padding
          original no desktop, onde essas barras nem aparecem). */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 pt-6 pb-20 md:pb-6">
        <Outlet context={context} />
      </main>

      <footer className="border-t border-gray-200 bg-white mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-brand rounded flex flex-col items-center justify-center shrink-0">
              <span className="text-white font-black" style={{ fontSize: "0.37rem" }}>JSV</span>
              <span className="text-green-400 font-black" style={{ fontSize: "0.32rem" }}>CELL</span>
            </div>
            <span className="text-xs text-gray-400">© 2025 JSV CELL. Todos os direitos reservados.</span>
          </div>
          {/* Sem link/botão de Admin aqui de propósito — painel interno só
              é alcançável por quem digita a URL /painel-interno direto. */}
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <a href={whatsappService.getBotLink()} target="_blank" rel="noreferrer"
              className="hover:text-green-600 transition-colors flex items-center gap-1">
              <MessageCircle size={12} /> WhatsApp
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

// ─── Páginas (uma por rota) ─────────────────────────────────────────────────────

function CatalogPage() {
  // activeCategory e search agora vêm do PublicContext (layout), não de
  // estado local — precisam ser os MESMOS valores que o Header lê/escreve,
  // pra busca e o botão "Categorias" do cabeçalho conseguirem afetar o
  // catálogo mesmo vindo de fora dele. Efeito colateral aceitável: como o
  // contexto sobrevive à navegação (PublicLayout não desmonta), o filtro
  // de categoria/busca agora PERSISTE ao ir pro carrinho e voltar, em vez
  // de resetar — comportamento equivalente ao de outros sites de loja.
  const { items, add, mobileMenu, setMobileMenu, activeCategory, setActiveCategory, search, setSearch } =
    useOutletContext<PublicContext>();

  return (
    <CatalogView cart={items} onAdd={add}
      activeCategory={activeCategory} setActiveCategory={setActiveCategory}
      mobileMenuOpen={mobileMenu} setMobileMenuOpen={setMobileMenu}
      search={search} setSearch={setSearch} />
  );
}

function CartPage() {
  const { items, setQty, remove } = useOutletContext<PublicContext>();
  const navigate = useNavigate();

  return (
    <CartView items={items} setQty={setQty} remove={remove}
      onCheckout={() => navigate("/checkout")}
      onBack={() => navigate("/")} />
  );
}

function CheckoutPage() {
  const { items, clear } = useOutletContext<PublicContext>();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const savedCustomer = customerService.getCustomer();

  // Trava contra uma corrida real entre limpar o carrinho e navegar pra
  // confirmação (reproduzida e confirmada rodando o fluxo de verdade contra
  // o backend): o react-router (useSyncExternalStore por baixo) pode
  // aplicar a mudança de rota do navigate() em um commit SEPARADO do
  // setState de `clear()`, mesmo chamando navigate() antes de clear() no
  // código — não é garantido que as duas fiquem no mesmo lote. Isso abre
  // uma janela onde CheckoutPage re-renderiza com items=[] enquanto a URL
  // ainda é /checkout, aciona a guarda de "carrinho vazio" logo abaixo e
  // manda o usuário de volta pro catálogo antes da navegação pra
  // confirmação "vencer" a corrida. Um ref (não dispara re-render sozinho,
  // mas reflete o valor atual em QUALQUER render, venha de onde vier)
  // resolve isso sem depender de ordem/timing: uma vez que o pedido foi
  // confirmado, a guarda simplesmente para de valer, não importa quantas
  // vezes ou em que ordem os commits acontecem depois disso.
  const pedidoConfirmadoRef = useRef(false);

  const handleConfirmOrder = useCallback(async (customer: Customer, paymentWindow: Window | null) => {
    setSubmitting(true);
    try {
      const order = await orderService.createOrder(items, customer);
      pedidoConfirmadoRef.current = true;
      toast.success(`Pedido ${order.number} criado com sucesso!`, { duration: 3000 });
      // Mesmo link que a tela de confirmação abria antes num segundo clique
      // — agora só muda QUANDO ele é aberto (aqui, assim que o pedido é
      // criado com sucesso), não o link em si nem sua fonte (linkPagamento
      // do backend, com fallback local). A aba já existia (aberta em
      // branco no clique original, ver handleSubmit em CheckoutView) — só
      // navegamos ela pra URL certa agora que a temos.
      const paymentLink = whatsappService.getPaymentLink(order);
      if (paymentWindow) {
        paymentWindow.location.href = paymentLink;
      } else {
        // window.open síncrono no clique não retornou uma aba (navegador já
        // tinha bloqueado ali) — tenta mesmo assim como último recurso,
        // mas o esperado é isso já ter sido resolvido no clique original.
        window.open(paymentLink, "_blank");
      }
      // O pedido criado viaja pela navegação (state da rota), não por um
      // estado global — é assim que se passa dado "de uma tela pra outra"
      // com URLs de verdade, sem precisar de um contexto novo só pra isso.
      navigate("/pedido-confirmado", { state: { order } });
      clear();
    } catch {
      paymentWindow?.close();
      toast.error("Erro ao confirmar pedido. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  }, [items, clear, navigate]);

  // Acesso direto (ou refresh) com carrinho vazio não faz sentido continuar
  // — manda de volta pro catálogo em vez de mostrar um checkout quebrado.
  // `!pedidoConfirmadoRef.current` é o que impede essa guarda de disparar
  // por engano bem no momento em que o pedido acabou de ser confirmado (ver
  // comentário no ref acima).
  if (items.length === 0 && !pedidoConfirmadoRef.current) return <Navigate to="/" replace />;

  return (
    <CheckoutView items={items} savedCustomer={savedCustomer}
      onConfirm={handleConfirmOrder}
      onBack={() => navigate("/carrinho")}
      isSubmitting={submitting} />
  );
}

function ConfirmationPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const order = (location.state as { order?: Order } | null)?.order;

  // Acesso direto a essa URL (sem vir do checkout) ou um refresh perde o
  // "state" da navegação — sem pedido pra mostrar, volta pro catálogo em
  // vez de quebrar a tela.
  if (!order) return <Navigate to="/" replace />;

  return (
    <ConfirmationView order={order} onContinue={() => navigate("/")} />
  );
}

// AdminView por si só não traz <Toaster/> nem o fundo/padding da página —
// isso vivia no layout público (PublicLayout), que o painel interno
// propositalmente NÃO usa (nada de Header/Footer do catálogo aqui). Esse
// wrapper repõe só o que o painel precisa pra funcionar/ficar visualmente
// consistente, sem reintroduzir nenhum link pro catálogo público.
function AdminPage() {
  return (
    <div className="min-h-screen bg-[#f1f5f1]" style={{ fontFamily: "'Inter', sans-serif" }}>
      <Toaster position="bottom-right" richColors closeButton />
      <main className="max-w-7xl mx-auto w-full px-4 py-6">
        <AdminView />
      </main>
    </div>
  );
}

// ─── Rotas ──────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<CatalogPage />} />
          <Route path="carrinho" element={<CartPage />} />
          <Route path="checkout" element={<CheckoutPage />} />
          <Route path="pedido-confirmado" element={<ConfirmationPage />} />
        </Route>

        {/* Painel interno — de propósito FORA do PublicLayout (sem Header/
            Footer do catálogo) e sem nenhum link vindo da parte pública do
            site. Só acessível por quem digita essa URL direto. */}
        <Route path="painel-interno" element={<AdminPage />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
