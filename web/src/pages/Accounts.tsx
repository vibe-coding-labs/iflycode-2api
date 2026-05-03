import React, { useEffect, useRef, useState } from 'react';
import {
  Table, Button, Space, Modal, Form, Input, Switch,
  message, Popconfirm, Tag, Typography, Alert, Tabs, Spin, Popover,
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

const maskKey = (key: string) => key.length > 12 ? key.slice(0, 6) + '...' + key.slice(-4) : key;

const Accounts: React.FC = () => {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [validating, setValidating] = useState<string | null>(null);

  // SSO login state
  const [ssoLoginUrl, setSsoLoginUrl] = useState('');
  const [ssoClientId, setSsoClientId] = useState('');
  const [ssoLoading, setSsoLoading] = useState(false);
  const [ssoPolling, setSsoPolling] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const data = await api.listAccounts();
      setAccounts(data);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '获取账号列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAccounts(); }, []);

  useEffect(() => {
    return () => { if (pollTimerRef.current) clearInterval(pollTimerRef.current); };
  }, []);

  const handleAdd = async (values: { spark_token: string; user_id?: string; is_default?: boolean }) => {
    try {
      const result = await api.addAccount({ spark_token: values.spark_token, user_id: values.user_id, is_default: values.is_default });
      message.success(`账号「${result.account_id}」添加成功`);
      setModalOpen(false);
      form.resetFields();
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加账号失败');
    }
  };

  const handleRemove = async (accountId: string) => {
    try {
      await api.removeAccount(accountId);
      message.success(`账号已删除`);
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除账号失败');
    }
  };

  const handleSetDefault = async (accountId: string) => {
    try {
      await api.setDefault(accountId);
      message.success(`已设为默认账号`);
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '设置失败');
    }
  };

  const handleValidate = async (accountId: string) => {
    setValidating(accountId);
    try {
      const result = await api.validateAccount(accountId);
      if (result.valid) {
        message.success(`账号验证通过`);
      } else {
        message.error(`账号验证失败，token 无效或已过期`);
      }
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '验证请求失败');
    } finally {
      setValidating(null);
    }
  };

  const handleSSOLogin = async () => {
    setSsoLoading(true);
    setSsoLoginUrl('');
    setSsoClientId('');
    try {
      const result = await api.getLoginUrl();
      if (result.login_url) {
        setSsoLoginUrl(result.login_url);
        setSsoClientId(result.client_id);
        window.open(result.login_url, '_blank');
        startPolling(result.client_id);
      }
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '获取登录地址失败');
    } finally {
      setSsoLoading(false);
    }
  };

  const startPolling = (clientId: string) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setSsoPolling(true);
    pollTimerRef.current = setInterval(async () => {
      try {
        const result = await api.pollLoginStatus(clientId);
        if (result.ok && result.token) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setSsoPolling(false);
          const addResult = await api.addAccountFromSSO({
            token: result.token,
            user_id: result.user_id || '',
          });
          message.success(`SSO 登录成功，已添加账号`);
          setModalOpen(false);
          fetchAccounts();
        }
      } catch {
        // keep polling
      }
    }, 2000);
  };

  const handleModalClose = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setSsoPolling(false);
    setSsoLoginUrl('');
    setSsoClientId('');
    setModalOpen(false);
    form.resetFields();
  };

  const columns = [
    {
      title: '账号 ID',
      dataIndex: 'account_id',
      key: 'account_id',
      render: (text: string) => (
        <Typography.Text code style={{ cursor: 'pointer' }} onClick={() => navigate(`/accounts/${encodeURIComponent(text)}`)}>
          {text}
        </Typography.Text>
      ),
    },
    {
      title: 'API Key',
      dataIndex: 'api_key',
      key: 'api_key',
      render: (text: string) => (
        <Space size={4}>
          <Typography.Text code>{maskKey(text)}</Typography.Text>
          <Button size="small" type="link" icon={<CopyOutlined />} style={{ padding: 0, height: 'auto', minWidth: 0 }} onClick={() => { navigator.clipboard.writeText(text); message.success('已复制 API Key'); }} />
        </Space>
      ),
    },
    {
      title: '用户 ID',
      dataIndex: 'user_id',
      key: 'user_id',
    },
    {
      title: '默认模型',
      dataIndex: 'default_model',
      key: 'default_model',
      render: (val: string) => val ? <Tag color="green">{val}</Tag> : <Typography.Text type="secondary">自动</Typography.Text>,
    },
    {
      title: '状态',
      dataIndex: 'is_default',
      key: 'is_default',
      render: (val: boolean) => val ? <Tag color="blue"><StarOutlined /> 默认账号</Tag> : null,
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: Account) => (
        <Space>
          {!record.is_default && (
            <Button size="small" onClick={() => handleSetDefault(record.account_id)}>
              <StarOutlined /> 设为默认
            </Button>
          )}
          <Button size="small" onClick={() => handleValidate(record.account_id)} loading={validating === record.account_id}>
            <SafetyCertificateOutlined /> 验证
          </Button>
          <Popconfirm title="确定删除此账号？" onConfirm={() => handleRemove(record.account_id)}>
            <Button size="small" danger><DeleteOutlined /> 删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
    {
      title: '启动命令',
      key: 'copy_cmd',
      width: 120,
      align: 'center' as const,
      render: (_: unknown, record: Account) => {
        const modelFlag = record.default_model ? ` --model ${record.default_model}` : '';
        const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${record.api_key}" \\\nclaude --dangerously-skip-permissions${modelFlag}`;
        const codexCmd = `OPENAI_API_KEY="${record.api_key}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex${modelFlag}`;
        return (
          <Space>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Claude Code 启动命令" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />}
            >
              <Button size="small" icon={<AnthropicIcon />} onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />
            </Popover>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Codex 启动命令" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />}
            >
              <Button size="small" icon={<OpenAIIcon />} onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />
            </Popover>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>账号管理</Typography.Title>
        <Space>
          <Button onClick={fetchAccounts} icon={<ReloadOutlined />}>刷新</Button>
          <Button type="primary" onClick={() => setModalOpen(true)} icon={<PlusOutlined />}>添加账号</Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        message="多账号路由说明"
        description="每个账号拥有独立的 API Key 用于代理认证。客户端通过 x-api-key 头路由到对应账号。API Key 可随时轮换，不影响账号数据。"
        style={{ marginBottom: 16 }}
      />

      <Table
        dataSource={accounts}
        columns={columns}
        rowKey="account_id"
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无账号，请点击「添加账号」' }}
        onRow={(record) => ({
          onClick: () => navigate(`/accounts/${encodeURIComponent(record.account_id)}`),
          style: { cursor: 'pointer' },
        })}
      />

      <Modal
        title="添加 iFlyCode 账号"
        open={modalOpen}
        onCancel={handleModalClose}
        footer={null}
        width={560}
        destroyOnClose
      >
        <Tabs
          items={[
            {
              key: 'sso',
              label: 'SSO 登录',
              children: (
                <div style={{ padding: '12px 0' }}>
                  <Typography.Paragraph>
                    通过 iFlyCode 官方 SSO 登录，与 IDE 端登录方式一致。点击按钮打开登录页面，完成登录后 token 将自动获取并添加到账号池。
                  </Typography.Paragraph>
                  {!ssoLoginUrl ? (
                    <Button
                      type="primary"
                      size="large"
                      icon={<LoginOutlined />}
                      loading={ssoLoading}
                      onClick={handleSSOLogin}
                      block
                    >
                      打开 iFlyCode 登录
                    </Button>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '24px 0' }}>
                      {ssoPolling ? (
                        <>
                          <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} />} />
                          <Typography.Paragraph style={{ marginTop: 16 }}>
                            等待登录完成...
                          </Typography.Paragraph>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            请在浏览器中完成登录
                          </Typography.Text>
                        </>
                      ) : (
                        <Typography.Text type="success">
                          <CheckCircleOutlined /> 登录成功
                        </Typography.Text>
                      )}
                      <div style={{ marginTop: 12 }}>
                        <Button size="small" type="link" onClick={() => window.open(ssoLoginUrl, '_blank')}>
                          重新打开登录页面
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: 'manual',
              label: '手动粘贴 Token',
              children: (
                <Form form={form} layout="vertical" onFinish={handleAdd} style={{ padding: '12px 0' }}>
                  <Form.Item name="spark_token" label="iFlyCode SSO Token" rules={[{ required: true, message: '请输入 token' }]}>
                    <Input.Password placeholder="从 iFlyCode 登录后获取的 token" />
                  </Form.Item>
                  <Form.Item name="user_id" label="用户 ID">
                    <Input placeholder="可选" />
                  </Form.Item>
                  <Form.Item name="is_default" valuePropName="checked" label="设为默认账号">
                    <Switch />
                  </Form.Item>
                  <Form.Item>
                    <Space>
                      <Button type="primary" htmlType="submit">添加</Button>
                      <Button onClick={handleModalClose}>取消</Button>
                    </Space>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  );
};

export default Accounts;
