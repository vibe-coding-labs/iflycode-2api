import React from 'react';
import { Button, Card, Typography, Result } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Link, useSearchParams } from 'react-router-dom';

const { Title } = Typography;

const OAuthErrorPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const error = searchParams.get('error') || '未知错误';

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #389e0d 0%, #237804 100%)',
    }}>
      <Card style={{ width: 480, borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.12)' }}
            styles={{ body: { padding: 32 } }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 16 }}>登录失败</Title>
        <Result
          status="error"
          title="SSO 登录失败"
          subTitle={error}
        />
        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Link to="/login">
            <Button icon={<ArrowLeftOutlined />} type="primary" ghost style={{ borderRadius: 6 }}>
              返回登录
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
};

export default OAuthErrorPage;