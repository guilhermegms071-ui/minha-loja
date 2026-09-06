// ─── API Service ───────────────────────────────────────────────────────────
// Ponto único de comunicação com o backend Flask.
// Nenhum outro service deve chamar `fetch` diretamente nem falar com o Bling
// ou guardar credenciais — tudo passa por aqui.

const API_BASE_URL =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:5000";

class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const isJson = resp.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await resp.json() : null;

  if (!resp.ok) {
    throw new ApiError(
      (data && (data.erro || data.mensagem)) || `Erro ${resp.status}`,
      resp.status,
      data
    );
  }

  return data as T;
}

// `credentials` só é passado explicitamente ("include") pelos services do
// painel admin, que agora dependem do cookie de sessão do login
// (POST /api/admin/login) pra autenticar — ver authService.ts. Omitido
// (undefined), o fetch usa o default do navegador ("same-origin"), que é
// exatamente o comportamento de sempre pras rotas públicas (catálogo,
// checkout): nenhuma delas precisa de cookie, então nada muda pra elas.
export const api = {
  get: <T>(path: string, headers?: Record<string, string>, credentials?: RequestCredentials) =>
    request<T>(path, { method: "GET", headers, credentials }),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>, credentials?: RequestCredentials) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
      credentials,
    }),
  put: <T>(path: string, body?: unknown, headers?: Record<string, string>, credentials?: RequestCredentials) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
      headers,
      credentials,
    }),
};

export { ApiError };
