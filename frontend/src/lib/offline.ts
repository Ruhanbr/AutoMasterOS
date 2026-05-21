// ─────────────────────────────────────────────────────────────────────────────
// offline.ts — Bridge entre Next.js e Tauri para suporte offline
// ─────────────────────────────────────────────────────────────────────────────

// ── Detecção de ambiente ──────────────────────────────────────────────────────

/** Retorna true se o código está rodando dentro do app Tauri (desktop). */
export const isTauri = (): boolean =>
  typeof window !== 'undefined' && '__TAURI__' in window;

/** Retorna true se o navegador/OS reporta conexão ativa. */
export const isOnline = (): boolean =>
  typeof navigator !== 'undefined' ? navigator.onLine : true;

// ── Invoke wrapper ────────────────────────────────────────────────────────────

/**
 * Chama um comando Tauri (Rust) de dentro do Next.js.
 * Usa window.__TAURI__.core.invoke (injetado via withGlobalTauri: true).
 */
export async function invoke<T = unknown>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error(`[offline] invoke('${command}') chamado fora do Tauri`);
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tauri = (window as any).__TAURI__;
  return tauri.core.invoke(command, args) as Promise<T>;
}

// ── Auth token ────────────────────────────────────────────────────────────────

/**
 * Armazena o token JWT no SQLite local (para sync automático).
 * Deve ser chamado após o login bem-sucedido.
 */
export async function storeAuthToken(token: string, serverUrl: string): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('store_auth_token', { token, serverUrl });
  } catch (e) {
    console.warn('[offline] Não foi possível salvar auth token:', e);
  }
}

/** Limpa o token do SQLite local (ao fazer logout). */
export async function clearAuthToken(): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('clear_auth_token');
  } catch (e) {
    console.warn('[offline] Não foi possível limpar auth token:', e);
  }
}

// ── Sync ──────────────────────────────────────────────────────────────────────

export interface SyncStatus {
  online: boolean;
  pending: number;
  last_sync: string | null;
  server_url: string;
}

export interface SyncPullResult {
  clients: number;
  machines: number;
  service_orders: number;
  last_sync: string;
}

export interface SyncPushResult {
  pushed: number;
  failed: number;
}

/** Retorna o status atual de sincronização. */
export async function getSyncStatus(): Promise<SyncStatus | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<SyncStatus>('get_sync_status');
  } catch {
    return null;
  }
}

/**
 * Baixa todos os dados do servidor para o SQLite local.
 * Deve ser chamado ao iniciar o app e periodicamente.
 */
export async function syncPull(serverUrl: string, token: string): Promise<SyncPullResult | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<SyncPullResult>('sync_pull', { serverUrl, token });
  } catch (e) {
    console.warn('[offline] sync_pull falhou:', e);
    return null;
  }
}

/**
 * Envia escritas em fila (feitas offline) para o servidor.
 * Deve ser chamado quando a conexão for restaurada.
 */
export async function syncPush(serverUrl: string, token: string): Promise<SyncPushResult | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<SyncPushResult>('sync_push', { serverUrl, token });
  } catch (e) {
    console.warn('[offline] sync_push falhou:', e);
    return null;
  }
}

/**
 * Sincronização completa: push pending → pull fresh data.
 * Exposta globalmente como window.__AUTOMASTER_SYNC para o tray menu.
 */
export async function syncAll(serverUrl: string, token: string) {
  const push = await syncPush(serverUrl, token);
  const pull = await syncPull(serverUrl, token);
  return { push, pull };
}

// ── Leituras offline ──────────────────────────────────────────────────────────

/** Busca clientes do cache local (SQLite). */
export async function localGetClients(search?: string) {
  return invoke('local_get_clients', { search: search ?? null });
}

/** Busca máquinas do cache local. */
export async function localGetMachines(clientId?: string) {
  return invoke('local_get_machines', { clientId: clientId ?? null });
}

/** Busca ordens de serviço do cache local. */
export async function localGetServiceOrders(status?: string) {
  return invoke('local_get_service_orders', { status: status ?? null });
}

// ── Enfileirar escrita offline ────────────────────────────────────────────────

/**
 * Enfileira uma operação de escrita para sincronizar quando houver rede.
 * @param method  HTTP method (POST, PUT, PATCH, DELETE)
 * @param endpoint  path relativo, ex: /service-orders
 * @param payload   corpo da requisição como string JSON
 */
export async function queueWrite(
  method: string,
  endpoint: string,
  payload: unknown,
): Promise<number | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<number>('queue_write', {
      method,
      endpoint,
      payload: typeof payload === 'string' ? payload : JSON.stringify(payload),
    });
  } catch (e) {
    console.warn('[offline] queue_write falhou:', e);
    return null;
  }
}

// ── Mapeamento URL → comando local ────────────────────────────────────────────

/**
 * Tenta servir uma resposta do cache local baseado na URL da API.
 * Retorna null se não houver mapeamento ou o cache estiver vazio.
 */
export async function getCachedResponse(url: string, params?: Record<string, unknown>) {
  if (!isTauri()) return null;

  const path = url.replace(/^https?:\/\/[^/]+/, '').replace('/api/v1', '');

  if (path.startsWith('/clients') || path.startsWith('/clientes')) {
    const search = params?.name as string | undefined;
    return localGetClients(search);
  }

  if (path.startsWith('/machines') || path.startsWith('/maquinas')) {
    const clientId = (params?.client_id ?? params?.clientId) as string | undefined;
    return localGetMachines(clientId);
  }

  if (path.startsWith('/service-orders') || path.startsWith('/ordens')) {
    const status = params?.status as string | undefined;
    return localGetServiceOrders(status);
  }

  return null;
}
