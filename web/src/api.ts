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

export interface AccountStats {
  api_key: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
}

export interface LogEntry {
  id: number;
  api_key: string;
  model: string;
  endpoint: string;
  stream: number;
  status_code: number;
  latency_ms: number;
  created_at: string;
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
  // Accounts
  listAccounts: () => request<{ accounts: Account[] }>('/api/accounts').then(r => r.accounts),
  addAccount: (data: { api_key: string; token: string; user_id?: string; is_default?: boolean }) =>
    request<{ ok: boolean }>('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  removeAccount: (apiKey: string) =>
    request<{ ok: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}`, { method: 'DELETE' }),
  setDefault: (apiKey: string) =>
    request<{ ok: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}/default`, { method: 'PUT' }),
  validateAccount: (apiKey: string) =>
    request<{ valid: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}/validate`, { method: 'POST' }),
  getAccountStats: (apiKey: string) =>
    request<AccountStats>(`/api/accounts/${encodeURIComponent(apiKey)}/stats`),
  getAccountModels: (apiKey: string) =>
    request<{ models: string[] }>(`/api/accounts/${encodeURIComponent(apiKey)}/models`).then(r => r.models || []),
  updateAccountModel: (apiKey: string, model: string) =>
    request<{ ok: boolean }>(`/api/accounts/${encodeURIComponent(apiKey)}/model`, { method: 'PUT', body: JSON.stringify({ default_model: model }) }),

  // Stats
  getStats: () => request<Stats>('/api/stats'),
  getLogs: (limit: number = 100, filters?: { api_key?: string; model?: string; status?: number }) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filters?.api_key) params.set('api_key', filters.api_key);
    if (filters?.model) params.set('model', filters.model);
    if (filters?.status) params.set('status', String(filters.status));
    return request<{ logs: LogEntry[] }>(`/api/stats/logs?${params}`).then(r => r.logs);
  },
  cleanupLogs: (retentionDays: number = 30) =>
    request<{ ok: boolean; removed: number }>('/api/stats/logs/cleanup', { method: 'POST', body: JSON.stringify({ retention_days: retentionDays }) }),

  // Settings
  getSettings: () => request<Record<string, string>>('/api/settings').then(r => r.settings || {}),
  updateSettings: (data: Record<string, string>) =>
    request<{ ok: boolean }>('/api/settings', { method: 'PUT', body: JSON.stringify(data) }),

  // Health
  getHealth: () => request<{ status: string; accounts: number; version: string }>('/api/health'),
};
