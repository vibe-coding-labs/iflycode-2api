import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Col, Row, Statistic, Typography, Spin, Select, Button,
  Breadcrumb, Space, Tag, Table, message, Popover,
} from 'antd';
import {
  ArrowLeftOutlined, ApiOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { AnthropicIcon, OpenAIIcon } from '../components/BrandIcons';
import { api } from '../api';

interface AccountStats {
  api_key: string;
  total_requests: number;
  by_model: { model: string; count: number }[];
  by_endpoint: { endpoint: string; count: number }[];
  avg_latency_ms: number;
  stream_count: number;
  error_count: number;
  prompt_tokens: number;
  completion_tokens: number;
}

interface AccountInfo {
  api_key: string;
  user_id: string;
  is_default: boolean;
  default_model: string;
  created_at?: string;
}

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
    <div style={{ maxWidth: 480 }}>
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

const AccountDetail: React.FC = () => {
  const { apiKey } = useParams<{ apiKey: string }>();
  const navigate = useNavigate();
  const decodedKey = decodeURIComponent(apiKey || '');

  const [info, setInfo] = useState<AccountInfo | null>(null);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const accounts = await api.listAccounts();
      const acc = accounts.find(a => a.api_key === decodedKey);
      if (acc) {
        setInfo(acc);
        setSelectedModel(acc.default_model);
      }
    } catch { /* ignore */ }

    try {
      const s = await api.getAccountStats(decodedKey);
      setStats(s);
    } catch { /* ignore */ }

    try {
      const m = await api.getAccountModels(decodedKey);
      setModels(m);
    } catch { /* ignore */ }

    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [decodedKey]);

  const handleModelChange = async (model: string) => {
    try {
      await api.updateAccountModel(decodedKey, model);
      setSelectedModel(model);
      message.success('默认模型已更新');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失败');
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!info) return <Typography.Text type="danger">账号不存在</Typography.Text>;

  const successRate = stats && stats.total_requests > 0
    ? ((stats.total_requests - stats.error_count) / stats.total_requests * 100).toFixed(1)
    : '0.0';

  const claudeCmd = `API_TIMEOUT_MS=6000000 \\\nCLAUDE_CODE_MAX_RETRIES=1000000 \\\nCLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 \\\nANTHROPIC_BASE_URL=http://localhost:40419 \\\nANTHROPIC_AUTH_TOKEN="${decodedKey}" \\\nclaude --dangerously-skip-permissions`;
  const codexCmd = `OPENAI_API_KEY="${decodedKey}" \\\nOPENAI_BASE_URL=http://localhost:40419/v1 \\\ncodex`;

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: <a onClick={() => navigate('/accounts')}>账号管理</a> },
          { title: decodedKey },
        ]}
      />

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/accounts')}>返回</Button>
          <Typography.Title level={4} style={{ margin: 0 }}>{decodedKey}</Typography.Title>
          {info.is_default && <Tag color="blue">默认账号</Tag>}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="总请求数" value={stats?.total_requests || 0} prefix={<ApiOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="平均延迟" value={stats?.avg_latency_ms || 0} suffix="ms" prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="成功率" value={successRate} suffix="%" prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="错误请求" value={stats?.error_count || 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Prompt Tokens" value={stats?.prompt_tokens || 0} valueStyle={{ color: '#1677ff' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Completion Tokens" value={stats?.completion_tokens || 0} valueStyle={{ color: '#722ed1' }} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="流式请求" value={stats?.stream_count || 0} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card title="默认模型">
            <Select
              style={{ width: '100%' }}
              placeholder="使用服务器默认模型"
              allowClear
              value={selectedModel || undefined}
              onChange={handleModelChange}
              options={[
                { value: '', label: '自动（服务器默认）' },
                ...models.map(m => ({ value: m, label: m })),
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="账号信息">
            <Typography.Text type="secondary">用户 ID: </Typography.Text>
            <Typography.Text>{info.user_id || '未设置'}</Typography.Text>
            <br />
            <Typography.Text type="secondary">创建时间: </Typography.Text>
            <Typography.Text>{info.created_at || '未知'}</Typography.Text>
          </Card>
        </Col>
      </Row>

      <Card title="启动命令" style={{ marginTop: 16 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          点击图标复制启动命令，环境变量会自动将请求路由到此账号。
        </Typography.Paragraph>
        <Space size="middle">
          <Popover
            placement="bottomLeft"
            trigger="hover"
            content={<CommandPreview label="Claude Code 启动命令" cmd={claudeCmd} onCopy={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }} />}
          >
            <Button
              icon={<AnthropicIcon size={14} />}
              onClick={() => { navigator.clipboard.writeText(claudeCmd); message.success('已复制 Claude Code 启动命令'); }}
            >
              Claude Code
            </Button>
          </Popover>
          <Popover
            placement="bottomLeft"
            trigger="hover"
            content={<CommandPreview label="Codex 启动命令" cmd={codexCmd} onCopy={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }} />}
          >
            <Button
              icon={<OpenAIIcon size={14} />}
              onClick={() => { navigator.clipboard.writeText(codexCmd); message.success('已复制 Codex 启动命令'); }}
            >
              Codex
            </Button>
          </Popover>
        </Space>
      </Card>

      {stats && stats.by_model.length > 0 && (
        <Card title="模型使用分布" style={{ marginTop: 16 }}>
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

      {stats && stats.by_endpoint.length > 0 && (
        <Card title="端点调用统计" style={{ marginTop: 16 }}>
          <Table
            dataSource={stats.by_endpoint}
            columns={[
              { title: '端点', dataIndex: 'endpoint', key: 'endpoint' },
              { title: '调用次数', dataIndex: 'count', key: 'count' },
            ]}
            rowKey="endpoint"
            pagination={false}
            size="small"
          />
        </Card>
      )}
    </div>
  );
};

export default AccountDetail;
