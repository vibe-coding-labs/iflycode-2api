# iFlyCode Proxy Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 增强协议转换层（使用 openai SDK 类型替代手写 dict），并扩展前端管理能力（账号详情页、设置页、请求日志页）。

**Architecture:** openai SDK 的 Pydantic 模型用于构建/序列化 OpenAI 格式响应 → 替换 openai_handler.py 中所有手写 dict 构造 → 前端新增 3 个页面（AccountDetail、Settings、Logs）→ 路由和导航更新。后端 API 已具备大部分能力（`/api/accounts/{key}/stats`、`/api/settings`、`/api/stats/logs`），前端只需对接。

**Tech Stack:** Python 3.12+, openai SDK v1.x (Pydantic v2 模型), FastAPI 0.115+, React 19, Ant Design 6, React Router 7, Recharts 3

**Risks:**
- openai SDK 依赖较重（约 50MB），但只使用其类型定义，不影响运行时性能 → 缓解：仅 import types 模块
- AccountDetail 页面需要动态加载模型列表，免费账号可能返回空数组 → 缓解：前端处理空列表，显示"默认模型"
- 修改 openai_handler.py 可能影响现有聊天功能 → 缓解：Task 1 完成后立即验证端到端聊天

---

### Task 1: Backend — Replace hand-rolled OpenAI format with openai SDK types

**Depends on:** None
**Files:**
- Modify: `pyproject.toml:6-14`（添加 openai 依赖）
- Modify: `iflycode_proxy/openai_handler.py:1-187`（重写协议转换层）

- [ ] **Step 1: 添加 openai 依赖到 pyproject.toml**
文件: `pyproject.toml:6-14`

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "httpx>=0.28",
    "click>=8.2",
    "sse-starlette>=2.2",
    "rich>=13.7",
    "cryptography>=44.0",
    "openai>=1.0",
]
```

Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && source .venv/bin/activate && pip install "openai>=1.0" 2>&1 | tail -5`
Expected:
  - Exit code: 0
  - Output contains: "Successfully installed"

- [ ] **Step 2: 重写 openai_handler.py — 使用 openai SDK 类型构建响应**

```python
"""OpenAI-compatible API handler — translates OpenAI format to/from iFlyCode.

Uses openai SDK Pydantic types for type-safe response construction.
"""

import json
import logging
import time
from typing import Any, Iterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice, ChoiceDelta
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.completion_usage import CompletionUsage
from openai.types.model import Model

from iflycode_proxy.credential_router import CredentialRouter

log = logging.getLogger("iflycode-proxy.openai")

DEFAULT_MODEL = "iflycode-default"


def _short_id() -> str:
    return str(int(time.time() * 1e6) % 10**12)


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "type": "api_error"}})


def translate_request(req_body: dict) -> dict:
    model = req_body.get("model", "")
    stream = bool(req_body.get("stream", False))
    body: dict = {"stream": stream}
    messages = req_body.get("messages")
    if messages:
        body["messages"] = messages
    temperature = req_body.get("temperature")
    if temperature is not None:
        body["temperature"] = temperature
    return body


def _build_completion(content: str, model: str) -> ChatCompletion:
    return ChatCompletion(
        id=f"chatcmpl-{_short_id()}",
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


def _build_chunk(chat_id: str, model: str, delta: ChoiceDelta,
                 finish_reason: str | None = None) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id=chat_id,
        object="chat.completion.chunk",
        created=int(time.time()),
        model=model,
        choices=[
            ChunkChoice(index=0, delta=delta, finish_reason=finish_reason)
        ],
    )


def _stream_chat(client, body: dict, model: str) -> StreamingResponse:
    def _generate() -> Iterator[str]:
        chat_id = f"chatcmpl-{_short_id()}"
        try:
            # Initial role chunk
            role_chunk = _build_chunk(chat_id, model, ChoiceDelta(role="assistant", content=""))
            yield f"data: {role_chunk.model_dump_json()}\n\n"

            with client.chat_stream(body.get("messages", []), body) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                    else:
                        continue

                    if payload == "[DONE]":
                        continue

                    try:
                        chunk_data = json.loads(payload)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    reasoning = delta.get("reasoning_content", "")
                    finish_reason = choices[0].get("finish_reason")

                    if content:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=content))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if reasoning and not content:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(content=f"[think]{reasoning}[/think]"))
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

                    if finish_reason:
                        out_chunk = _build_chunk(chat_id, model, ChoiceDelta(), finish_reason=finish_reason)
                        yield f"data: {out_chunk.model_dump_json()}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as exc:
            error_payload = json.dumps({"error": {"message": str(exc)}})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close", "X-Accel-Buffering": "no"},
    )


def _stream_chat_non_streaming(client, body: dict, model: str) -> JSONResponse:
    full_content = ""
    reasoning_content = ""

    with client.chat_stream(body.get("messages", []), body) as resp:
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data:"):
                payload = line[5:].strip()
            else:
                continue
            if payload == "[DONE]":
                continue
            try:
                chunk_data = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue
            choices = chunk_data.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                full_content += delta["content"]
            if delta.get("reasoning_content"):
                reasoning_content += delta["reasoning_content"]

    final = f"[think]{reasoning_content}[/think]\n\n{full_content}" if reasoning_content else full_content
    completion = _build_completion(final, model)
    return JSONResponse(content=completion.model_dump(mode="json"))


def create_openai_router(cred_router: CredentialRouter) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        api_key = request.headers.get("x-api-key", "")
        try:
            client = cred_router.get_client(api_key or None)
        except KeyError:
            return _error_response("No account available. Add an account via /api/accounts first.", 401)

        try:
            req_body = await request.json()
        except Exception:
            return _error_response("invalid JSON", 400)

        model = req_body.get("model", DEFAULT_MODEL)
        jc_body = translate_request(req_body)

        if jc_body.get("stream"):
            return _stream_chat(client, jc_body, model)

        return _stream_chat_non_streaming(client, jc_body, model)

    @router.get("/v1/models")
    async def list_models() -> Any:
        model_ids = ["iflycode-default", "gpt-4", "gpt-4o"]
        models = [
            Model(id=m, object="model", created=1700000000, owned_by="iflycode")
            for m in model_ids
        ]
        return JSONResponse(content={"object": "list", "data": [m.model_dump(mode="json") for m in models]})

    @router.get("/health")
    async def health() -> Any:
        return JSONResponse(content={
            "status": "ok",
            "service": "iflycode-openai-proxy",
            "accounts": len(cred_router.list_accounts()),
            "endpoints": ["/v1/chat/completions", "/v1/models"],
        })

    return router
```

