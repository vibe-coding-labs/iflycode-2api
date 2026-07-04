import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { LockOutlined, KeyOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { authApi, setToken } from '../api';

const { Title, Text } = Typography;

const SetupPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (values: { password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error('两次输入的密码不一致');
      return;
    }
    if (values.password.length < 6) {
      message.error('密码至少 6 个字符');
      return;
    }
    setLoading(true);
    try {
      const result = await authApi.init(values.password);
      setToken(result.token);
      message.success('初始化成功');
      navigate('/');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '初始化失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #1677ff 0%, #0958d9 100%)',
    }}>
      <Card
        style={{ width: 420, borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}
        styles={{ body: { padding: 32 } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>初始化管理密码</Title>
          <Text type="secondary">首次使用，请设置管理后台的登录密码</Text>
        </div>
        <Form onFinish={handleSubmit} size="large">
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请设置管理密码' }]}
          >
            <Input.Password prefix={<KeyOutlined />} placeholder="管理密码（至少 6 位）" autoFocus />
          </Form.Item>
          <Form.Item
            name="confirm"
            rules={[{ required: true, message: '请再次输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              style={{ borderRadius: 6, height: 44 }}
            >
              初始化
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default SetupPage;