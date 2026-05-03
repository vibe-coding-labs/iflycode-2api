# 账号详情页统计增强 — 请求统计 + Token 消耗 + 请求日志

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在账号详情页添加三大统计面板：(1) 请求统计面板含今日/总请求、成功/失败数、平均响应时间、每小时请求折线图；(2) Token 消耗面板含总消耗/24h消耗、每小时 token 折线图；(3) 最近 20 条请求日志表。

**Architecture:** 前端请求 `/api/accounts/{id}/stats` 获取汇总指标 → 请求 `/api/accounts/{id}/hourly-stats?hours=24` 获取时间序列 → 请求 `/api/accounts/{id}/recent-logs?limit=20` 获取最近日志。后端在 db.py 新增 `get_account_hourly_stats()` 和 `get_account_recent_logs()` 方法，用 SQLite `strftime('%Y-%m-%d %H:00', created_at)` 做小时级聚合。前端使用已有的 recharts LineChart 绘制折线图。

**Tech Stack:** Python 3.12, SQLite 3, FastAPI, React 19, Ant Design 6, Recharts 3.8.1, TypeScript 6

**Risks:**
- request_logs 表无索引，大量日志时聚合查询可能慢 → 缓解：查询限制最近 24h/7d，后续可加索引
- prompt_tokens/completion_tokens 当前始终为 0（middleware 未填充） → 缓解：面板显示但标注"数据待上游填充"，折线图有数据则展示无数据则空

---

### Task 1: 后端 DB 查询方法 — 新增小时级聚合和最近日志查询

**Depends on:** None
**Files:**
- Modify: `iflycode_proxy/db.py:362-405`

- [ ] **Step 1: 修改 get_account_stats 方法 — 新增今日请求和今日错误指标**

文件: `iflycode_proxy/db.py:362-405`（替换整个 get_account_stats 方法）

```python
    def get_account_stats(self, account_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        # Get api_key for this account (used as log key)
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ?", (log_key,)
        ).fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY model ORDER BY cnt DESC",
            (log_key,),
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE api_key = ? AND latency_ms > 0",
            (log_key,),
        ).fetchone()["avg"]
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY endpoint ORDER BY cnt DESC",
            (log_key,),
        ).fetchall()
        stream_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND stream = 1",
            (log_key,),
        ).fetchone()["cnt"]
        error_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400",
            (log_key,),
        ).fetchone()["cnt"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ?",
            (log_key,),
        ).fetchone()
        # Today's stats
        today_requests = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND date(created_at) = date('now')",
            (log_key,),
        ).fetchone()["cnt"]
        today_errors = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400 AND date(created_at) = date('now')",
            (log_key,),
        ).fetchone()["cnt"]
        # 24h token consumption
        token_24h = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ? AND created_at >= datetime('now', '-24 hours')",
            (log_key,),
        ).fetchone()
        return {
            "account_id": account_id,
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_endpoint": [{"endpoint": r["endpoint"], "count": r["cnt"]} for r in by_endpoint],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "stream_count": stream_count,
            "error_count": error_count,
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
            "today_requests": today_requests,
            "today_errors": today_errors,
            "today_success_rate": round((today_requests - today_errors) / today_requests * 100, 1) if today_requests > 0 else 0.0,
            "prompt_tokens_24h": token_24h["pt"],
            "completion_tokens_24h": token_24h["ct"],
        }
```

- [ ] **Step 2: 新增 get_account_hourly_stats 方法 — 小时级请求和 token 聚合**

文件: `iflycode_proxy/db.py:405` 之后（在 get_account_stats 方法结束后添加）

