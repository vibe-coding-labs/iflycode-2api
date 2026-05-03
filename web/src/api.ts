export interface Account {
  account_id: string;
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
  prompt_tokens: number;
  completion_tokens: number;
  all_time: {
    total_requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    error_count: number;
  };
  today_requests: number;
  today_success_count: number;
  today_error_count: number;
  today_stream_count: number;
  today_avg_latency_ms: number;
  today_prompt_tokens: number;
  today_completion_tokens: number;
  today_by_model: { model: string; count: number }[];
  today_by_account: { api_key: string; count: number }[];
  hourly: {
    hour: string;
    count: number;
    input_tokens: number;
    output_tokens: number;
    errors: number;
  }[];
}

export interface AccountStats {
  account_id: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  today_requests: number;
  today_errors: number;
  today_success_rate: number;
  prompt_tokens_24h: number;
  completion_tokens_24h: number;
}

export interface HourlyStatsPoint {
  hour: string;
  request_count: number;
  error_count: number;
  avg_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface HourlyStats {
  hours: number;
  data: HourlyStatsPoint[];
}

export interface RecentLogEntry {
  id: number;
  model: string;
  endpoint: string;
  stream: number;
  status_code: number;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
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

function enc(s: string) {
  return encodeURIComponent(s);
}

export const api = {
  // Accounts
  listAccounts: () => request<{ accounts: Account[] }>('/api/accounts').then(r => r.accounts),
  addAccount: (data: { account_id?: string; api_key?: string; spark_token: string; user_id?: string; is_default?: boolean }) =>
    request<{ ok: boolean; account_id: string; api_key: string }>('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  removeAccount: (accountId: string) =>
    request<{ ok: boolean }>(`/api/accounts/${enc(accountId)}`, { method: 'DELETE' }),
  setDefault: (accountId: string) =>
    request<{ ok: boolean }>(`/api/accounts/${enc(accountId)}/default`, { method: 'PUT' }),
  validateAccount: (accountId: string) =>
    request<{ valid: boolean }>(`/api/accounts/${enc(accountId)}/validate`, { method: 'POST' }),
  getAccountStats: (accountId: string) =>
    request<AccountStats>(`/api/accounts/${enc(accountId)}/stats`),
  getAccountModels: (accountId: string) =>
    request<{ models: { modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean; permissionCode: string; permissionName: string; language: string }[] }>(`/api/accounts/${enc(accountId)}/models`).then(r => r.models || []),
  updateAccountModel: (accountId: string, model: string) =>
    request<{ ok: boolean }>(`/api/accounts/${enc(accountId)}/model`, { method: 'PUT', body: JSON.stringify({ default_model: model }) }),
  renewApiKey: (accountId: string) =>
    request<{ ok: boolean; account_id: string; api_key: string }>(`/api/accounts/${enc(accountId)}/renew-key`, { method: 'POST' }),
  getAccountHourlyStats: (accountId: string, hours: number = 24) =>
    request<HourlyStats>(`/api/accounts/${enc(accountId)}/hourly-stats?hours=${hours}`),
  getAccountRecentLogs: (accountId: string, limit: number = 20) =>
    request<{ logs: RecentLogEntry[] }>(`/api/accounts/${enc(accountId)}/recent-logs?limit=${limit}`).then(r => r.logs),

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

  // SSO Auth
  getLoginUrl: () =>
    request<{ ok: boolean; login_url: string; client_id: string }>('/api/auth/login-url', { method: 'POST' }),
  pollLoginStatus: (clientId: string) =>
    request<{ ok: boolean; status: string; token?: string; user_id?: string }>(`/api/auth/login-status?client_id=${enc(clientId)}`),
  addAccountFromSSO: (data: { token: string; user_id?: string }) =>
    request<{ ok: boolean; account_id: string; api_key: string }>('/api/auth/add-from-sso', { method: 'POST', body: JSON.stringify(data) }),
};
