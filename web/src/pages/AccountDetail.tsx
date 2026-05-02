import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Space, Tag, Table, message, Divider, Tooltip as AntTooltip, Popconfirm,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CopyOutlined, QuestionCircleOutlined, SyncOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts';
import { SPARK_MODELS, formatContextLength, TIER_EXPLANATION } from '../data/sparkModels';
import { api } from '../api';
import type { Account, AccountStats, HourlyStatsPoint, RecentLogEntry } from '../api';

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
    <div>
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

const formatHour = (h: string) => {
  const parts = h.split(' ');
  return parts.length >= 2 ? parts[1] : h;
};

const AccountDetail: React.FC = () => {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const decodedId = decodeURIComponent(accountId || '');

  const [info, setInfo] = useState<Account | null>(null);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [hourlyData, setHourlyData] = useState<HourlyStatsPoint[]>([]);
  const [recentLogs, setRecentLogs] = useState<RecentLogEntry[]>([]);
  const [models, setModels] = useState<{ modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean }[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [hourRange, setHourRange] = useState<number>(24);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const accounts = await api.listAccounts();
      const acc = accounts.find(a => a.account_id === decodedId);
      if (acc) {
        setInfo(acc);
        setSelectedModel(acc.default_model);
      }
    } catch { /* ignore */ }

    try {
      const s = await api.getAccountStats(decodedId);
      setStats(s);
    } catch { /* ignore */ }

    try {
      const h = await api.getAccountHourlyStats(decodedId, hourRange);
      setHourlyData(h.data || []);
    } catch { /* ignore */ }

    try {
      const logs = await api.getAccountRecentLogs(decodedId, 20);
      setRecentLogs(logs);
    } catch { /* ignore */ }

    try {
      const m = await api.getAccountModels(decodedId);
      setModels(m);
    } catch { /* ignore */ }

    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [decodedId]);

  useEffect(() => {
    if (!decodedId) return;
    api.getAccountHourlyStats(decodedId, hourRange)
      .then(h => setHourlyData(h.data || []))
      .catch(() => {});
  }, [hourRange]);

  const handleModelChange = async (model: string) => {
    try {
      await api.updateAccountModel(decodedId, model);
      setSelectedModel(model);
      message.success('默认模型已更新');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  };

  const handleRenewKey = async () => {
    try {
      const result = await api.renewApiKey(decodedId);
      message.success('API Key 已轮换');
      fetchData();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '轮换失败');
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!info) return <Typography.Text type="danger">账号不存在</Typography.Text>;

  const totalSuccessRate = stats && stats.total_requests > 0
    ? ((stats.total_requests - stats.error_count) / stats.total_requests * 100).toFixed(1)
    : '0.0';

  const apiKey = info.api_key;
  const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${apiKey}" \\\nclaude --dangerously-skip-permissions`;
  const codexCmd = `OPENAI_API_KEY="${apiKey}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounts')}>返回</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>{info.account_id}</Typography.Title>
          {info.is_default && <Tag color="blue">默认账号</Tag>}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </div>

      {/* 1. Request Statistics */}
      <Card title="请求统计" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总请求" value={stats?.total_requests || 0} prefix={<ApiOutlined />} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="今日请求" value={stats?.today_requests || 0} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总成功率" value={totalSuccessRate} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="今日成功率" value={stats?.today_success_rate || 0} suffix="%" valueStyle={{ color: '#52c41a' }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="总错误" value={stats?.error_count || 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: stats?.error_count ? '#ff4d4f' : undefined }} />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Statistic title="平均延迟" value={stats?.avg_latency_ms || 0} suffix="ms" prefix={<ThunderboltOutlined />} />
          </Col>
        </Row>
        {hourlyData.length > 0 && (
          <>
            <Divider style={{ margin: '16px 0 12px' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>每小时请求量</Typography.Text>
              <Select
                size="small"
                value={hourRange}
                onChange={setHourRange}
                style={{ width: 120 }}
                options={[
                  { value: 24, label: '最近 24 小时' },
                  { value: 48, label: '最近 48 小时' },
                  { value: 168, label: '最近 7 天' },
                ]}
              />
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hourlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(l) => String(l)} />
                <Legend />
                <Line type="monotone" dataKey="request_count" name="请求数" stroke="#1677ff" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="error_count" name="错误数" stroke="#ff4d4f" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      {/* 2. Token Consumption */}
      <Card title="Token 消耗" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="总 Prompt Tokens" value={stats?.prompt_tokens || 0} valueStyle={{ color: '#1677ff', fontSize: 18 }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="总 Completion Tokens" value={stats?.completion_tokens || 0} valueStyle={{ color: '#722ed1', fontSize: 18 }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="24h Prompt" value={stats?.prompt_tokens_24h || 0} valueStyle={{ color: '#1677ff' }} />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Statistic title="24h Completion" value={stats?.completion_tokens_24h || 0} valueStyle={{ color: '#722ed1' }} />
          </Col>
        </Row>
        {hourlyData.some(h => h.prompt_tokens > 0 || h.completion_tokens > 0) && (
          <>
            <Divider style={{ margin: '16px 0 12px' }} />
            <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>每小时 Token 消耗</Typography.Text>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={hourlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(l) => String(l)} />
                <Legend />
                <Line type="monotone" dataKey="prompt_tokens" name="Prompt Tokens" stroke="#1677ff" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="completion_tokens" name="Completion Tokens" stroke="#722ed1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      {/* 3. Model & Account */}
      <Card title="模型与账号" style={{ marginBottom: 16 }}>
        <Row gutter={[24, 16]}>
          <Col xs={24} md={8}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>默认模型</Typography.Text>
            <Select
              style={{ width: '100%', marginTop: 4 }}
              placeholder="使用服务器默认模型"
              allowClear
              value={selectedModel || undefined}
              onChange={handleModelChange}
              options={[
                { value: '', label: '自动（服务器默认）' },
                ...SPARK_MODELS.map(m => {
                  const authorized = models.find(am => am.modelCode === m.domain);
                  const suffix = authorized ? '' : '（未授权）';
                  return { value: m.domain, label: `${m.name}${suffix}` };
                }),
              ]}
            />

            <Divider style={{ margin: '16px 0 12px' }} />

            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>用户 ID</Typography.Text>
              <Typography.Text>{info.user_id || '未设置'}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8 }}>创建时间</Typography.Text>
              <Typography.Text>{info.created_at || '未知'}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8 }}>流式请求数</Typography.Text>
              <Typography.Text>{stats?.stream_count || 0}</Typography.Text>

              <Divider style={{ margin: '12px 0 8px' }} />

              <Typography.Text type="secondary" style={{ fontSize: 12 }}>API Key（代理认证）</Typography.Text>
              <Space size={4}>
                <Typography.Text code>{maskKey(apiKey)}</Typography.Text>
                <Button size="small" type="link" icon={<CopyOutlined />} style={{ padding: 0, height: 'auto', minWidth: 0 }} onClick={() => { navigator.clipboard.writeText(apiKey); message.success('已复制 API Key'); }} />
              </Space>
              <Popconfirm title="轮换后旧 API Key 将立即失效，确定继续？" onConfirm={handleRenewKey}>
                <Button size="small" icon={<SyncOutlined />} style={{ marginTop: 4 }}>轮换 API Key</Button>
              </Popconfirm>
            </Space>
          </Col>

          <Col xs={24} md={16}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>可用模型</Typography.Text>
              <AntTooltip title={TIER_EXPLANATION} overlayStyle={{ maxWidth: 360 }}>
                <QuestionCircleOutlined style={{ color: '#999', fontSize: 13, cursor: 'pointer' }} />
              </AntTooltip>
            </div>
            <Table
              dataSource={SPARK_MODELS.map(m => {
                const authorized = models.find(am => am.modelCode === m.domain);
                return { ...m, authorized: !!authorized, tokenExhausted: authorized?.tokenExhausted || false, key: m.domain };
              }) as any}
              columns={[
                {
                  title: '模型',
                  key: 'name',
                  render: (_: unknown, record: any) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text strong>{record.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>{record.domain}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '等级',
                  key: 'tier',
                  width: 70,
                  render: (_: unknown, record: any) => {
                    if (record.tier === 'free') return <Tag color="green">免费</Tag>;
                    if (record.tier === 'premium') return <Tag color="gold">旗舰版</Tag>;
                    return <Tag color="blue">专业版</Tag>;
                  },
                },
                { title: '参数量', dataIndex: 'params', key: 'params', width: 100 },
                { title: '上下文', key: 'context', width: 60, render: (_: unknown, record: any) => formatContextLength(record.contextLength) },
                {
                  title: '能力',
                  key: 'capabilities',
                  render: (_: unknown, record: any) => (
                    <Space size={[4, 4]} wrap>
                      {record.capabilities.slice(0, 2).map((c: string) => <Tag key={c} color="blue" style={{ fontSize: 11 }}>{c}</Tag>)}
                      {record.capabilities.length > 2 && <Tag style={{ fontSize: 11 }}>+{record.capabilities.length - 2}</Tag>}
                    </Space>
                  ),
                },
                {
                  title: '状态',
                  key: 'status',
                  width: 80,
                  render: (_: unknown, record: any) => {
                    if (record.status === 'deprecated') return <Tag color="orange">下线</Tag>;
                    if (record.authorized && record.tokenExhausted) return <Tag color="red">用尽</Tag>;
                    if (record.authorized) return <Tag color="green">已授权</Tag>;
                    return <Tag>未授权</Tag>;
                  },
                },
              ]}
              pagination={false}
              size="small"
            />
          </Col>
        </Row>
      </Card>

      {/* 4. Startup Commands */}
      <Card title="启动命令" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <CommandPreview label="Claude Code" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />
          </Col>
          <Col xs={24}>
            <CommandPreview label="Codex" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />
          </Col>
        </Row>
      </Card>

      {/* 5. Recent Request Logs */}
      {recentLogs.length > 0 && (
        <Card title="最近请求日志" style={{ marginBottom: 16 }}>
          <Table
            dataSource={recentLogs}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 700 }}
            columns={[
              {
                title: '时间',
                dataIndex: 'created_at',
                key: 'created_at',
                width: 160,
                render: (v: string) => v ? v.replace('T', ' ').slice(0, 19) : '',
              },
              { title: '模型', dataIndex: 'model', key: 'model', width: 120, ellipsis: true },
              { title: '端点', dataIndex: 'endpoint', key: 'endpoint', width: 140, ellipsis: true },
              {
                title: '状态',
                dataIndex: 'status_code',
                key: 'status_code',
                width: 70,
                render: (v: number) => <Tag color={v < 400 ? 'green' : 'red'}>{v}</Tag>,
              },
              {
                title: '延迟',
                dataIndex: 'latency_ms',
                key: 'latency_ms',
                width: 80,
                render: (v: number) => `${v}ms`,
              },
              {
                title: '流式',
                dataIndex: 'stream',
                key: 'stream',
                width: 50,
                render: (v: number) => v ? '是' : '否',
              },
              {
                title: 'Tokens',
                key: 'tokens',
                width: 100,
                render: (_: unknown, r: RecentLogEntry) => {
                  const total = (r.prompt_tokens || 0) + (r.completion_tokens || 0);
                  return total > 0 ? total.toLocaleString() : '-';
                },
              },
            ]}
          />
        </Card>
      )}

      {/* 6. Analytics */}
      {(stats && (stats.by_model.length > 0 || stats.by_endpoint.length > 0)) && (
        <Card title="使用分析" style={{ marginBottom: 16 }}>
          <Row gutter={[24, 16]}>
            {stats.by_model.length > 0 && (
              <Col xs={24} md={14}>
                <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>模型使用分布</Typography.Text>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={stats.by_model}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="model" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" name="请求次数" fill="#1677ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Col>
            )}
            {stats.by_endpoint.length > 0 && (
              <Col xs={24} md={10}>
                <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>端点调用统计</Typography.Text>
                <Table
                  dataSource={stats.by_endpoint}
                  columns={[
                    { title: '端点', dataIndex: 'endpoint', key: 'endpoint' },
                    { title: '调用次数', dataIndex: 'count', key: 'count', width: 80 },
                  ]}
                  rowKey="endpoint"
                  pagination={false}
                  size="small"
                />
              </Col>
            )}
          </Row>
        </Card>
      )}
    </div>
  );
};

export default AccountDetail;