```python
    def get_account_hourly_stats(self, account_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Return hourly request and token stats for the last N hours."""
        conn = self._get_conn()
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        rows = conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00', created_at) as hour, "
            "  COUNT(*) as request_count, "
            "  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as error_count, "
            "  AVG(CASE WHEN latency_ms > 0 THEN latency_ms END) as avg_latency_ms, "
            "  COALESCE(SUM(prompt_tokens), 0) as prompt_tokens, "
            "  COALESCE(SUM(completion_tokens), 0) as completion_tokens "
            "FROM request_logs WHERE api_key = ? AND created_at >= datetime('now', ?) "
            "GROUP BY hour ORDER BY hour",
            (log_key, f"-{hours} hours"),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 3: 新增 get_account_recent_logs 方法 — 获取账号最近 N 条请求日志**

文件: `iflycode_proxy/db.py:424` 之后（在 get_account_hourly_stats 方法结束后添加）

```python
    def get_account_recent_logs(self, account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent request logs for an account."""
        conn = self._get_conn()
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        rows = conn.execute(
            "SELECT id, model, endpoint, stream, status_code, latency_ms, "
            "  prompt_tokens, completion_tokens, created_at "
            "FROM request_logs WHERE api_key = ? ORDER BY id DESC LIMIT ?",
            (log_key, limit),
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: 验证 DB 模块导入正常**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && python3 -c "from iflycode_proxy.db import Database; db = Database(); print('hourly_stats' in dir(db), 'recent_logs' in dir(db))"`
Expected:
  - Exit code: 0
  - Output contains: "True True"

- [ ] **Step 5: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && git add iflycode_proxy/db.py && git commit -m "feat(db): add hourly stats aggregation and recent logs query for accounts"`

---

### Task 2: 后端 API 路由 — 新增小时级统计和最近日志 endpoint

**Depends on:** Task 1
**Files:**
- Modify: `iflycode_proxy/web_api.py:66-68`

- [ ] **Step 1: 修改 web_api.py — 新增两个 API endpoint 并更新 stats 返回值**

文件: `iflycode_proxy/web_api.py:66-68`（替换 get_account_stats 并在其后添加两个新 endpoint）

```python
    @router.get("/accounts/{account_id:path}/stats")
    async def get_account_stats(account_id: str):
        return db.get_account_stats(account_id)

    @router.get("/accounts/{account_id:path}/hourly-stats")
    async def get_account_hourly_stats(account_id: str, hours: int = 24):
        if hours < 1 or hours > 720:
            hours = 24
        return {"hours": hours, "data": db.get_account_hourly_stats(account_id, hours)}

    @router.get("/accounts/{account_id:path}/recent-logs")
    async def get_account_recent_logs(account_id: str, limit: int = 20):
        if limit < 1 or limit > 100:
            limit = 20
        return {"logs": db.get_account_recent_logs(account_id, limit)}
```

- [ ] **Step 2: 验证 API endpoint 注册正常**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && python3 -c "from iflycode_proxy.web_api import create_web_api_router; from iflycode_proxy.db import Database; r = create_web_api_router(Database()); routes = [rt.path for rt in r.routes]; print('hourly-stats' in ' '.join(routes), 'recent-logs' in ' '.join(routes))"`
Expected:
  - Exit code: 0
  - Output contains: "True True"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && git add iflycode_proxy/web_api.py && git commit -m "feat(api): add hourly-stats and recent-logs endpoints for account detail page"`

---

### Task 3: 前端 API 客户端 — 新增类型和方法

**Depends on:** Task 2
**Files:**
- Modify: `web/src/api.ts:19-28`（扩展 AccountStats 类型）
- Modify: `web/src/api.ts:68-69`（新增 API 方法）

- [ ] **Step 1: 修改 AccountStats 类型 — 新增今日统计和 24h token 字段**

文件: `web/src/api.ts:19-28`

```typescript
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
```

- [ ] **Step 2: 新增 API 方法 — getAccountHourlyStats 和 getAccountRecentLogs**

文件: `web/src/api.ts:75` 之后（在 renewApiKey 方法后添加）

```typescript
  getAccountHourlyStats: (accountId: string, hours: number = 24) =>
    request<HourlyStats>(`/api/accounts/${enc(accountId)}/hourly-stats?hours=${hours}`),
  getAccountRecentLogs: (accountId: string, limit: number = 20) =>
    request<{ logs: RecentLogEntry[] }>(`/api/accounts/${enc(accountId)}/recent-logs?limit=${limit}`).then(r => r.logs),
```

- [ ] **Step 3: 验证 TypeScript 编译通过**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy/web && npx tsc --noEmit 2>&1 | head -20`
Expected:
  - Exit code: 0
  - Output does NOT contain: "error"

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && git add web/src/api.ts && git commit -m "feat(api-client): add HourlyStats, RecentLogEntry types and API methods"`

---

### Task 4: 前端 AccountDetail 页面 — 统计面板增强

**Depends on:** Task 3
**Files:**
- Modify: `web/src/pages/AccountDetail.tsx:1-365`（大幅增强统计面板）

- [ ] **Step 1: 修改 AccountDetail.tsx — 新增 import 和状态，重写统计面板**

文件: `web/src/pages/AccountDetail.tsx`（完整替换）

```typescript
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Space, Tag, Table, message, Divider, Tooltip as AntTooltip, Popconfirm,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CopyOutlined, QuestionCircleOutlined, SyncOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts';
import { SPARK_MODELS, formatContextLength, TIER_EXPLANATION } from '../data/sparkModels';
import { api } from '../api';
import type { Account, AccountStats, HourlyStatsPoint, RecentLogEntry } from '../api';

const highlightBash = (cmd: string) => {
  const tokens: { text: string; color: string }[] = [];
  const envRe = /^([A-Z_][A-Z_0-9]*)(=)/;
  const lines = cmd.split('\n');
  lines.forEach((line, li) => {
    if (li > 0) tokens.push({ text: '\n', color: '#d4d4d4' });
    let rest = line;
    while (rest) {
      const envMatch = rest.match(envRe);
      if (envMatch) {
        tokens.push({ text: envMatch[1], color: '#9cdcfe' });
        tokens.push({ text: envMatch[2], color: '#d4d4d4' });
        rest = rest.slice(envMatch[0].length);
        const valMatch = rest.match(/^("(?:[^"]*)")|([^\s\\][^\s\\]*)/);
        if (valMatch) {
          const val = valMatch[1] || valMatch[2] || '';
          tokens.push({ text: val, color: '#ce9178' });
          rest = rest.slice(val.length);
        }
        continue;
      }
      const bsMatch = rest.match(/^\\\\/);
      if (bsMatch) {
        tokens.push({ text: bsMatch[0], color: '#d4d4d4' });
        rest = rest.slice(bsMatch[0].length);
        continue;
      }
      const cmdMatch = rest.match(/^(claude|codex)\b/);
      if (cmdMatch) {
        tokens.push({ text: cmdMatch[0], color: '#4ec9b0' });
        rest = rest.slice(cmdMatch[0].length);
        continue;
      }
      const flagMatch = rest.match(/^(--?[a-zA-Z][\w-]*)/);
      if (flagMatch) {
        tokens.push({ text: flagMatch[0], color: '#569cd6' });
        rest = rest.slice(flagMatch[0].length);
        continue;
      }
      tokens.push({ text: rest[0], color: '#d4d4d4' });
      rest = rest.slice(1);
    }
  });
  return tokens;
};

const CommandPreview: React.FC<{ label: string; cmd: string; onCopy: () => void }> = ({ label, cmd, onCopy }) => {
  const tokens = React.useMemo(() => highlightBash(cmd), [cmd]);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <Typography.Text strong style={{ fontSize: 12 }}>{label}</Typography.Text>
        <Button size="small" type="link" icon={<CopyOutlined />} onClick={onCopy} style={{ padding: 0, height: 'auto', fontSize: 12 }}>
          复制
        </Button>
      </div>
      <pre style={{
        margin: 0, padding: '8px 10px', background: '#1e1e1e', borderRadius: 6,
        fontSize: 11, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
        maxHeight: 200, overflowY: 'auto',
      }}>
        {tokens.map((t, i) => <span key={i} style={{ color: t.color }}>{t.text}</span>)}
      </pre>
    </div>
  );
};

const maskKey = (key: string) => key.length > 12 ? key.slice(0, 6) + '...' + key.slice(-4) : key;

const formatHour = (h: string) => {
  const parts = h.split(' ');
  return parts.length >= 2 ? parts[1] : h;
};

const AccountDetail: React.FC = () => {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const decodedId = decodeURIComponent(accountId || '');

  const [info, setInfo] = useState<Account | null>(null);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [hourlyData, setHourlyData] = useState<HourlyStatsPoint[]>([]);
  const [recentLogs, setRecentLogs] = useState<RecentLogEntry[]>([]);
  const [models, setModels] = useState<{ modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean }[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [hourRange, setHourRange] = useState<number>(24);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const accounts = await api.listAccounts();
      const acc = accounts.find(a => a.account_id === decodedId);
      if (acc) {
        setInfo(acc);
        setSelectedModel(acc.default_model);
      }
    } catch { /* ignore */ }

    try {
      const s = await api.getAccountStats(decodedId);
      setStats(s);
    } catch { /* ignore */ }

    try {
      const h = await api.getAccountHourlyStats(decodedId, hourRange);
      setHourlyData(h.data || []);
    } catch { /* ignore */ }

    try {
      const logs = await api.getAccountRecentLogs(decodedId, 20);
      setRecentLogs(logs);
    } catch { /* ignore */ }

    try {
      const m = await api.getAccountModels(decodedId);
      setModels(m);
    } catch { /* ignore */ }

    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [decodedId]);

  useEffect(() => {
    if (!decodedId) return;
    api.getAccountHourlyStats(decodedId, hourRange)
      .then(h => setHourlyData(h.data || []))
      .catch(() => {});
  }, [hourRange]);

  const handleModelChange = async (model: string) => {
    try {
      await api.updateAccountModel(decodedId, model);
      setSelectedModel(model);
      message.success('默认模型已更新');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  };

  const handleRenewKey = async () => {
    try {
      const result = await api.renewApiKey(decodedId);
      message.success('API Key 已轮换');
      fetchData();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '轮换失败');
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!info) return <Typography.Text type="danger">账号不存在</Typography.Text>;

  const totalSuccessRate = stats && stats.total_requests > 0
    ? ((stats.total_requests - stats.error_count) / stats.total_requests * 100).toFixed(1)
    : '0.0';

  const apiKey = info.api_key;
  const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${apiKey}" \\\nclaude --dangerously-skip-permissions`;
  const codexCmd = `OPENAI_API_KEY="${apiKey}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;

  const totalTokens = (stats?.prompt_tokens || 0) + (stats?.completion_tokens || 0);
  const tokens24h = (stats?.prompt_tokens_24h || 0) + (stats?.completion_tokens_24h || 0);

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounts')}>返回</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>{info.account_id}</Typography.Title>
          {info.is_default && <Tag color="blue">默认账号</Tag>}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </div>

      {/* 1. Request Statistics */}
      <Card title="请求统计" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总请求" value={stats?.total_requests || 0} prefix={<ApiOutlined />} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="今日请求" value={stats?.today_requests || 0} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总成功率" value={totalSuccessRate} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="今日成功率" value={stats?.today_success_rate || 0} suffix="%" valueStyle={{ color: '#52c41a' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总错误" value={stats?.error_count || 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: stats?.error_count ? '#ff4d4f' : undefined }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="平均延迟" value={stats?.avg_latency_ms || 0} suffix="ms" prefix={<ThunderboltOutlined />} />
          </Col>
        </Row>
        {hourlyData.length > 0 && (
          <>
            <Divider style={{ margin: '16px 0 12px' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>每小时请求量</Typography.Text>
              <Select
                size="small"
                value={hourRange}
                onChange={setHourRange}
                style={{ width: 120 }}
                options={[
                  { value: 24, label: '最近 24 小时' },
                  { value: 48, label: '最近 48 小时' },
                  { value: 168, label: '最近 7 天' },
                ]}
              />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hourlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(l: string) => l} />
                <Legend />
                <Line type="monotone" dataKey="request_count" name="请求数" stroke="#1677ff" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="error_count" name="错误数" stroke="#ff4d4f" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      {/* 2. Token Consumption */}
      <Card title="Token 消耗" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="总 Prompt Tokens" value={stats?.prompt_tokens || 0} valueStyle={{ color: '#1677ff', fontSize: 18 }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="总 Completion Tokens" value={stats?.completion_tokens || 0} valueStyle={{ color: '#722ed1', fontSize: 18 }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="24h Prompt" value={stats?.prompt_tokens_24h || 0} valueStyle={{ color: '#1677ff' }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="24h Completion" value={stats?.completion_tokens_24h || 0} valueStyle={{ color: '#722ed1' }} />
          </Col>
        </Row>
        {hourlyData.some(h => h.prompt_tokens > 0 || h.completion_tokens > 0) && (
          <>
            <Divider style={{ margin: '16px 0 12px' }} />
            <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>每小时 Token 消耗</Typography.Text>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hourlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(l: string) => l} />
                <Legend />
                <Line type="monotone" dataKey="prompt_tokens" name="Prompt Tokens" stroke="#1677ff" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="completion_tokens" name="Completion Tokens" stroke="#722ed1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      {/* 3. Model & Account */}
      <Card title="模型与账号" style={{ marginBottom: 16 }}>
        <Row gutter={[24, 16]}>
          {/* Left: default model + account info */}
          <Col xs={24} md={8}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>默认模型</Typography.Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              placeholder="使用服务器默认模型"
              allowClear
              value={selectedModel || undefined}
              onChange={handleModelChange}
              options={[
                { value: '', label: '自动（服务器默认）' },
                ...SPARK_MODELS.map(m => {
                  const authorized = models.find(am => am.modelCode === m.domain);
                  const suffix = authorized ? '' : '（未授权）';
                  return { value: m.domain, label: `${m.name}${suffix}` };
                }),
              ]}
            />

            <Divider style={{ margin: '16px 0 12px' }} />

            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>用户 ID</Typography.Text>
              <Typography.Text>{info.user_id || '未设置'}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8 }}>创建时间</Typography.Text>
              <Typography.Text>{info.created_at || '未知'}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8 }}>流式请求数</Typography.Text>
              <Typography.Text>{stats?.stream_count || 0}</Typography.Text>

              <Divider style={{ margin: '12px 0 8px' }} />

              <Typography.Text type="secondary" style={{ fontSize: 12 }}>API Key（代理认证）</Typography.Text>
              <Space size={4}>
                <Typography.Text code>{maskKey(apiKey)}</Typography.Text>
                <Button size="small" type="link" icon={<CopyOutlined />} style={{ padding: 0, height: 'auto', minWidth: 0 }} onClick={() => { navigator.clipboard.writeText(apiKey); message.success('已复制 API Key'); }} />
              </Space>
              <Popconfirm title="轮换后旧 API Key 将立即失效，确定继续？" onConfirm={handleRenewKey}>
                <Button size="small" icon={<SyncOutlined />} style={{ marginTop: 4 }}>轮换 API Key</Button>
              </Popconfirm>
            </Space>
          </Col>

          {/* Right: model catalog table */}
          <Col xs={24} md={16}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>可用模型</Typography.Text>
              <AntTooltip title={TIER_EXPLANATION} overlayStyle={{ maxWidth: 360 }}>
                <QuestionCircleOutlined style={{ color: '#999', fontSize: 13, cursor: 'pointer' }} />
              </AntTooltip>
            </div>
            <Table
              dataSource={SPARK_MODELS.map(m => {
                const authorized = models.find(am => am.modelCode === m.domain);
                return { ...m, authorized: !!authorized, tokenExhausted: authorized?.tokenExhausted || false, key: m.domain };
              }) as any}
              columns={[
                {
                  title: '模型',
                  key: 'name',
                  render: (_: unknown, record: any) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text strong>{record.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{record.domain}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '等级',
                  key: 'tier',
                  width: 70,
                  render: (_: unknown, record: any) => {
                    if (record.tier === 'free') return <Tag color="green">免费</Tag>;
                    if (record.tier === 'premium') return <Tag color="gold">旗舰版</Tag>;
                    return <Tag color="blue">专业版</Tag>;
                  },
                },
                { title: '参数量', dataIndex: 'params', key: 'params', width: 100 },
                { title: '上下文', key: 'context', width: 60, render: (_: unknown, record: any) => formatContextLength(record.contextLength) },
                {
                  title: '能力',
                  key: 'capabilities',
                  render: (_: unknown, record: any) => (
                    <Space size={[4, 4]} wrap>
                      {record.capabilities.slice(0, 2).map((c: string) => <Tag key={c} color="blue" style={{ fontSize: 11 }}>{c}</Tag>)}
                      {record.capabilities.length > 2 && <Tag style={{ fontSize: 11 }}>+{record.capabilities.length - 2}</Tag>}
                    </Space>
                  ),
                },
                {
                  title: '状态',
                  key: 'status',
                  width: 80,
                  render: (_: unknown, record: any) => {
                    if (record.status === 'deprecated') return <Tag color="orange">下线</Tag>;
                    if (record.authorized && record.tokenExhausted) return <Tag color="red">用尽</Tag>;
                    if (record.authorized) return <Tag color="green">已授权</Tag>;
                    return <Tag>未授权</Tag>;
                  },
                },
              ]}
              pagination={false}
              size="small"
            />
          </Col>
        </Row>
      </Card>

      {/* 4. Startup Commands */}
      <Card title="启动命令" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <CommandPreview label="Claude Code" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />
          </Col>
          <Col xs={24}>
            <CommandPreview label="Codex" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />
          </Col>
        </Row>
      </Card>

      {/* 5. Recent Request Logs */}
      {recentLogs.length > 0 && (
        <Card title="最近请求日志" style={{ marginBottom: 16 }}>
          <Table
            dataSource={recentLogs}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 700 }}
            columns={[
              {
                title: '时间',
                dataIndex: 'created_at',
                key: 'created_at',
                width: 160,
                render: (v: string) => v ? v.replace('T', ' ').slice(0, 19) : '',
              },
              { title: '模型', dataIndex: 'model', key: 'model', width: 120, ellipsis: true },
              { title: '端点', dataIndex: 'endpoint', key: 'endpoint', width: 140, ellipsis: true },
              {
                title: '状态',
                dataIndex: 'status_code',
                key: 'status_code',
                width: 70,
                render: (v: number) => <Tag color={v < 400 ? 'green' : 'red'}>{v}</Tag>,
              },
              {
                title: '延迟',
                dataIndex: 'latency_ms',
                key: 'latency_ms',
                width: 80,
                render: (v: number) => `${v}ms`,
              },
              {
                title: '流式',
                dataIndex: 'stream',
                key: 'stream',
                width: 50,
                render: (v: number) => v ? '是' : '否',
              },
              {
                title: 'Tokens',
                key: 'tokens',
                width: 100,
                render: (_: unknown, r: RecentLogEntry) => {
                  const total = (r.prompt_tokens || 0) + (r.completion_tokens || 0);
                  return total > 0 ? total.toLocaleString() : '-';
                },
              },
            ]}
          />
        </Card>
      )}

      {/* 6. Analytics (model/endpoint breakdown) */}
      {(stats && (stats.by_model.length > 0 || stats.by_endpoint.length > 0)) && (
        <Card title="使用分析" style={{ marginBottom: 16 }}>
          <Row gutter={[24, 16]}>
            {stats.by_model.length > 0 && (
              <Col xs={24} md={14}>
                <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>模型使用分布</Typography.Text>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={stats.by_model}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="model" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" name="请求次数" fill="#1677ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Col>
            )}
            {stats.by_endpoint.length > 0 && (
              <Col xs={24} md={10}>
                <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>端点调用统计</Typography.Text>
                <Table
                  dataSource={stats.by_endpoint}
                  columns={[
                    { title: '端点', dataIndex: 'endpoint', key: 'endpoint' },
                    { title: '调用次数', dataIndex: 'count', key: 'count', width: 80 },
                  ]}
                  rowKey="endpoint"
                  pagination={false}
                  size="small"
                />
              </Col>
            )}
          </Row>
        </Card>
      )}
    </div>
  );
};

export default AccountDetail;
```

- [ ] **Step 2: 验证前端编译通过**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy/web && npx tsc --noEmit 2>&1 | head -20`
Expected:
  - Exit code: 0
  - Output does NOT contain: "error"

- [ ] **Step 3: 验证前端构建通过**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy/web && npm run build 2>&1 | tail -5`
Expected:
  - Exit code: 0
  - Output contains: "built in"

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && git add web/src/pages/AccountDetail.tsx && git commit -m "feat(ui): enhance account detail page with request stats, token charts, and recent logs"`