- [ ] **Step 3: 验证后端启动和 API 响应格式**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && lsof -ti:40419 2>/dev/null | xargs kill -9 2>/dev/null; source .venv/bin/activate && python -m iflycode_proxy.cli serve &>/tmp/iflycode-proxy.log & sleep 2 && curl -s http://localhost:40419/v1/models | python3 -m json.tool`
Expected:
  - Exit code: 0
  - Output contains: "iflycode-default" and "owned_by"
  - Server log contains no traceback

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add pyproject.toml iflycode_proxy/openai_handler.py && git commit -m "refactor(proxy): use openai SDK types for protocol format conversion"`

---

### Task 2: Frontend — Add AccountDetail page with per-account stats and model config

**Depends on:** None
**Files:**
- Create: `web/src/pages/AccountDetail.tsx`

- [ ] **Step 1: 创建 AccountDetail 页面 — 展示账号详情、统计、模型配置**

```tsx
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Breadcrumb, Space, Tag, Table, message,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api';

interface AccountStats {
  api_key: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
}

interface AccountInfo {
  api_key: string;
  user_id: string;
  is_default: boolean;
  default_model: string;
  created_at?: string;
}

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
          <Card><Statistic title="成功请求" value={(stats?.total_requests || 0) - (stats?.error_count || 0)} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="错误请求" value={stats?.error_count || 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card>
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

- [ ] **Step 2: 验证 TypeScript 编译**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web && npx tsc --noEmit 2>&1 | head -20`
Expected:
  - Exit code: 0 or errors only about missing api methods (fixed in Task 5)

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/pages/AccountDetail.tsx && git commit -m "feat(web): add AccountDetail page with stats and model config"`

---

### Task 3: Frontend — Add Settings page

**Depends on:** None
**Files:**
- Create: `web/src/pages/Settings.tsx`

- [ ] **Step 1: 创建 Settings 页面 — 代理服务配置管理**

```tsx
import React, { useEffect, useState } from 'react';
import {
  Card, Form, Input, InputNumber, Switch, Button, Space, message, Spin, Typography,
} from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../api';

interface SettingGroup {
  title: string;
  items: SettingItem[];
}

interface SettingItem {
  key: string;
  label: string;
  type: 'text' | 'number' | 'switch' | 'select';
  placeholder?: string;
  tooltip?: string;
  options?: { value: string; label: string }[];
  defaultValue?: string | number | boolean;
}

const SETTING_GROUPS: SettingGroup[] = [
  {
    title: '网络配置',
    items: [
      { key: 'base_url', label: 'iFlyCode API 地址', type: 'text', placeholder: 'https://iflycode-xfsaas.xfyun.cn', tooltip: 'iFlyCode 服务的基础 URL' },
      { key: 'proxy_host', label: '代理监听地址', type: 'text', placeholder: '0.0.0.0', tooltip: '代理服务器绑定的主机地址' },
      { key: 'proxy_port', label: '代理监听端口', type: 'number', placeholder: 40419, tooltip: '代理服务器绑定的端口' },
    ],
  },
  {
    title: '模型配置',
    items: [
      { key: 'default_model', label: '默认模型', type: 'text', placeholder: '留空使用服务器默认', tooltip: '未指定模型时使用的默认模型' },
      { key: 'max_tokens', label: '最大 Token 数', type: 'number', placeholder: 8000, tooltip: '单次请求的最大 token 数' },
    ],
  },
  {
    title: '连接优化',
    items: [
      { key: 'connect_timeout', label: '连接超时 (秒)', type: 'number', placeholder: 10, tooltip: '与 iFlyCode 建立连接的超时时间' },
      { key: 'read_timeout', label: '读取超时 (秒)', type: 'number', placeholder: 120, tooltip: '等待响应数据的超时时间' },
      { key: 'max_retries', label: '最大重试次数', type: 'number', placeholder: 2, tooltip: '请求失败后的最大重试次数' },
    ],
  },
  {
    title: '日志与安全',
    items: [
      { key: 'log_enabled', label: '请求日志', type: 'switch', tooltip: '记录所有 API 请求到数据库', defaultValue: true },
      { key: 'log_retention_days', label: '日志保留天数', type: 'number', placeholder: 30, tooltip: '超过此天数的日志将自动清理' },
    ],
  },
];

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = await api.getSettings();
      const values: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(data)) {
        if (val === 'true') values[key] = true;
        else if (val === 'false') values[key] = false;
        else if (/^\d+$/.test(val)) values[key] = parseInt(val, 10);
        else values[key] = val;
      }
      form.setFieldsValue(values);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchSettings(); }, []);

  const handleSave = async (values: Record<string, unknown>) => {
    setSaving(true);
    try {
      const payload: Record<string, string> = {};
      for (const [key, val] of Object.entries(values)) {
        if (val === undefined || val === null) continue;
        payload[key] = String(val);
      }
      await api.updateSettings(payload);
      message.success('设置已保存');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>系统设置</Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={fetchSettings}>重置</Button>
      </div>

      <Form form={form} layout="vertical" onFinish={handleSave}>
        {SETTING_GROUPS.map(group => (
          <Card key={group.title} title={group.title} style={{ marginBottom: 16 }}>
            {group.items.map(item => (
              <Form.Item
                key={item.key}
                name={item.key}
                label={item.label}
                tooltip={item.tooltip}
                valuePropName={item.type === 'switch' ? 'checked' : 'value'}
              >
                {item.type === 'text' && <Input placeholder={item.placeholder} />}
                {item.type === 'number' && <InputNumber style={{ width: '100%' }} placeholder={String(item.placeholder)} />}
                {item.type === 'switch' && <Switch />}
                {item.type === 'select' && (
                  <Select placeholder={String(item.placeholder || '')} options={item.options} />
                )}
              </Form.Item>
            ))}
          </Card>
        ))}

        <Space>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存设置</Button>
        </Space>
      </Form>
    </div>
  );
};

export default Settings;
```

- [ ] **Step 2: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/pages/Settings.tsx && git commit -m "feat(web): add Settings page for proxy configuration"`

---

### Task 4: Frontend — Add Request Logs page

**Depends on:** None
**Files:**
- Create: `web/src/pages/Logs.tsx`

- [ ] **Step 1: 创建 Request Logs 页面 — 展示请求历史记录**

```tsx
import React, { useEffect, useState } from 'react';
import {
  Table, Typography, Tag, Button, InputNumber, Space, Spin,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { api } from '../api';

interface LogEntry {
  id: number;
  api_key: string;
  model: string;
  endpoint: string;
  stream: number;
  status_code: number;
  latency_ms: number;
  created_at: string;
}

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState(200);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await api.getLogs(limit);
      setLogs(data);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchLogs(); }, []);

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
    },
    {
      title: '账号',
      dataIndex: 'api_key',
      key: 'api_key',
      width: 150,
      render: (text: string) => <Typography.Text code>{text || '-'}</Typography.Text>,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      width: 150,
      render: (text: string) => text || <Tag>默认</Tag>,
    },
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      width: 200,
    },
    {
      title: '流式',
      dataIndex: 'stream',
      key: 'stream',
      width: 80,
      render: (v: number) => v ? <Tag color="blue">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 100,
      render: (v: number) => {
        const color = v < 400 ? 'green' : v < 500 ? 'orange' : 'red';
        return <Tag color={color}>{v}</Tag>;
      },
    },
    {
      title: '延迟',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 100,
      render: (v: number) => `${v}ms`,
      sorter: (a: LogEntry, b: LogEntry) => a.latency_ms - b.latency_ms,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>请求日志</Typography.Title>
        <Space>
          <span>显示条数:</span>
          <InputNumber min={10} max={1000} value={limit} onChange={v => setLimit(v || 100)} />
          <Button icon={<ReloadOutlined />} onClick={fetchLogs}>刷新</Button>
        </Space>
      </div>

      <Table
        dataSource={logs}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20, showTotal: total => `共 ${total} 条` }}
        locale={{ emptyText: '暂无请求记录' }}
        scroll={{ x: 960 }}
        size="small"
      />
    </div>
  );
};

