import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Card, Col, Row, Statistic, Typography, Spin, Empty, Alert, Select, Space, Button } from 'antd';
import {
  ApiOutlined, TeamOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../api';
import type { Stats } from '../api';

const REFRESH_OPTIONS = [
  { value: 0, label: '关闭' },
  { value: 10, label: '10 秒' },
  { value: 30, label: '30 秒' },
  { value: 60, label: '60 秒' },
];

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (refreshInterval > 0) {
      timerRef.current = setInterval(fetchStats, refreshInterval * 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [refreshInterval, fetchStats]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!stats) return <Empty description="无法连接代理服务" />;

  const errorCount = stats.by_model.length > 0 ? 0 : 0; // stats 不含 error_count，从 logs 推导

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>数据概览</Typography.Title>
        <Space>
          <span style={{ color: '#666' }}>自动刷新:</span>
          <Select
            value={refreshInterval}
            onChange={setRefreshInterval}
            options={REFRESH_OPTIONS}
            style={{ width: 100 }}
            size="small"
          />
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchStats}>刷新</Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        message="iFlyCode 代理服务"
        description="此处展示代理运行状态。在「账号管理」中添加 iFlyCode 账号（token），客户端通过 x-api-key 路由到对应账号。"
        style={{ marginBottom: 24 }}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="总请求数" value={stats.total_requests} prefix={<ApiOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="已配置账号" value={stats.accounts_count} prefix={<TeamOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="平均延迟" value={stats.avg_latency_ms} suffix="ms" prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="模型种类"
              value={stats.by_model.length}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
      </Row>

      {stats.by_model.length > 0 && (
        <Card title="各模型请求量" style={{ marginTop: 24 }}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stats.by_model}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="model" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" name="请求次数" fill="#1677ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {stats.by_account.length > 0 && (
        <Card title="各账号请求量" style={{ marginTop: 24 }}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stats.by_account}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="api_key" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" name="请求次数" fill="#52c41a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  );
};

export default Dashboard;
