import React, { useEffect, useRef, useState } from 'react';
import {
  Typography, Select, Button, Input, Space, Card, Avatar, Spin,
  Empty, Popconfirm,
} from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined,
  ClearOutlined,
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