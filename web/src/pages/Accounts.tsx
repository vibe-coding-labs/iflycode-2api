import React, { useEffect, useState } from 'react';
import {
  Table, Button, Space, Modal, Form, Input, Switch,
  message, Popconfirm, Tag, Typography, Alert,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, StarOutlined,
  SafetyCertificateOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { api } from '../api';
import type { Account } from '../api';

const Accounts: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [validating, setValidating] = useState<string | null>(null);

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

  const columns = [
    {
      title: '路由密钥 (API Key)',
      dataIndex: 'api_key',
      key: 'api_key',
      render: (text: string) => <Typography.Text code>{text}</Typography.Text>,
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
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        okText="添加"
        cancelText="取消"
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
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
        </Form>
      </Modal>
    </div>
  );
};

export default Accounts;
