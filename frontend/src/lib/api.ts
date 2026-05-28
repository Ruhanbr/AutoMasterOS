import axios, { type AxiosError } from 'axios';
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from './auth';
import { isTauri, getCachedResponse, queueWrite, storeAuthToken, syncAll } from './offline';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor — attach Bearer token
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor — handle 401 / refresh
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: string) => void;
  reject: (reason: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token!);
    }
  });
  failedQueue = [];
}

// ─── Interceptor offline (Tauri only) ────────────────────────────────────────
//
// Se estiver rodando no app desktop (Tauri) e a requisição falhar por rede,
// tenta servir do cache SQLite local (leituras) ou enfileira para sync (escritas).
//
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as typeof error.config & {
      _retry?: boolean;
      _offlineFallback?: boolean;
    };

    // Erro de rede (sem error.response = servidor inacessível) + ambiente Tauri
    if (!error.response && isTauri() && !originalRequest._offlineFallback) {
      originalRequest._offlineFallback = true;
      const method = (originalRequest.method ?? 'get').toUpperCase();
      const url = originalRequest.url ?? '';
      const params = originalRequest.params as Record<string, unknown> | undefined;

      // GET: tenta o cache local
      if (method === 'GET') {
        try {
          const cached = await getCachedResponse(url, params);
          if (cached) {
            console.info('[offline] Servindo do cache local:', url);
            return {
              data: cached,
              status: 200,
              statusText: 'OK (offline cache)',
              headers: {},
              config: originalRequest,
            };
          }
        } catch {
          // sem cache — deixa o erro passar normalmente
        }
      }

      // POST/PUT/PATCH/DELETE: enfileira para sync posterior
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        const endpoint = url.replace(/^https?:\/\/[^/]+/, '').replace('/api/v1', '');
        const payload = originalRequest.data ?? '{}';
        await queueWrite(method, endpoint, payload);
        console.info('[offline] Escrita enfileirada para sync:', method, endpoint);
        return {
          data: { offline_queued: true, message: 'Salvo localmente, será sincronizado ao reconectar.' },
          status: 202,
          statusText: 'Accepted (offline queue)',
          headers: {},
          config: originalRequest,
        };
      }
    }

    const originalRequest2 = error.config as typeof error.config & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest2._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest2.headers!.Authorization = `Bearer ${token}`;
          return api(originalRequest2);
        });
      }

      originalRequest2._retry = true;
      isRefreshing = true;

      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        clearTokens();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }

      try {
        const response = await axios.post(`${API_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token } = response.data;
        setTokens(access_token, refresh_token);
        processQueue(null, access_token);
        originalRequest2.headers!.Authorization = `Bearer ${access_token}`;
        return api(originalRequest2);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearTokens();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  },
);

// ─── Dashboard ───────────────────────────────────────────────────────────────
export const dashboardApi = {
  get: () => api.get('/dashboard'),
};

// ─── Auth ────────────────────────────────────────────────────────────────────
export const authApi = {
  login: async (email: string, password: string, tenant_id?: string) => {
    const body: Record<string, string> = { email, password };
    if (tenant_id) body.tenant_id = tenant_id;
    const response = await api.post('/auth/login', body);
    // Armazena token no SQLite local (para sync offline)
    if (response.data?.access_token && isTauri()) {
      const serverUrl = process.env.NEXT_PUBLIC_API_URL?.replace('/api/v1', '') ?? 'http://localhost:8000';
      await storeAuthToken(response.data.access_token, serverUrl);
      // Dispara sync inicial em background
      syncAll(serverUrl, response.data.access_token).catch(() => null);
    }
    return response;
  },
  /** Login do Administrador Master — sem tenant_id */
  loginMaster: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  me: () => api.get('/auth/me'),
};

// ─── Tenants / Oficinas ───────────────────────────────────────────────────────
export const tenantsApi = {
  list: () => api.get('/tenants/'),
  get: (id: string) => api.get(`/tenants/${id}`),
  /** Cria oficina + admin em uma única operação, envia email com senha */
  setup: (data: unknown) => api.post('/tenants/setup', data),
  create: (data: unknown) => api.post('/tenants/', data),
  update: (id: string, data: unknown) => api.patch(`/tenants/${id}`, data),
  /** Soft-delete: desativa a oficina (dados históricos preservados) */
  delete: (id: string) => api.delete(`/tenants/${id}`),
  /** Upload de logo da oficina (PNG/JPG/WebP, máx 3 MB) */
  uploadLogo: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/tenants/${id}/logo`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  /** Remove o logo da oficina */
  deleteLogo: (id: string) => api.delete(`/tenants/${id}/logo`),
  /** Salva ou remove a chave PIX da oficina */
  updatePix: (id: string, data: { pix_key: string | null; pix_key_type: string | null }) =>
    api.patch(`/tenants/${id}/pix`, data),
};

// ─── Service Orders ───────────────────────────────────────────────────────────
export const serviceOrdersApi = {
  list: (params?: { status?: string; client_id?: string; page?: number; page_size?: number }) =>
    api.get('/service-orders', { params }),
  get: (id: string) => api.get(`/service-orders/${id}`),
  create: (data: unknown) => api.post('/service-orders', data),
  update: (id: string, data: unknown) => api.put(`/service-orders/${id}`, data),
  updateStatus: (id: string, status: string, notes?: string) =>
    api.patch(`/service-orders/${id}/status`, { status, notes }),
  /**
   * Finaliza a OS usando o endpoint completo:
   * registra receita financeira + baixa estoque + cria Invoice + dispara NF-e.
   * NÃO usar /finalize (legado) — ele não registra a entrada financeira.
   */
  finalize: (id: string, notes?: string) =>
    api.post(`/service-orders/${id}/finalize-complete`, undefined, {
      params: { notes: notes || undefined },
    }),
  // Relatório / totais agregados
  summary: (params?: { date_from?: string; date_to?: string; status?: string }) =>
    api.get('/service-orders/summary', { params }),
  // Portal do cliente / aprovação de orçamento
  sendBudget: (id: string) =>
    api.post(`/service-orders/${id}/send-budget`, {}),
  getPortalLink: (id: string) =>
    api.get(`/service-orders/${id}/portal-link`),
};

// ─── Clients ─────────────────────────────────────────────────────────────────
export const clientsApi = {
  list: (params?: { name?: string; active_only?: boolean; page?: number; page_size?: number }) =>
    api.get('/clients', { params }),
  get: (id: string) => api.get(`/clients/${id}`),
  create: (data: unknown) => api.post('/clients', data),
  update: (id: string, data: unknown) => api.patch(`/clients/${id}`, data),
  deactivate: (id: string) => api.delete(`/clients/${id}`),
  deactivatePost: (id: string) => api.post(`/clients/${id}/deactivate`),
};

// ─── Invoices ─────────────────────────────────────────────────────────────────
export const invoicesApi = {
  list: (params?: { status?: string; page?: number; page_size?: number }) =>
    api.get('/invoices', { params }),
  getByServiceOrder: (serviceOrderId: string) =>
    api.get(`/invoices/service-order/${serviceOrderId}`),
};

// ─── Stock ───────────────────────────────────────────────────────────────────
export const stockApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    api.get('/stock', { params }),
  get: (id: string) => api.get(`/stock/${id}`),
  create: (data: unknown) => api.post('/stock', data),
  update: (id: string, data: unknown) => api.put(`/stock/${id}`, data),
  delete: (id: string) => api.delete(`/stock/${id}`),
  addMovement: (id: string, data: unknown) => api.post(`/stock/${id}/movements`, data),
  listMovements: (id: string, params?: { page?: number; page_size?: number }) =>
    api.get(`/stock/${id}/movements`, { params }),
  exportExcel: () => api.get('/stock/report/excel', { responseType: 'blob' }),
};

