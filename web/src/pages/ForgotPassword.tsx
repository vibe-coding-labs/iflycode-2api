import React from 'react';
import { Button, Card, Typography, Alert } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';

const { Title, Text, Paragraph } = Typography;

const codeStyle: React.CSSProperties = {
  background: '#1e1e2e', color: '#cdd6f4', padding: '14px 18px',
  borderRadius: 8, marginTop: 8, marginBottom: 20, fontSize: 14,
  fontFamily: "'SF Mono', 'Fira Code', Menlo, monospace",
  lineHeight: 1.6, overflow: 'auto', whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-all' as const,
};

const ForgotPasswordPage: React.FC = () => {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1677ff 0%, #0958d9 100%)',
    }}>
      <Card style={{ width: 640, borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}
            styles={{ body: { padding: 32 } }}>
        <Title level={3} style={{ marginBottom: 8 }}>忘记密码</Title>
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          管理后台的密码需要通过服务器命令行重置。
        </Paragraph>
        <Alert type="info" showIcon style={{ marginBottom: 20 }}
               message="在代理服务器终端执行以下命令" />
        <Text strong>交互式重置：</Text>
        <pre style={codeStyle}>iflycode-proxy reset-password</pre>
        <Text strong>直接指定新密码：</Text>
        <pre style={codeStyle}>iflycode-proxy reset-password -p 你的新密码</pre>
        <Alert type="warning" showIcon style={{ marginBottom: 24 }}
               message={<>密码至少 <Text strong>6 位</Text>，以 bcrypt 哈希加密存储。</>} />
        <Link to="/login">
          <Button icon={<ArrowLeftOutlined />} type="primary" ghost style={{ borderRadius: 6 }}>
            返回登录
          </Button>
        </Link>
      </Card>
    </div>
  );
};

export default ForgotPasswordPage;