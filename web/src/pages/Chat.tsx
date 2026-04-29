import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Typography, Select, Button, Input, Space, Avatar, Spin,
  Empty, Popconfirm,
} from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  ClearOutlined, StopOutlined,
} from '@ant-design/icons';
import { api } from '../api';
import type { Account } from '../api';

const { TextArea } = Input;

interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

const DB_NAME = 'iflycode-chat';
const DB_VERSION = 1;
const STORE_NAME = 'conversations';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function loadMessages(accountKey: string): Promise<ChatMessage[]> {
  const db = await openDB();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.get(accountKey);
    req.onsuccess = () => resolve(req.result?.messages || []);
    req.onerror = () => resolve([]);
  });
}

async function saveMessages(accountKey: string, messages: ChatMessage[]): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.put({ id: accountKey, messages });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function clearMessages(accountKey: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.delete(accountKey);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
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
    if (!selectedAccount) return;
    loadMessages(selectedAccount).then(m => setMessages(m)).catch(() => setMessages([]));
  }, [selectedAccount]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const persistMessages = useCallback((msgs: ChatMessage[]) => {
    if (!selectedAccount) return;
    saveMessages(selectedAccount, msgs).catch(() => {});
  }, [selectedAccount]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !selectedAccount || streaming) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setStreaming(true);

    const assistantMsg: ChatMessage = { role: 'assistant', content: '' };
    const withAssistant = [...newMessages, assistantMsg];
    setMessages(withAssistant);

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
              const updated = [...newMessages, { ...assistantMsg }];
              setMessages(updated);
            }
          } catch {
            // skip malformed chunks
          }
        }
      }

      persistMessages([...newMessages, { ...assistantMsg }]);
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        assistantMsg.content = `[错误] ${e instanceof Error ? e.message : '请求失败'}`;
        const failed = [...newMessages, { ...assistantMsg }];
        setMessages(failed);
        persistMessages(failed);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    persistMessages(messages);
  };

  const handleClear = async () => {
    setMessages([]);
    if (selectedAccount) {
      await clearMessages(selectedAccount).catch(() => {});
    }
  };

  if (accounts.length === 0) {
    return (
      <div style={{ padding: 24 }}>
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
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 148px)', overflow: 'hidden' }}>
      {/* Top bar */}
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0, flexWrap: 'wrap', gap: 8 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>聊天测试</Typography.Title>
        <Space wrap>
          <Select
            value={selectedAccount}
            onChange={setSelectedAccount}
            style={{ minWidth: 160, maxWidth: 220 }}
            placeholder="选择账号"
            options={accounts.map(a => ({
              value: a.api_key,
              label: (
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.is_default ? '★ ' : ''}{a.api_key}
                </span>
              ),
            }))}
          />
          <Select
            value={selectedModel}
            onChange={setSelectedModel}
            style={{ minWidth: 140, maxWidth: 200 }}
            placeholder="选择模型"
            options={[
              { value: 'iflycode-default', label: '默认模型' },
              ...models.map(m => ({ value: m, label: m })),
            ]}
          />
          <Popconfirm title="清空所有对话记录？" onConfirm={handleClear}>
            <Button icon={<ClearOutlined />}>清空</Button>
          </Popconfirm>
        </Space>
      </div>

      {/* Messages area */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', marginBottom: 12, padding: '12px 16px', backgroundColor: '#fafafa', borderRadius: 8 }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 20px', color: '#999' }}>
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
                maxWidth: '100%',
              }}
            >
              {msg.role === 'assistant' && (
                <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#1677ff', flexShrink: 0, marginRight: 10, marginTop: 2 }} />
              )}
              <div
                style={{
                  maxWidth: '75%',
                  padding: '10px 16px',
                  borderRadius: 12,
                  backgroundColor: msg.role === 'user' ? '#1677ff' : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#333',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  lineHeight: 1.7,
                  boxShadow: msg.role === 'assistant' ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                  border: msg.role === 'assistant' ? '1px solid #f0f0f0' : 'none',
                  overflowWrap: 'break-word',
                }}
              >
                {msg.content}
                {msg.role === 'assistant' && streaming && idx === messages.length - 1 && !msg.content && (
                  <Spin size="small" style={{ marginLeft: 8 }} />
                )}
              </div>
              {msg.role === 'user' && (
                <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#87d068', flexShrink: 0, marginLeft: 10, marginTop: 2 }} />
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={{ flexShrink: 0, display: 'flex', gap: 12, alignItems: 'flex-end' }}>
        <TextArea
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={e => {
            if (!e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          autoSize={{ minRows: 3, maxRows: 8 }}
          disabled={streaming}
          style={{ flex: 1, fontSize: 15, padding: '10px 14px', borderRadius: 8 }}
        />
        {streaming ? (
          <Button
            danger
            icon={<StopOutlined />}
            onClick={handleStop}
            size="large"
            style={{ height: 'auto', minHeight: 56, borderRadius: 8, paddingInline: 24 }}
          >
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!input.trim() || !selectedAccount}
            size="large"
            style={{ height: 'auto', minHeight: 56, borderRadius: 8, paddingInline: 28 }}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
};

export default Chat;