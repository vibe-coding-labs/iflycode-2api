import React, { useEffect, useState } from 'react';
import { Layout, Menu, Typography } from 'antd';
import { DashboardOutlined, TeamOutlined, SettingOutlined, FileTextOutlined } from '@ant-design/icons';
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