export default Logs;
```

- [ ] **Step 2: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/pages/Logs.tsx && git commit -m "feat(web): add Request Logs page with pagination"`

---

### Task 5: Frontend — Update API client, routing, layout and Accounts page navigation

**Depends on:** Task 2, Task 3, Task 4
**Files:**
- Modify: `web/src/api.ts:1-41`（添加新 API 方法）
- Modify: `web/src/App.tsx:1-25`（添加新路由）
- Modify: `web/src/layouts/MainLayout.tsx:1-43`（添加菜单项）
- Modify: `web/src/pages/Accounts.tsx:82-119`（添加点击跳转详情）

- [ ] **Step 1: 更新 API 客户端 — 添加新的 API 方法**
文件: `web/src/api.ts:1-41`（替换整个文件）

```typescript
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
  getLogs: (limit: number = 100) =>
    request<{ logs: LogEntry[] }>('/api/stats/logs?limit=' + limit).then(r => r.logs),

  // Settings
  getSettings: () => request<Record<string, string>>('/api/settings').then(r => r.settings || {}),
  updateSettings: (data: Record<string, string>) =>
    request<{ ok: boolean }>('/api/settings', { method: 'PUT', body: JSON.stringify(data) }),

  // Health
  getHealth: () => request<{ status: string; accounts: number }>('/api/health'),
};
```

