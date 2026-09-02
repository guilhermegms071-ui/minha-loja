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

export const api = {
  get: <T>(path: string, headers?: Record<string, string>) =>
    request<T>(path, { method: "GET", headers }),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
  put: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
      headers,
    }),
};

export { ApiError };
