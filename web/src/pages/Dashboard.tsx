import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Card, Col, Row, Statistic, Typography, Spin, Empty, Select, Space, Button, Tag } from 'antd';
import {
  ApiOutlined, TeamOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CloudSyncOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { api } from '../api';
import type { Stats, Account } from '../api';

const REFRESH_OPTIONS = [
  { value: 0, label: '关闭' },
  { value: 10, label: '10 秒' },
  { value: 30, label: '30 秒' },
  { value: 60, label: '60 秒' },
];

const fmt = (n: number) => n.toLocaleString();
const fmtTokens = (n: number) => n >= 1000000 ? `${(n / 1000000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n);
const successRateColor = (rate: number) => rate >= 95 ? '#00b96b' : rate >= 80 ? '#faad14' : '#ff4d4f';

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const [data, accs] = await Promise.all([api.getStats(), api.listAccounts()]);
      setStats(data);
      setAccounts(accs);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (refreshInterval > 0) {
      timerRef.current = setInterval(fetchStats, refreshInterval * 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [refreshInterval, fetchStats]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!stats) return <Empty description="无法连接代理服务" />;

  const todayTokens = stats.today_prompt_tokens + stats.today_completion_tokens;
  const allTimeTokens = stats.all_time.prompt_tokens + stats.all_time.completion_tokens;
  const todaySuccessRate = stats.today_requests > 0
    ? Math.round(stats.today_success_count / stats.today_requests * 1000) / 10 : 100;
  const todayStreamRate = stats.today_requests > 0
    ? Math.round(stats.today_stream_count / stats.today_requests * 1000) / 10 : 0;
  const avgTokensPerReq = stats.today_requests > 0
    ? Math.round(todayTokens / stats.today_requests) : 0;
  const ioRatio = stats.today_completion_tokens > 0
    ? (stats.today_prompt_tokens / stats.today_completion_tokens).toFixed(1) : '-';

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>数据概览</Typography.Title>
        <Space>
          <span style={{ color: '#666' }}>自动刷新:</span>
          <Select value={refreshInterval} onChange={setRefreshInterval} options={REFRESH_OPTIONS} style={{ width: 100 }} size="small" />
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchStats}>刷新</Button>
        </Space>
      </div>

      {/* Banner Card */}
      <Card
        style={{ marginBottom: 16, background: 'linear-gradient(135deg, #1677ff 0%, #0958d9 100%)', border: 'none' }}
        bodyStyle={{ padding: '24px 32px' }}
      >
        <Row gutter={[32, 16]} align="middle">
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>24h 请求</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{fmt(stats.today_requests)}</div>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>24h Tokens</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{fmtTokens(todayTokens)}</div>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>累计请求</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{fmt(stats.all_time.total_requests)}</div>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>累计 Tokens</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{fmtTokens(allTimeTokens)}</div>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>账号数</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{stats.accounts_count}</div>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>24h 成功率</div>
            <div style={{ color: '#fff', fontSize: 28, fontWeight: 700 }}>{todaySuccessRate}%</div>
          </Col>
        </Row>
      </Card>

      {/* 24h Trend Charts */}
      {stats.hourly && stats.hourly.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} lg={12}>
            <Card title="24h 请求趋势" size="small">
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={stats.hourly}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="count" name="请求数" stroke="#1677ff" fill="#1677ff" fillOpacity={0.15} strokeWidth={2} />
                  <Area type="monotone" dataKey="errors" name="错误数" stroke="#ff4d4f" fill="#ff4d4f" fillOpacity={0.1} strokeWidth={1.5} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="24h Token 消耗" size="small">
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={stats.hourly}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="input_tokens" name="Prompt" stroke="#1677ff" fill="#1677ff" fillOpacity={0.15} strokeWidth={2} />
                  <Area type="monotone" dataKey="output_tokens" name="Completion" stroke="#722ed1" fill="#722ed1" fillOpacity={0.1} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </Col>
        </Row>
      )}

      {/* 3 Statistic Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <Card title="请求统计" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Statistic title="24h 请求" value={stats.today_requests} prefix={<ApiOutlined />} valueStyle={{ fontSize: 20 }} />
                <Statistic title="累计请求" value={stats.all_time.total_requests} prefix={<CloudSyncOutlined />} valueStyle={{ fontSize: 20 }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span><CheckCircleOutlined style={{ color: '#00b96b' }} /> 成功 {fmt(stats.today_success_count)} <Tag color="green">{todaySuccessRate}%</Tag></span>
                <span><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 失败 {fmt(stats.today_error_count)} <Tag color="red">{stats.today_requests > 0 ? (100 - todaySuccessRate).toFixed(1) : 0}%</Tag></span>
              </div>
              <div>
                <ClockCircleOutlined /> 流式请求 {fmt(stats.today_stream_count)} <Tag color="blue">{todayStreamRate}%</Tag>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title="Token 消耗" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Statistic title="24h Tokens" value={fmtTokens(todayTokens)} valueStyle={{ fontSize: 20, color: '#1677ff' }} />
                <Statistic title="累计 Tokens" value={fmtTokens(allTimeTokens)} valueStyle={{ fontSize: 20, color: '#722ed1' }} />
              </div>
              <div>
                Prompt: {fmtTokens(stats.today_prompt_tokens)} / Completion: {fmtTokens(stats.today_completion_tokens)}
              </div>
              <div>
                平均每请求: {fmt(avgTokensPerReq)} tokens &nbsp;|&nbsp; I/O 比: {ioRatio}
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card title="响应质量" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Statistic title="24h 平均延迟" value={stats.today_avg_latency_ms} suffix="ms" prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 20 }} />
              <div>
                成功率: <span style={{ color: successRateColor(todaySuccessRate), fontWeight: 600 }}>{todaySuccessRate}%</span>
              </div>
              <div>
                流式率: {todayStreamRate}% &nbsp;|&nbsp; 账号: {stats.accounts_count} &nbsp;|&nbsp; 模型: {stats.by_model.length}
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* Distribution Charts */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="模型使用分布" size="small">
            {stats.today_by_model && stats.today_by_model.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={stats.today_by_model} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="model" type="category" width={100} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="请求数" fill="#1677ff" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="账号请求分布" size="small">
            {stats.today_by_account && stats.today_by_account.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={stats.today_by_account}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="api_key" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" name="请求数" fill="#1677ff" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Accounts Overview Table */}
      {accounts.length > 0 && (
        <Card title="账号概览" size="small">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#666' }}>账号 ID</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#666' }}>默认模型</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#666' }}>API Key</th>
                <th style={{ textAlign: 'left', padding: '8px 12px', color: '#666' }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map(acc => (
                <tr key={acc.account_id} style={{ borderBottom: '1px solid #f5f5f5' }}>
                  <td style={{ padding: '8px 12px' }}>{acc.account_id}{acc.is_default ? ' ★' : ''}</td>
                  <td style={{ padding: '8px 12px' }}>{acc.default_model || '自动'}</td>
                  <td style={{ padding: '8px 12px' }}><Typography.Text code>{acc.api_key.slice(0, 10)}...</Typography.Text></td>
                  <td style={{ padding: '8px 12px' }}><Tag color="green">在线</Tag></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default Dashboard;
