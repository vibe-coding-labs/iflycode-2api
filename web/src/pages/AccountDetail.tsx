import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Space, Tag, Table, message, Divider, Tooltip as AntTooltip, Popconfirm,
  Descriptions,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CopyOutlined, QuestionCircleOutlined, SyncOutlined,
  ClockCircleOutlined, DeleteOutlined, StarOutlined,
} from '@ant-design/icons';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, Legend, PieChart, Pie, Cell,
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
const fmtK = (v: number) => v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(1)}K` : String(v);

const formatHour = (h: string) => {
  const parts = h.split(' ');
  return parts.length >= 2 ? parts[1] : h;
};

const PIE_COLORS = ['#389e0d', '#722ed1', '#52c41a', '#faad14', '#ff4d4f', '#13c2c2', '#eb2f96'];

const AccountDetail: React.FC = () => {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const decodedId = decodeURIComponent(accountId || '');

  const [info, setInfo] = useState<Account | null>(null);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [hourlyData, setHourlyData] = useState<HourlyStatsPoint[]>([]);
  const [recentLogs, setRecentLogs] = useState<RecentLogEntry[]>([]);
  const [models, setModels] = useState<{ modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean; permissionCode: string; permissionName: string; language: string }[]>([]);
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

    try { setStats(await api.getAccountStats(decodedId)); } catch { /* ignore */ }
    try { const h = await api.getAccountHourlyStats(decodedId, hourRange); setHourlyData(h.data || []); } catch { /* ignore */ }
    try { setRecentLogs(await api.getAccountRecentLogs(decodedId, 20)); } catch { /* ignore */ }
    try { setModels(await api.getAccountModels(decodedId)); } catch { /* ignore */ }

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
    setSelectedModel(model);
    try {
      await api.updateAccountModel(decodedId, model || '');
      message.success('默认模型已更新');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  };

  const handleRenewKey = async () => {
    try {
      await api.renewApiKey(decodedId);
      message.success('API Key 已轮换');
      fetchData();
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '轮换失败');
    }
  };

  const handleDelete = async () => {
    try {
      await api.removeAccount(decodedId);
      message.success('账号已删除');
      navigate('/accounts');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '删除失败');
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!info) return <Typography.Text type="danger">账号不存在</Typography.Text>;

  const apiKey = info.api_key;
  const modelFlag = selectedModel ? ` --model ${selectedModel}` : '';
  const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${apiKey}" \\\nclaude --dangerously-skip-permissions${modelFlag}`;
  const codexCmd = `OPENAI_API_KEY="${apiKey}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex${modelFlag}`;
  const curlCmd = `curl http://localhost:40419/v1/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${apiKey}" \\\n  -d '{\n    "model": "${selectedModel || 'iflycode-default'}",\n    "messages": [{"role": "user", "content": "Hello"}],\n    "stream": true\n  }'`;
  const pythonCmd = `from openai import OpenAI\nclient = OpenAI(\n  api_key="${apiKey}",\n  base_url="http://localhost:40419/v1"\n)\nresp = client.chat.completions.create(\n  model="${selectedModel || 'iflycode-default'}",\n  messages=[{"role": "user", "content": "Hello"}]\n)\nprint(resp.choices[0].message.content)`;

  return (
    <div>
      {/* Header — account identity + actions */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounts')}>返回</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>{info.account_id}</Typography.Title>
          {info.is_default && <Tag color="blue">默认账号</Tag>}
        </Space>
        <Space>
          <Select
            size="small"
            style={{ width: 200 }}
            placeholder="默认模型"
            allowClear
            value={selectedModel || undefined}
            onChange={handleModelChange}
            options={[
              { value: '', label: '自动（服务器默认）' },
              { value: 'iflycode-default-coding', label: '自动选择 (Coding)' },
              ...SPARK_MODELS.flatMap(m => {
                const authorized = models.find(am => am.modelCode === m.domain);
                const suffix = authorized ? '' : '（未授权）';
                const items: { value: string; label: string }[] = [
                  { value: m.domain, label: `${m.name} [Chat]${suffix}` },
                ];
                if (m.supportsCoding) {
                  items.push({ value: `${m.domain}-coding`, label: `${m.name} [Coding]${suffix}` });
                }
                return items;
              }),
            ]}
          />
          <Popconfirm title="轮换后旧 API Key 将立即失效，确定继续？" onConfirm={handleRenewKey}>
            <Button size="small" icon={<SyncOutlined />}>轮换 Key</Button>
          </Popconfirm>
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
          <Popconfirm title="确定删除此账号？删除后不可恢复！" onConfirm={handleDelete}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      </div>

      {/* 1. Quick Start — 2-column for commands */}
      <Card title="快速接入" size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 12]}>
          <Col xs={24} md={12}>
            <CommandPreview label="Claude Code" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制'); }} />
          </Col>
          <Col xs={24} md={12}>
            <CommandPreview label="Codex" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制'); }} />
          </Col>
          <Col xs={24} md={12}>
            <CommandPreview label="OpenAI API (curl)" cmd={curlCmd} onCopy={() => { navigator.clipboard.writeText(curlCmd); message.success('已复制'); }} />
          </Col>
          <Col xs={24} md={12}>
            <CommandPreview label="Python (openai SDK)" cmd={pythonCmd} onCopy={() => { navigator.clipboard.writeText(pythonCmd); message.success('已复制'); }} />
          </Col>
        </Row>
      </Card>

      {/* 2. Stats — compact 2-column */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card title="请求统计" size="small">
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Statistic title="今日请求" value={stats?.today_requests || 0} prefix={<ApiOutlined />} valueStyle={{ fontSize: 20 }} />
                <Statistic title="累计请求" value={stats?.total_requests || 0} valueStyle={{ fontSize: 20 }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span><CheckCircleOutlined style={{ color: '#52c41a' }} /> 成功 {stats ? stats.today_requests - stats.today_errors : 0} <Tag color="green">{stats?.today_success_rate || 0}%</Tag></span>
                <span><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 失败 {stats?.today_errors || 0} <Tag color="red">{stats && stats.today_requests > 0 ? (100 - stats.today_success_rate).toFixed(1) : 0}%</Tag></span>
              </div>
              <div>
                <ClockCircleOutlined /> 流式 {stats?.stream_count || 0} &nbsp;|&nbsp; 平均延迟 <span style={{ color: (stats?.avg_latency_ms || 0) < 500 ? '#52c41a' : (stats?.avg_latency_ms || 0) < 1500 ? '#faad14' : '#ff4d4f' }}>{stats?.avg_latency_ms || 0}ms</span>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="Token 消耗" size="small">
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Statistic title="24h Tokens" value={fmtK((stats?.prompt_tokens_24h || 0) + (stats?.completion_tokens_24h || 0))} valueStyle={{ fontSize: 20, color: '#389e0d' }} />
                <Statistic title="累计 Tokens" value={fmtK((stats?.prompt_tokens || 0) + (stats?.completion_tokens || 0))} valueStyle={{ fontSize: 20, color: '#722ed1' }} />
              </div>
              <div>
                24h &mdash; Prompt: {fmtK(stats?.prompt_tokens_24h || 0)} / Completion: {fmtK(stats?.completion_tokens_24h || 0)}
              </div>
              <div>
                累计 &mdash; Prompt: {fmtK(stats?.prompt_tokens || 0)} / Completion: {fmtK(stats?.completion_tokens || 0)}
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 3. Hourly Charts — AreaChart */}
      {hourlyData.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} lg={12}>
            <Card title="请求趋势" size="small" extra={
              <Select size="small" value={hourRange} onChange={setHourRange} style={{ width: 100 }} options={[
                { value: 24, label: '24h' }, { value: 48, label: '48h' }, { value: 168, label: '7天' },
              ]} />
            }>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={hourlyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip labelFormatter={(l) => String(l)} />
                  <Legend />
                  <Area type="monotone" dataKey="request_count" name="请求数" stroke="#389e0d" fill="#389e0d" fillOpacity={0.15} strokeWidth={2} />
                  <Area type="monotone" dataKey="error_count" name="错误数" stroke="#ff4d4f" fill="#ff4d4f" fillOpacity={0.1} strokeWidth={1.5} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="Token 消耗趋势" size="small">
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={hourlyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tickFormatter={formatHour} tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip labelFormatter={(l) => String(l)} />
                  <Legend />
                  <Area type="monotone" dataKey="prompt_tokens" name="Prompt" stroke="#389e0d" fill="#389e0d" fillOpacity={0.15} strokeWidth={2} />
                  <Area type="monotone" dataKey="completion_tokens" name="Completion" stroke="#722ed1" fill="#722ed1" fillOpacity={0.1} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </Col>
        </Row>
      )}

      {/* 4. Account Info + Model Table — merged card */}
      <Card title="账号信息与模型" size="small" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="API Key">
            <Space size={4}>
              <Typography.Text code>{maskKey(apiKey)}</Typography.Text>
              <Button size="small" type="link" icon={<CopyOutlined />} style={{ padding: 0, height: 'auto', minWidth: 0 }} onClick={() => { navigator.clipboard.writeText(apiKey); message.success('已复制 API Key'); }} />
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="用户 ID">{info.user_id || '未设置'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{info.created_at || '未知'}</Descriptions.Item>
          <Descriptions.Item label="流式请求数">{stats?.stream_count || 0}</Descriptions.Item>
        </Descriptions>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>可用模型</Typography.Text>
          <AntTooltip title={TIER_EXPLANATION} overlayStyle={{ maxWidth: 360 }}>
            <QuestionCircleOutlined style={{ color: '#999', fontSize: 13, cursor: 'pointer' }} />
          </AntTooltip>
        </div>
        <Table
          dataSource={SPARK_MODELS.flatMap(m => {
            const authorized = models.find(am => am.modelCode === m.domain);
            const auth = !!authorized;
            const rows: any[] = [{ ...m, mode: 'chat', modelId: m.domain, modelName: `${m.name}`, authorized: auth, tokenExhausted: authorized?.tokenExhausted || false, key: m.domain }];
            if (m.supportsCoding) {
              rows.push({ ...m, mode: 'coding', modelId: `${m.domain}-coding`, modelName: `${m.name} (Coding)`, authorized: auth, tokenExhausted: authorized?.tokenExhausted || false, key: `${m.domain}-coding` });
            }
            return rows;
          }) as any}
          columns={[
            {
              title: '模型',
              key: 'name',
              render: (_: unknown, record: any) => (
                <Space direction="vertical" size={0}>
                  <Typography.Text strong>{record.modelName}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>{record.modelId}</Typography.Text>
                </Space>
              ),
            },
            {
              title: '等级', key: 'tier', width: 70,
              render: (_: unknown, record: any) => {
                if (record.tier === 'free') return <Tag color="green">免费</Tag>;
                if (record.tier === 'premium') return <Tag color="gold">旗舰版</Tag>;
                return <Tag color="blue">专业版</Tag>;
              },
            },
            {
              title: '模式', key: 'mode', width: 75,
              render: (_: unknown, record: any) => {
                if (record.mode === 'coding') return <Tag color="green" style={{ fontWeight: 600 }}>Coding</Tag>;
                return <Tag color="blue">Chat</Tag>;
              },
            },
            { title: '参数量', dataIndex: 'params', key: 'params', width: 100 },
            { title: '上下文', key: 'context', width: 60, render: (_: unknown, record: any) => formatContextLength(record.contextLength) },
            {
              title: '状态', key: 'status', width: 80,
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
      </Card>

      {/* 5. Usage Analytics — model dist + endpoint dist */}
      {(stats && (stats.by_model.length > 0 || stats.by_endpoint.length > 0)) && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {stats.by_model.length > 0 && (
            <Col xs={24} md={14}>
              <Card title="模型使用分布" size="small">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={stats.by_model} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis dataKey="model" type="category" width={100} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="请求次数" fill="#389e0d" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </Col>
          )}
          {stats.by_endpoint.length > 0 && (
            <Col xs={24} md={10}>
              <Card title="端点调用分布" size="small">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={stats.by_endpoint} dataKey="count" nameKey="endpoint" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }: any) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}>
                      {stats.by_endpoint.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Card>
            </Col>
          )}
        </Row>
      )}

      {/* 6. Recent Request Logs */}
      {recentLogs.length > 0 && (
        <Card title="最近请求日志" size="small" style={{ marginBottom: 16 }}>
          <Table
            dataSource={recentLogs}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 800 }}
            columns={[
              {
                title: '时间', dataIndex: 'created_at', key: 'created_at', width: 145,
                render: (v: string) => <Typography.Text code style={{ fontSize: 11 }}>{v ? v.replace('T', ' ').slice(0, 19) : ''}</Typography.Text>,
              },
              { title: '端点', dataIndex: 'endpoint', key: 'endpoint', width: 120, render: (v: string) => <Typography.Text code style={{ fontSize: 11 }}>{v}</Typography.Text> },
              { title: '模型', dataIndex: 'model', key: 'model', width: 100, ellipsis: true, render: (v: string) => v || '-' },
              {
                title: '流式', dataIndex: 'stream', key: 'stream', width: 50,
                render: (v: number) => v ? <Tag color="processing" style={{ fontSize: 11 }}>流</Tag> : <Tag style={{ fontSize: 11 }}>普</Tag>,
              },
              {
                title: '状态', dataIndex: 'status_code', key: 'status_code', width: 60,
                render: (v: number) => <Tag color={v < 300 ? 'green' : v < 400 ? 'orange' : 'red'}>{v}</Tag>,
              },
              {
                title: '输入', dataIndex: 'prompt_tokens', key: 'prompt_tokens', width: 70,
                render: (v: number) => v > 0 ? fmtK(v) : '-',
              },
              {
                title: '输出', dataIndex: 'completion_tokens', key: 'completion_tokens', width: 70,
                render: (v: number) => v > 0 ? fmtK(v) : '-',
              },
              {
                title: '延迟', dataIndex: 'latency_ms', key: 'latency_ms', width: 70,
                render: (v: number) => {
                  const color = v < 500 ? '#52c41a' : v < 1500 ? '#faad14' : '#ff4d4f';
                  return <span style={{ color, fontWeight: v >= 1500 ? 600 : 400 }}>{v}ms</span>;
                },
              },
            ]}
          />
        </Card>
      )}
    </div>
  );
};

export default AccountDetail;
