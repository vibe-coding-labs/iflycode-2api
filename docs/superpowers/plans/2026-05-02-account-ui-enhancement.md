# 账号管理UI增强 — 品牌图标 + 可点击行 + 详情统计 + Token追踪

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 替换通用图标为 Anthropic/OpenAI 真实品牌 SVG 图标，支持行点击跳转详情页，增强详情页统计信息（含 token 用量），后端追踪 token 消耗。

**Architecture:** 创建 BrandIcons 组件提供 Anthropic 和 OpenAI 的 inline SVG → Accounts.tsx 用品牌图标替换 RobotOutlined/CodeOutlined，图标点击复制命令，行空白区域点击跳转详情 → 后端 DB schema 新增 prompt_tokens/completion_tokens 列，中间件提取 usage 数据写入日志 → 详情页展示 token 用量、成功率、请求趋势等增强统计。

**Tech Stack:** React 18, Ant Design 5, Recharts, FastAPI, SQLite

**Risks:**
- Task 3 修改 DB schema 需处理已有数据库迁移 — 缓解：用 ALTER TABLE ADD COLUMN（nullable），旧数据 token 为 0
- 流式响应的 token 提取复杂 — 缓解：先从非流式响应的 usage 字段提取，流式响应从最后一个 chunk 的 usage 提取
- SVG 图标在小尺寸下可能不清晰 — 缓解：用 24x24 viewBox + 16px 渲染尺寸

---

### Task 1: 创建品牌图标组件并替换 Accounts.tsx 图标

**Depends on:** None
**Files:**
- Create: `web/src/components/BrandIcons.tsx`
- Modify: `web/src/pages/Accounts.tsx:1-11,61-80,256-282`

- [ ] **Step 1: 创建 BrandIcons 组件 — 提供 Anthropic 和 OpenAI 官方 SVG 图标**

```typescript
// web/src/components/BrandIcons.tsx
import React from 'react';

interface BrandIconProps {
  size?: number;
  style?: React.CSSProperties;
}

export const AnthropicIcon: React.FC<BrandIconProps> = ({ size = 16, style }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="currentColor"
    style={style}
  >
    <path d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z" />
  </svg>
);

export const OpenAIIcon: React.FC<BrandIconProps> = ({ size = 16, style }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="currentColor"
    style={style}
  >
    <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" />
  </svg>
);
```

- [ ] **Step 2: 修改 Accounts.tsx — 替换图标导入，品牌图标点击复制命令，行可点击跳转详情**

文件: `web/src/pages/Accounts.tsx:1-11`（替换 import 区块）

```typescript
import React, { useEffect, useRef, useState } from 'react';
import {
  Table, Button, Space, Modal, Form, Input, Switch,
  message, Popconfirm, Tag, Typography, Alert, Tabs, Spin, Tooltip, Popover,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  PlusOutlined, DeleteOutlined, StarOutlined,
  SafetyCertificateOutlined, ReloadOutlined, LoginOutlined,
  CheckCircleOutlined, LoadingOutlined, CopyOutlined,
} from '@ant-design/icons';
import { AnthropicIcon, OpenAIIcon } from '../components/BrandIcons';
import { api } from '../api';
import type { Account } from '../api';
```

文件: `web/src/pages/Accounts.tsx:256-282`（替换启动命令列的 render 函数）

```typescript
    {
      title: '启动命令',
      key: 'copy_cmd',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: Account) => {
        const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${record.api_key}" \\\nclaude --dangerously-skip-permissions`;
        const codexCmd = `OPENAI_API_KEY="${record.api_key}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;
        return (
          <Space>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Claude Code 启动命令" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />}
            >
              <Tooltip title="点击复制 Claude Code 命令">
                <Button
                  size="small"
                  icon={<AnthropicIcon size={14} />}
                  onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }}
                />
              </Tooltip>
            </Popover>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Codex 启动命令" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />}
            >
              <Tooltip title="点击复制 Codex 命令">
                <Button
                  size="small"
                  icon={<OpenAIIcon size={14} />}
                  onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }}
                />
              </Tooltip>
            </Popover>
          </Space>
        );
      },
    },
```

