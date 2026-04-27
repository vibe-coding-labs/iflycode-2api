export interface Account {
  api_key: string;
  user_id: string;
  is_default: boolean;
  default_model: string;
  created_at?: string;
}

export interface Stats {
  total_requests: number;
  accounts_count: number;
  avg_latency_ms: number;
  by_model: { model: string; count: number }[];
  by_account: { api_key: string; count: number }[];
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export const api = {
  listAccounts: () => request<{ accounts: Account[] }>('/api/accounts').then(r => r.accounts),
  addAccount: (data: { api_key: string; token: string; user_id?: string; is_default?: boolean }) =>
    request<{ ok: boolean }>('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  removeAccount: (apiKey: string) =>
    request<{ ok: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}`, { method: 'DELETE' }),
  setDefault: (apiKey: string) =>
    request<{ ok: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}/default`, { method: 'PUT' }),
  validateAccount: (apiKey: string) =>
    request<{ valid: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}/validate`, { method: 'POST' }),
  getStats: () => request<Stats>('/api/stats'),
  getHealth: () => request<{ status: string; accounts: number }>('/api/health'),
};
