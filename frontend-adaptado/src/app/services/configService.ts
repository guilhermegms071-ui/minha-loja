// ─── Config Service ───────────────────────────────────────────────────────
// Configurações da loja editáveis pelo lojista no painel admin (textos do
// menu, horário, endereço, telefone do atendente, IA, pedido mínimo,
// desconto) — substituem regras que antes só existiam hardcoded/no .env do
// servidor. NUNCA inclui credencial nenhuma (Client Secret do Bling, chave
// de IA, token do WhatsApp) — essas continuam só no .env, fora do alcance
// deste painel.

import { api } from "./apiService";

export interface Configuracoes {
  textoSaudacao: string;
  textoMenuComprar: string;
  textoMenuAssistencia: string;
  textoSobreLoja: string;
  horarioFuncionamento: string;
  enderecoLoja: string;
  atendentePagamentoTelefone: string;
  // null = segue o AI_ENABLED do .env (o lojista nunca mexeu nesse campo)
  iaHabilitada: boolean | null;
  pedidoMinimo: number;
  descontoPadraoPercentual: number;
}

export async function getConfiguracoes(adminKey: string): Promise<Configuracoes> {
  return api.get<Configuracoes>("/api/admin/configuracoes", { "X-Admin-Key": adminKey });
}

/** Atualiza só os campos passados em `dados` — os demais mantêm o valor atual. */
export async function atualizarConfiguracoes(
  adminKey: string,
  dados: Partial<Configuracoes>
): Promise<Configuracoes> {
  return api.put<Configuracoes>("/api/admin/configuracoes", dados, { "X-Admin-Key": adminKey });
}