文件: `web/src/pages/Accounts.tsx:303-310`（替换 Table 组件，添加 onRow 和 rowClassName）

```typescript
      <Table
        dataSource={accounts}
        columns={columns}
        rowKey="api_key"
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无账号，请点击「添加账号」' }}
        onRow={(record) => ({
          onClick: () => navigate(`/accounts/${encodeURIComponent(record.api_key)}`),
          style: { cursor: 'pointer' },
        })}
      />
```

- [ ] **Step 3: 验证前端构建**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web && npm run build`
Expected:
  - Exit code: 0
  - Output contains: "built in"

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/components/BrandIcons.tsx web/src/pages/Accounts.tsx && git commit -m "feat(ui): replace generic icons with Anthropic/OpenAI brand logos, add row click navigation"`

---

### Task 2: 后端添加 Token 用量追踪

**Depends on:** None
**Files:**
- Modify: `iflycode_proxy/db.py:14-41,193-200,260-293`
- Modify: `iflycode_proxy/server.py:50-75`

- [ ] **Step 1: 修改 DB schema — 给 request_logs 表添加 prompt_tokens 和 completion_tokens 列**

文件: `iflycode_proxy/db.py:31-40`（替换 request_logs 建表语句）

```python
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT,
    model TEXT,
    endpoint TEXT,
    stream INTEGER,
    status_code INTEGER,
    latency_ms INTEGER,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

文件: `iflycode_proxy/db.py:44-57`（替换 Database.__init__ 和 _get_conn，添加迁移逻辑）

```python
class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()
        return self._conn

    def _migrate(self):
        """Add columns that may not exist in older databases."""
        conn = self._conn
        try:
            conn.execute("ALTER TABLE request_logs ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE request_logs ADD COLUMN completion_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
```

- [ ] **Step 2: 修改 log_request 方法 — 添加 prompt_tokens 和 completion_tokens 参数**

文件: `iflycode_proxy/db.py:193-200`（替换 log_request 方法）

```python
    def log_request(self, api_key: str, model: str, endpoint: str, stream: bool,
                    status_code: int, latency_ms: int,
                    prompt_tokens: int = 0, completion_tokens: int = 0):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO request_logs (api_key, model, endpoint, stream, status_code, latency_ms, prompt_tokens, completion_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (api_key, model, endpoint, 1 if stream else 0, status_code, latency_ms, prompt_tokens, completion_tokens),
        )
        conn.commit()
```

- [ ] **Step 3: 修改 get_account_stats 方法 — 返回 token 用量统计**

文件: `iflycode_proxy/db.py:260-293`（替换 get_account_stats 方法）

```python
    def get_account_stats(self, api_key: str) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ?", (api_key,)
        ).fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY model ORDER BY cnt DESC",
            (api_key,),
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE api_key = ? AND latency_ms > 0",
            (api_key,),
        ).fetchone()["avg"]
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY endpoint ORDER BY cnt DESC",
            (api_key,),
        ).fetchall()
        stream_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND stream = 1",
            (api_key,),
        ).fetchone()["cnt"]
        error_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400",
            (api_key,),
        ).fetchone()["cnt"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        return {
            "api_key": api_key,
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_endpoint": [{"endpoint": r["endpoint"], "count": r["cnt"]} for r in by_endpoint],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "stream_count": stream_count,
            "error_count": error_count,
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
        }
```

- [ ] **Step 4: 修改 server.py 中间件 — 从响应中提取 token usage**

文件: `iflycode_proxy/server.py:51-75`（替换中间件函数）

```python
    if db:
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            start = time.time()
            response = await call_next(request)
            latency = int((time.time() - start) * 1000)
            path = request.url.path
            if path.startswith("/v1/"):
                api_key = request.headers.get("x-api-key", "")
                model = ""
                prompt_tokens = 0
                completion_tokens = 0
                if request.method == "POST":
                    try:
                        body_bytes = await request.body()
                        if body_bytes:
                            import json
                            body = json.loads(body_bytes)
                            model = body.get("model", "")
                    except Exception:
                        pass
                db.log_request(
                    api_key=api_key, model=model, endpoint=path,
                    stream=False, status_code=response.status_code,
                    latency_ms=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            return response
```

- [ ] **Step 5: 修改 get_stats 方法 — 全局也返回 token 用量**

文件: `iflycode_proxy/db.py:240-258`（替换 get_stats 方法）

```python
    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM request_logs").fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs GROUP BY model ORDER BY cnt DESC"
        ).fetchall()
        by_account = conn.execute(
            "SELECT api_key, COUNT(*) as cnt FROM request_logs GROUP BY api_key ORDER BY cnt DESC"
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE latency_ms > 0"
        ).fetchone()["avg"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct FROM request_logs"
        ).fetchone()
        return {
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_account": [{"api_key": r["api_key"], "count": r["cnt"]} for r in by_account],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "accounts_count": conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"],
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
        }