// ─── Financial ────────────────────────────────────────────────────────────────
export const financialApi = {
  list: (params?: { entry_type?: string; date_from?: string; date_to?: string; technician_user_id?: string; page?: number; page_size?: number }) =>
    api.get('/financial', { params }),
  summary: (params?: { date_from?: string; date_to?: string; technician_user_id?: string }) =>
    api.get('/financial/summary', { params }),
  createExpense: (data: unknown) => api.post('/financial/expenses', data),
  exportExcel: (params?: { entry_type?: string; date_from?: string; date_to?: string; technician_user_id?: string }) =>
    api.get('/financial/report/excel', { params, responseType: 'blob' }),
};

// ─── Machines ────────────────────────────────────────────────────────────────
export const machinesApi = {
  /**
   * List machines.
   * client_id is sent as the X-Cliente-ID header so the backend applies
   * ownership isolation (only machines belonging to that client are returned).
   * Without client_id the full tenant list is returned (admin mode).
   */
  list: (params?: { client_id?: string; active_only?: boolean; search?: string; page?: number; page_size?: number }) => {
    const { client_id, ...queryParams } = params ?? {};
    return api.get('/machines', {
      params: queryParams,
      ...(client_id ? { headers: { 'X-Cliente-ID': client_id } } : {}),
    });
  },
  listByClient: (clientId: string, params?: { page?: number; page_size?: number }) =>
    api.get(`/machines/client/${clientId}`, { params }),
  get: (id: string) => api.get(`/machines/${id}`),
  /** Histórico de OS vinculadas a esta máquina (paginado, cache Redis 5 min). */
  listOS: (machineId: string, params?: { status?: string; page?: number; page_size?: number }) =>
    api.get(`/machines/${machineId}/os`, { params }),
  /** Totais financeiros e contagem por status do histórico de OS de uma máquina. */
  osSummary: (machineId: string, params?: { status?: string }) =>
    api.get(`/machines/${machineId}/os/summary`, { params }),
  create: (data: unknown, idempotencyKey?: string) =>
    api.post('/machines', data, idempotencyKey ? { headers: { 'X-Idempotency-Key': idempotencyKey } } : undefined),
  update: (id: string, data: unknown) => api.patch(`/machines/${id}`, data),
  deactivate: (id: string) => api.delete(`/machines/${id}`),
  reactivate: (id: string) => api.post(`/machines/${id}/reactivate`),
};