- [ ] **Step 2: 更新路由配置 — 添加新页面路由**
文件: `web/src/App.tsx:1-25`（替换整个文件）

```tsx
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Accounts = lazy(() => import('./pages/Accounts'));
const AccountDetail = lazy(() => import('./pages/AccountDetail'));
const Settings = lazy(() => import('./pages/Settings'));
const Logs = lazy(() => import('./pages/Logs'));

const pageLoading = <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

const App: React.FC = () => (
  <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#1677ff' } }}>
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Suspense fallback={pageLoading}><Dashboard /></Suspense>} />
          <Route path="/accounts" element={<Suspense fallback={pageLoading}><Accounts /></Suspense>} />
          <Route path="/accounts/:apiKey" element={<Suspense fallback={pageLoading}><AccountDetail /></Suspense>} />
          <Route path="/settings" element={<Suspense fallback={pageLoading}><Settings /></Suspense>} />
          <Route path="/logs" element={<Suspense fallback={pageLoading}><Logs /></Suspense>} />
        </Route>
      </Routes>
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
```

- [ ] **Step 3: 更新侧边栏导航 — 添加新菜单项**
文件: `web/src/layouts/MainLayout.tsx:1-43`（替换整个文件）

```tsx
import React from 'react';
import { Layout, Menu } from 'antd';
import { DashboardOutlined, TeamOutlined, SettingOutlined, FileTextOutlined } from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';

const { Header, Content, Sider } = Layout;

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = location.pathname === '/accounts' || location.pathname.startsWith('/accounts/')
    ? '/accounts'
    : location.pathname;

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '数据概览' },
    { key: '/accounts', icon: <TeamOutlined />, label: '账号管理' },
    { key: '/logs', icon: <FileTextOutlined />, label: '请求日志' },
    { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={0}>
        <div style={{ height: 32, margin: 16, color: '#fff', fontSize: 18, fontWeight: 'bold', textAlign: 'center' }}>
          iFlyCode
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', fontSize: 16, fontWeight: 500 }}>
          iFlyCode OpenAI Proxy
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
```

