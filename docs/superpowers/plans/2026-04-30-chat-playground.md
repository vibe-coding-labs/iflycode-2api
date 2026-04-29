# Chat Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在管理界面中添加聊天测试页面，用户可选择账号和模型，通过 OpenAI 兼容的 `/v1/chat/completions` 端点与 AI 对话，用于验证账号和模型是否正常工作。

**Architecture:** 用户选择账号 → 前端通过 `x-api-key` header 调用 `/v1/chat/completions`（stream: true）→ 解析 SSE 流逐字渲染 AI 回复 → 支持多轮对话。复用现有 OpenAI 兼容端点，无需后端改动。

**Tech Stack:** React 19, Ant Design 6, TypeScript 6, Vite 8（前端已有依赖，无需新增）

**Risks:**
- SSE 流解析需要正确处理 `data: [DONE]` 终止和错误事件 → 缓解：参考 OpenAI SDK 的 SSE 解析模式，逐行读取
- 长对话内存增长 → 缓解：限制消息历史为最近 50 条，超出自动截断
- 无账号时聊天不可用 → 缓解：无账号时显示引导提示，跳转账号管理页

---

### Task 1: 创建 Chat 聊天页面组件

**Depends on:** None
**Files:**
- Create: `web/src/pages/Chat.tsx`

- [ ] **Step 1: 创建 Chat.tsx — 账号选择 + 模型选择 + 多轮对话 + SSE 流式渲染**

```typescript
// web/src/pages/Chat.tsx
import React, { useEffect, useRef, useState } from 'react';
import {
  Typography, Select, Button, Input, Space, Card, Avatar, Spin,
  Empty, Tooltip, Popconfirm,
} from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  DeleteOutlined, ClearOutlined,
} from '@ant-design/icons';
import { api } from '../api';
import type { Account } from '../api';

const { TextArea } = Input;

interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

const Chat: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('iflycode-default');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api.listAccounts().then(accs => {
      setAccounts(accs);
      const defaultAcc = accs.find(a => a.is_default);
      if (defaultAcc) {
        setSelectedAccount(defaultAcc.api_key);
      } else if (accs.length > 0) {
        setSelectedAccount(accs[0].api_key);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedAccount) { setModels([]); return; }
    api.getAccountModels(selectedAccount).then(m => {
      setModels(m);
      if (m.length > 0 && !m.includes(selectedModel)) {
        setSelectedModel(m[0]);
      }
    }).catch(() => setModels([]));
  }, [selectedAccount]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !selectedAccount || streaming) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setStreaming(true);

    const assistantMsg: ChatMessage = { role: 'assistant', content: '' };
    setMessages([...newMessages, assistantMsg]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const resp = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': selectedAccount,
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
          stream: true,
        }),
        signal: abort.signal,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: { message: resp.statusText } }));
        throw new Error(err.error?.message || `HTTP ${resp.status}`);
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;
          const payload = trimmed.slice(6);
          if (payload === '[DONE]') continue;

          try {
            const chunk = JSON.parse(payload);
            const delta = chunk.choices?.[0]?.delta;
            if (delta?.content) {
              assistantMsg.content += delta.content;
              setMessages([...newMessages, { ...assistantMsg }]);
            }
          } catch {
            // skip malformed chunks
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        assistantMsg.content = `[错误] ${e instanceof Error ? e.message : '请求失败'}`;
        setMessages([...newMessages, { ...assistantMsg }]);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const handleClear = () => {
    setMessages([]);
  };

  if (accounts.length === 0) {
    return (
      <div>
        <Typography.Title level={4}>聊天测试</Typography.Title>
        <Empty
          description="暂无账号，请先在「账号管理」中添加账号"
          style={{ marginTop: 60 }}
        >
          <Button type="primary" onClick={() => window.location.hash = '#/accounts'}>
            前往添加账号
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)' }}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>聊天测试</Typography.Title>
        <Space>
          <Select
            value={selectedAccount}
            onChange={setSelectedAccount}
            style={{ width: 200 }}
            placeholder="选择账号"
            options={accounts.map(a => ({
              value: a.api_key,
              label: (
                <Space>
                  {a.is_default && <Typography.Text type="warning">★</Typography.Text>}
                  {a.api_key}
                </Space>
              ),
            }))}
          />
          <Select
            value={selectedModel}
            onChange={setSelectedModel}
            style={{ width: 180 }}
            placeholder="选择模型"
            options={[
              { value: 'iflycode-default', label: '默认模型' },
              ...models.map(m => ({ value: m, label: m })),
            ]}
          />
          <Popconfirm title="清空所有对话记录？" onConfirm={handleClear}>
            <Button icon={<ClearOutlined />} size="small">清空</Button>
          </Popconfirm>
        </Space>
      </div>

      <Card
        style={{ flex: 1, overflow: 'hidden', marginBottom: 12 }}
        styles={{ body: { height: '100%', overflowY: 'auto', padding: '16px 20px' } }}
      >
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#999' }}>
            <RobotOutlined style={{ fontSize: 48, marginBottom: 16, display: 'block' }} />
            <Typography.Text type="secondary">
              选择账号和模型，输入消息开始对话
            </Typography.Text>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 16,
              }}
            >
              {msg.role === 'assistant' && (
                <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#1677ff', flexShrink: 0, marginRight: 8 }} />
              )}
              <div
                style={{
                  maxWidth: '70%',
                  padding: '8px 14px',
                  borderRadius: 12,
                  backgroundColor: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                  color: msg.role === 'user' ? '#fff' : '#333',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  lineHeight: 1.6,
                }}
              >
                {msg.content}
                {msg.role === 'assistant' && streaming && idx === messages.length - 1 && !msg.content && (
                  <Spin size="small" style={{ marginLeft: 8 }} />
                )}
              </div>
              {msg.role === 'user' && (
                <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#87d068', flexShrink: 0, marginLeft: 8 }} />
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </Card>

      <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        <TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => {
            if (!e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
          style={{ flex: 1 }}
        />
        {streaming ? (
          <Button danger onClick={handleStop} style={{ alignSelf: 'flex-end' }}>
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!input.trim() || !selectedAccount}
            style={{ alignSelf: 'flex-end' }}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
};

export default Chat;
```