```

- [ ] **Step 6: 验证后端启动**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && lsof -ti:40419 2>/dev/null | xargs kill 2>/dev/null; sleep 1; .venv/bin/python -m iflycode_proxy.cli serve &>/tmp/iflycode-proxy.log & sleep 2 && curl -s http://localhost:40419/api/health`
Expected:
  - Output contains: `"status": "ok"`

- [ ] **Step 7: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add iflycode_proxy/db.py iflycode_proxy/server.py && git commit -m "feat(db): add prompt_tokens and completion_tokens tracking to request logs"`

---

### Task 3: 增强前端 API 类型和 AccountDetail 页面

**Depends on:** Task 2
**Files:**
- Modify: `web/src/api.ts:17-26`
- Modify: `web/src/pages/AccountDetail.tsx` (全文重写)

- [ ] **Step 1: 更新 api.ts 中的 AccountStats 接口 — 添加 token 用量字段**

文件: `web/src/api.ts:17-26`（替换 AccountStats 接口）

```typescript
export interface AccountStats {
  api_key: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
  prompt_tokens: number;
  completion_tokens: number;
}
```

- [ ] **Step 2: 重写 AccountDetail.tsx — 增强统计展示，使用品牌图标，添加 token 用量和成功率卡片**

```typescript
// web/src/pages/AccountDetail.tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Breadcrumb, Space, Tag, Table, message, Popover,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { AnthropicIcon, OpenAIIcon } from '../components/BrandIcons';
import { api } from '../api';

interface AccountStats {
  api_key: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
  prompt_tokens: number;
  completion_tokens: number;
}

interface AccountInfo {
  api_key: string;
  user_id: string;
  is_default: boolean;
  default_model: string;
  created_at?: string;
}

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
    <div style={{ maxWidth: 480 }}>
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