- [ ] **Step 4: 更新 Accounts 页面 — 添加点击跳转到详情**
文件: `web/src/pages/Accounts.tsx:82-119`（替换 columns 定义，在 api_key 列添加点击跳转）

在 Accounts.tsx 顶部 import 中添加 `useNavigate`:
文件: `web/src/pages/Accounts.tsx:3`

```typescript
import { useNavigate } from 'react-router-dom';
```

在组件内部（`const [validating, setValidating] = useState<string | null>(null);` 之后）添加:
```typescript
const navigate = useNavigate();
```

修改 columns 中 api_key 列的 render（替换第 87 行）:
```typescript
render: (text: string) => (
  <Typography.Text
    code
    style={{ cursor: 'pointer' }}
    onClick={() => navigate(`/accounts/${encodeURIComponent(text)}`)}
  >
    {text}
  </Typography.Text>
),
```

- [ ] **Step 5: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add web/src/api.ts web/src/App.tsx web/src/layouts/MainLayout.tsx web/src/pages/Accounts.tsx && git commit -m "feat(web): update routing, navigation, and API client for new pages"`

---

### Task 6: Backend — Add account models endpoint

**Depends on:** Task 1
**Files:**
- Modify: `iflycode_proxy/web_api.py:47-61`（添加 models 端点）

- [ ] **Step 1: 在 web_api.py 中添加获取账号模型列表的端点**
文件: `iflycode_proxy/web_api.py:50-57`（在 validate_account 端点之后，update_account_model 端点之前插入）

在 `validate_account` 函数之后（第 50 行后）添加:

```python
    @router.get("/accounts/{api_key:path}/models")
    async def list_account_models(api_key: str):
        models = db.get_account_models(api_key)
        return {"models": models}
```

- [ ] **Step 2: 在 db.py 中添加 get_account_models 方法**
文件: `iflycode_proxy/db.py:169-170`（在 validate_account 方法之后添加）

```python
    def get_account_models(self, api_key: str) -> List[str]:
        acc = self.get_account(api_key)
        if not acc:
            return []
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["token"], acc.get("user_id", ""))
            models_data = client.list_models()
            client.close()
            return [m.get("modelCode", m.get("name", "")) for m in models_data if m.get("modelCode") or m.get("name")]
        except Exception:
            return []
```

- [ ] **Step 3: 验证新端点可访问**
Run: `curl -s http://localhost:40419/api/accounts/nonexistent/models | python3 -m json.tool`
Expected:
  - Exit code: 0
  - Output: `{"models": []}`

- [ ] **Step 4: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add iflycode_proxy/web_api.py iflycode_proxy/db.py && git commit -m "feat(api): add per-account model list endpoint"`

---

### Task 7: Build frontend and end-to-end verification

**Depends on:** Task 1, Task 2, Task 3, Task 4, Task 5, Task 6
**Files:**
- Rebuild: `iflycode_proxy/static/`（构建产物）

- [ ] **Step 1: 构建前端**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web && npm run build 2>&1`
Expected:
  - Exit code: 0
  - Output contains: "built in"

- [ ] **Step 2: 重启后端并验证所有页面可访问**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && lsof -ti:40419 2>/dev/null | xargs kill -9 2>/dev/null; source .venv/bin/activate && python -m iflycode_proxy.cli serve &>/tmp/iflycode-proxy.log & sleep 2 && curl -s http://localhost:40419/ | head -5 && echo "---" && curl -s http://localhost:40419/api/health | python3 -m json.tool && echo "---" && curl -s http://localhost:40419/api/stats/logs | python3 -m json.tool && echo "---" && curl -s http://localhost:40419/api/settings | python3 -m json.tool`
Expected:
  - Frontend HTML loads
  - health returns `{"status": "ok", ...}`
  - stats/logs returns `{"logs": [...]}`
  - settings returns `{"settings": {...}}`

- [ ] **Step 3: 推送所有更改**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git push origin main 2>&1`
Expected:
  - Exit code: 0
  - Output contains: "main -> main"
