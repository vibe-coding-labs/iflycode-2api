import React, { useEffect, useRef, useState } from 'react';
import {
  Table, Button, Space, Modal, Form, Input, Switch,
  message, Popconfirm, Tag, Typography, Alert, Tabs, Spin, Tooltip, Popover,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  PlusOutlined, DeleteOutlined, StarOutlined,
  SafetyCertificateOutlined, ReloadOutlined, LoginOutlined,
  CheckCircleOutlined, LoadingOutlined, CodeOutlined, RobotOutlined, CopyOutlined,
} from '@ant-design/icons';
import { api } from '../api';
import type { Account } from '../api';

const CommandPreview: React.FC<{ label: string; cmd: string; onCopy: () => void }> = ({ label, cmd, onCopy }) => (
  <div style={{ maxWidth: 480 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
      <Typography.Text strong style={{ fontSize: 12 }}>{label}</Typography.Text>
      <Button size="small" type="link" icon={<CopyOutlined />} onClick={onCopy} style={{ padding: 0, height: 'auto', fontSize: 12 }}>
        复制
      </Button>
    </div>
    <pre style={{
      margin: 0,
      padding: '8px 10px',
      background: '#1e1e1e',
      color: '#d4d4d4',
      borderRadius: 6,
      fontSize: 11,
      lineHeight: 1.5,
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-all',
      maxHeight: 200,
      overflowY: 'auto',
    }}>
      {cmd}
    </pre>
  </div>
);

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

  const handleAdd = async (values: { api_key: string; token: string; user_id?: string; is_default?: boolean }) => {
    try {
      await api.addAccount(values);
      message.success(`账号「${values.api_key}」添加成功`);
      setModalOpen(false);
      form.resetFields();
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '添加账号失败');
    }
  };

  const handleRemove = async (apiKey: string) => {
    try {
      await api.removeAccount(apiKey);
      message.success(`账号「${apiKey}」已删除`);
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除账号失败');
    }
  };

  const handleSetDefault = async (apiKey: string) => {
    try {
      await api.setDefault(apiKey);
      message.success(`已将「${apiKey}」设为默认账号`);
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '设置失败');
    }
  };

  const handleValidate = async (apiKey: string) => {
    setValidating(apiKey);
    try {
      const result = await api.validateAccount(apiKey);
      if (result.valid) {
        message.success(`账号「${apiKey}」验证通过`);
      } else {
        message.error(`账号「${apiKey}」验证失败，token 无效或已过期`);
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
          message.success(`SSO 登录成功，已添加账号「${addResult.api_key}」`);
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
      title: '路由密钥 (API Key)',
      dataIndex: 'api_key',
      key: 'api_key',
      render: (text: string) => (
        <Typography.Text code style={{ cursor: 'pointer' }} onClick={() => navigate(`/accounts/${encodeURIComponent(text)}`)}>
          {text}
        </Typography.Text>
      ),
    },
    {
      title: '用户 ID',
      dataIndex: 'user_id',
      key: 'user_id',
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
            <Button size="small" onClick={() => handleSetDefault(record.api_key)}>
              <StarOutlined /> 设为默认
            </Button>
          )}
          <Button size="small" onClick={() => handleValidate(record.api_key)} loading={validating === record.api_key}>
            <SafetyCertificateOutlined /> 验证
          </Button>
          <Popconfirm title={`确定删除账号「${record.api_key}」？`} onConfirm={() => handleRemove(record.api_key)}>
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
        const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${record.api_key}" \\\nclaude --dangerously-skip-permissions`;
        const codexCmd = `OPENAI_API_KEY="${record.api_key}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;
        return (
          <Space>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Claude Code 启动命令" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />}
            >
              <Button size="small" icon={<RobotOutlined />} />
            </Popover>
            <Popover
              placement="leftTop"
              trigger="hover"
              content={<CommandPreview label="Codex 启动命令" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />}
            >
              <Button size="small" icon={<CodeOutlined />} />
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
        description="每个账号对应一个 iFlyCode token。客户端通过 x-api-key 头路由到对应账号。配置 OpenAI SDK 时将路由密钥填入 api_key 即可。"
        style={{ marginBottom: 16 }}
      />

      <Table
        dataSource={accounts}
        columns={columns}
        rowKey="api_key"
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无账号，请点击「添加账号」' }}
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
                  <Form.Item name="api_key" label="路由密钥" rules={[{ required: true, message: '请输入路由密钥' }]}>
                    <Input placeholder="例如：account-1、user-zhangsan" />
                  </Form.Item>
                  <Form.Item name="token" label="iFlyCode Token" rules={[{ required: true, message: '请输入 token' }]}>
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