- [ ] **Step 2: 验证 Chat.tsx 编译**
Run: `cd web && node_modules/.bin/tsc --noEmit 2>&1`
Expected:
  - Exit code: 0
  - Output does NOT contain: "error TS"

- [ ] **Step 3: 提交**
Run: `git add web/src/pages/Chat.tsx && git commit -m "feat(chat): add chat playground page with SSE streaming support"`

---

### Task 2: 集成 Chat 路由和导航

**Depends on:** Task 1
**Files:**
- Modify: `web/src/App.tsx:1-30`
- Modify: `web/src/layouts/MainLayout.tsx:1-80`

- [ ] **Step 1: 修改 App.tsx 以添加 /chat 路由**
文件: `web/src/App.tsx:1-30`

```typescript
// web/src/App.tsx — 完整替换
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Accounts = lazy(() => import('./pages/Accounts'));
const AccountDetail = lazy(() => import('./pages/AccountDetail'));
const Chat = lazy(() => import('./pages/Chat'));
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
          <Route path="/chat" element={<Suspense fallback={pageLoading}><Chat /></Suspense>} />
          <Route path="/settings" element={<Suspense fallback={pageLoading}><Settings /></Suspense>} />
          <Route path="/logs" element={<Suspense fallback={pageLoading}><Logs /></Suspense>} />
        </Route>
      </Routes>
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
```

- [ ] **Step 2: 修改 MainLayout.tsx 以添加聊天导航项**
文件: `web/src/layouts/MainLayout.tsx:1-80`

```typescript
// web/src/layouts/MainLayout.tsx — 完整替换
import React, { useEffect, useState } from 'react';
import { Layout, Menu, Typography } from 'antd';
import { DashboardOutlined, TeamOutlined, MessageOutlined, SettingOutlined, FileTextOutlined } from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { api } from '../api';

const { Header, Content, Sider, Footer } = Layout;

const MainLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [version, setVersion] = useState('');

  const selectedKey = location.pathname === '/accounts' || location.pathname.startsWith('/accounts/')
    ? '/accounts'
    : location.pathname;

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '数据概览' },
    { key: '/accounts', icon: <TeamOutlined />, label: '账号管理' },
    { key: '/chat', icon: <MessageOutlined />, label: '聊天测试' },
    { key: '/logs', icon: <FileTextOutlined />, label: '请求日志' },
    { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  ];

  useEffect(() => {
    api.getHealth().then(data => setVersion(data.version || '')).catch(() => {});
  }, []);

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
        <Footer style={{ textAlign: 'center', padding: '12px 24px', color: '#999', fontSize: 12 }}>
          iFlyCode Proxy {version && `v${version}`} — port 40419
        </Footer>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
```

- [ ] **Step 3: 验证编译和构建**
Run: `cd web && node_modules/.bin/tsc --noEmit && npm run build 2>&1`
Expected:
  - Exit code: 0
  - Output contains: "built in"
  - Output does NOT contain: "error" or "TS"

- [ ] **Step 4: 提交**
Run: `git add web/src/App.tsx web/src/layouts/MainLayout.tsx && git commit -m "feat(chat): integrate chat playground into navigation and routing"`

---

### Task 3: 端到端验证

**Depends on:** Task 2
**Files:**
- None (验证 only)

- [ ] **Step 1: 重启后端服务并验证聊天端点可达**
Run: `kill $(lsof -ti :40419) 2>/dev/null; sleep 1; cd /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy && python3 -m iflycode_proxy.cli serve --port 40419 & sleep 3 && curl -s http://localhost:40419/api/health | python3 -m json.tool`
Expected:
  - Output contains: "status": "ok"

- [ ] **Step 2: 验证前端静态资源包含 Chat 组件**
Run: `ls /Users/cc11001100/github/vibe-coding-labs/iflycode-proxy/iflycode_proxy/static/assets/ | grep -i chat`
Expected:
  - Exit code: 0
  - Output contains a filename with "Chat"

- [ ] **Step 3: 提交并推送**
Run: `git push`
