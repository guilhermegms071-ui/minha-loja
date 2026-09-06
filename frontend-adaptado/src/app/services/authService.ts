// ─── Auth Service ──────────────────────────────────────────────────────────
// Login do painel admin — usuário/senha único (não é multiusuário, não tem
// permissão diferenciada). Ao logar com sucesso, o backend cria uma sessão
// via cookie (Flask, válida por 8h — ver PERMANENT_SESSION_LIFETIME no
// config.py do servidor); daqui em diante, toda chamada admin só precisa
// mandar o cookie (credentials:"include"), sem precisar guardar/repassar
// nenhuma chave manualmente (diferente do fluxo antigo, que exigia colar a
// ADMIN_API_KEY na tela — isso continua existindo, mas só pro scheduler
// automático, nunca mais pro navegador).

import { api } from "./apiService";

export async function getSessionStatus(): Promise<{ logado: boolean }> {
  return api.get<{ logado: boolean }>("/api/admin/me", undefined, "include");
}

export async function login(usuario: string, senha: string): Promise<void> {
  await api.post("/api/admin/login", { usuario, senha }, undefined, "include");
}

export async function logout(): Promise<void> {
  await api.post("/api/admin/logout", undefined, undefined, "include");
}