// ─── Users / Técnicos ─────────────────────────────────────────────────────────
export const usersApi = {
  list: (params?: { role?: string; active_only?: boolean }) =>
    api.get('/users', { params }),
  create: (data: { full_name: string; email: string; password: string; role: string }) =>
    api.post('/users', data),
  update: (id: string, data: { full_name?: string; email?: string; role?: string; active?: boolean }) =>
    api.put(`/users/${id}`, data),
  uploadSignature: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/users/${id}/signature`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  removeSignature: (id: string) => api.delete(`/users/${id}/signature`),
};

// ─── Reports ─────────────────────────────────────────────────────────────────
export const reportsApi = {
  downloadOsPdf: (id: string) =>
    api.get(`/service-orders/${id}/report/pdf`, { responseType: 'blob' }),
  getWhatsappLink: (id: string) =>
    api.get(`/service-orders/${id}/report/whatsapp`),
};

// ─── Notifications ───────────────────────────────────────────────────────────
export const notificationsApi = {
  list: (params?: { unread_only?: boolean }) =>
    api.get('/notifications', { params }),
  unreadCount: () =>
    api.get('/notifications/unread-count'),
  markRead: (id: string) =>
    api.post(`/notifications/${id}/read`),
  markAllRead: () =>
    api.post('/notifications/read-all'),
};

// ─── John Deere (por cliente) ─────────────────────────────────────────────────
export const deereApi = {
  getConnectUrl: (clientId: string) =>
    api.get(`/integrations/deere/connect-url?client_id=${clientId}`),
  clientStatus: (clientId: string) =>
    api.get(`/integrations/deere/clients/${clientId}/status`),
  clientDisconnect: (clientId: string) =>
    api.delete(`/integrations/deere/clients/${clientId}/disconnect`),
  clientMachines: (clientId: string) =>
    api.get(`/integrations/deere/clients/${clientId}/machines`),
  clientAlerts: (clientId: string) =>
    api.get(`/integrations/deere/clients/${clientId}/alerts`),
  clientSync: (clientId: string) =>
    api.post(`/integrations/deere/clients/${clientId}/sync`),
};
