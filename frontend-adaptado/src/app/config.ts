// ─── Configuração Central JSV CELL ───────────────────────────────────────────
// Antes: guardava clientId/clientSecret do Bling aqui, expostos no navegador.
// Agora: essas credenciais vivem só no backend (.env do servidor Flask).
// O front só sabe a URL do backend e os números de WhatsApp que aparecem
// na interface (nenhum dos dois é dado sensível).

const STORAGE_KEY = "jsvcell_config";

interface AppConfig {
  whatsapp: {
    /** Número do bot geral (Evolution API) — exibido no rodapé/links, não é segredo */
    bot: string;
    /** Número do atendente de pagamento — usado só como FALLBACK se o
     * backend não devolver linkPagamento pronto (ver whatsappService.ts) */
    payment: string;
  };
  store: {
    name: string;
    frete: number;
    pedidoMinimo: number;
  };
}

const DEFAULT: AppConfig = {
  whatsapp: {
    bot: "5511900000000",
    payment: "5511911111111",
  },
  store: {
    name: "JSV CELL",
    frete: 6.0,
    pedidoMinimo: 0,
  },
};

function load(): AppConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT;
    return deepMerge(DEFAULT, JSON.parse(raw)) as AppConfig;
  } catch {
    return DEFAULT;
  }
}

function deepMerge(base: Record<string, unknown>, override: Record<string, unknown>): Record<string, unknown> {
  const result = { ...base };
  for (const key in override) {
    if (
      override[key] !== null &&
      typeof override[key] === "object" &&
      !Array.isArray(override[key]) &&
      typeof base[key] === "object"
    ) {
      result[key] = deepMerge(base[key] as Record<string, unknown>, override[key] as Record<string, unknown>);
    } else {
      result[key] = override[key];
    }
  }
  return result;
}

export let CONFIG: AppConfig = load();

export function updateConfig(partial: Partial<AppConfig>) {
  CONFIG = deepMerge(CONFIG as unknown as Record<string, unknown>, partial as unknown as Record<string, unknown>) as unknown as AppConfig;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(CONFIG));
}

export function resetConfig() {
  localStorage.removeItem(STORAGE_KEY);
  CONFIG = { ...DEFAULT };
}