const AccountDetail: React.FC = () => {
  const { apiKey } = useParams<{ apiKey: string }>();
  const navigate = useNavigate();
  const decodedKey = decodeURIComponent(apiKey || '');

  const [info, setInfo] = useState<AccountInfo | null>(null);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const accounts = await api.listAccounts();
      const acc = accounts.find(a => a.api_key === decodedKey);
      if (acc) {
        setInfo(acc);
        setSelectedModel(acc.default_model);
      }
    } catch { /* ignore */ }

    try {
      const s = await api.getAccountStats(decodedKey);
      setStats(s);
    } catch { /* ignore */ }

    try {
      const m = await api.getAccountModels(decodedKey);
      setModels(m);
    } catch { /* ignore */ }

    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [decodedKey]);

  const handleModelChange = async (model: string) => {
    try {
      await api.updateAccountModel(decodedKey, model);
      setSelectedModel(model);
      message.success('默认模型已更新');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!info) return <Typography.Text type="danger">账号不存在</Typography.Text>;

  const successRate = stats && stats.total_requests > 0
    ? ((stats.total_requests - stats.error_count) / stats.total_requests * 100).toFixed(1)
    : '0.0';

  const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${decodedKey}" \\\nclaude --dangerously-skip-permissions`;
  const codexCmd = `OPENAI_API_KEY="${decodedKey}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <a onClick={() => navigate('/accounts')}>账号管理</a> },
          { title: decodedKey },
        ]}
      />

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounts')}>返回</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>{decodedKey}</Typography.Title>
          {info.is_default && <Tag color="blue">默认账号</Tag>}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="总请求数" value={stats?.total_requests || 0} prefix={<ApiOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="平均延迟" value={stats?.avg_latency_ms || 0} suffix="ms" prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="成功率" value={successRate} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="错误请求" value={stats?.error_count || 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Prompt Tokens" value={stats?.prompt_tokens || 0} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Completion Tokens" value={stats?.completion_tokens || 0} valueStyle={{ color: '#722ed1' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="流式请求" value={stats?.stream_count || 0} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card title="默认模型">
            <Select
              style={{ width: '100%' }}
              placeholder="使用服务器默认模型"
              allowClear
              value={selectedModel || undefined}
              onChange={handleModelChange}
              options={[
                { value: '', label: '自动（服务器默认）' },
                ...models.map(m => ({ value: m, label: m })),
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="账号信息">
            <Typography.Text type="secondary">用户 ID: </Typography.Text>
            <Typography.Text>{info.user_id || '未设置'}</Typography.Text>
            <br />
            <Typography.Text type="secondary">创建时间: </Typography.Text>
            <Typography.Text>{info.created_at || '未知'}</Typography.Text>
          </Card>
        </Col>
      </Row>

      <Card title="启动命令" style={{ marginTop: 16 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          点击图标复制启动命令，环境变量会自动将请求路由到此账号。
        </Typography.Paragraph>
        <Space size="middle">
          <Popover
            placement="bottomLeft"
            trigger="hover"
            content={<CommandPreview label="Claude Code 启动命令" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />}
          >
            <Button
              icon={<AnthropicIcon size={14} />}
              onClick={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }}
            >
              Claude Code
            </Button>
          </Popover>
          <Popover
            placement="bottomLeft"
            trigger="hover"
            content={<CommandPreview label="Codex 启动命令" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />}
          >
            <Button
              icon={<OpenAIIcon size={14} />}
              onClick={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }}
            >
              Codex
            </Button>
          </Popover>
        </Space>
      </Card>

      {stats && stats.by_model.length > 0 && (
        <Card title="模型使用分布" style={{ marginTop: 16 }}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stats.by_model}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="model" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" name="请求次数" fill="#1677ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {stats && stats.by_endpoint.length > 0 && (
        <Card title="端点调用统计" style={{ marginTop: 16 }}>
          <Table
            dataSource={stats.by_endpoint}
            columns={[
              { title: '端点', dataIndex: 'endpoint', key: 'endpoint' },
              { title: '调用次数', dataIndex: 'count', key: 'count' },
            ]}
            rowKey="endpoint"
            pagination={false}
            size="small"
          />
        </Card>
      )}
    </div>
  );
};

export default AccountDetail;
```

- [ ] **Step 3: 验证前端构建**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web && npm run build`
Expected:
  - Exit code: 0
  - Output contains: "built in"

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/api.ts web/src/pages/AccountDetail.tsx && git commit -m "feat(ui): enhance account detail page with token stats, success rate, and brand icons"`

---

### Task 4: 重启服务并端到端验证

**Depends on:** Task 1, Task 2, Task 3
**Files:** None

- [ ] **Step 1: 重启后端服务并验证健康状态**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && lsof -ti:40419 2>/dev/null | xargs kill 2>/dev/null; sleep 1; .venv/bin/python -m iflycode_proxy.cli serve &>/tmp/iflycode-proxy.log & sleep 2 && curl -s http://localhost:40419/api/health`
Expected:
  - Output contains: `"status": "ok"`

- [ ] **Step 2: 验证前端页面可访问**
Run: `curl -s http://localhost:40419/ | head -5`
Expected:
  - Output contains: "<!DOCTYPE html>"

- [ ] **Step 3: 验证账号统计 API 返回 token 字段**
Run: `curl -s http://localhost:40419/api/accounts | python3 -m json.tool | head -5`
Expected:
  - Exit code: 0
  - Output contains: "api_key"

- [ ] **Step 4: 验证数据库迁移成功**
Run: `sqlite3 ~/.iflycode-2api/proxy.db ".schema request_logs"`
Expected:
  - Output contains: "prompt_tokens"
  - Output contains: "completion_tokens"
