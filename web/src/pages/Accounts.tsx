import React, { useEffect, useRef, useState } from 'react';
import {
  Table, Button, Space, Modal, Form, Input, Switch,
  message, Popconfirm, Tag, Typography, Alert, Tabs, Spin, Tooltip,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  PlusOutlined, DeleteOutlined, StarOutlined,
  SafetyCertificateOutlined, ReloadOutlined, LoginOutlined,
  CheckCircleOutlined, LoadingOutlined, CodeOutlined, RobotOutlined,
} from '@ant-design/icons';
import { api } from '../api';
import type { Account } from '../api';

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

  // Account login state
  const [accountForm] = Form.useForm();
  const [accountLoginLoading, setAccountLoginLoading] = useState(false);

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

  const handleAccountLogin = async (values: { username: string; password: string }) => {
    setAccountLoginLoading(true);
    try {
      const result = await api.loginByAccount(values);
      message.success(`登录成功，已添加账号「${result.api_key}」`);
      setModalOpen(false);
      accountForm.resetFields();
      fetchAccounts();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '登录失败');
    } finally {
      setAccountLoginLoading(false);
    }
  };

  const handleModalClose = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setSsoPolling(false);
    setSsoLoginUrl('');
    setSsoClientId('');
    setModalOpen(false);
    form.resetFields();
    accountForm.resetFields();
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
            <Tooltip title="复制 Claude Code 启动命令">
              <Button
                size="small"
                icon={<RobotOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(claudeCmd);
                  message.success('已复制 Claude Code 启动命令');
                }}
              />
            </Tooltip>
            <Tooltip title="复制 Codex 启动命令">
              <Button
                size="small"
                icon={<CodeOutlined />}
                onClick={() => {
                  navigator.clipboard.writeText(codexCmd);
                  message.success('已复制 Codex 启动命令');
                }}
              />
            </Tooltip>
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
              label: 'SSO 登录（推荐）',
              children: (
                <div style={{ padding: '12px 0' }}>
                  <Typography.Paragraph>
                    点击下方按钮将打开 iFlyCode 登录页面。完成登录后，token 将自动获取并添加到账号池。
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
              key: 'account',
              label: '账号密码登录',
              children: (
                <Form form={accountForm} layout="vertical" onFinish={handleAccountLogin} style={{ padding: '12px 0' }}>
                  <Typography.Paragraph type="secondary">
                    使用 iFlyCode 账号密码直接登录，token 将自动获取并添加到账号池。
                  </Typography.Paragraph>
                  <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input placeholder="iFlyCode 用户名" autoComplete="username" />
                  </Form.Item>
                  <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password placeholder="iFlyCode 密码" autoComplete="current-password" />
                  </Form.Item>
                  <Form.Item>
                    <Space>
                      <Button type="primary" htmlType="submit" loading={accountLoginLoading} icon={<LoginOutlined />}>登录并添加</Button>
                      <Button onClick={handleModalClose}>取消</Button>
                    </Space>
                  </Form.Item>
                </Form>
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
