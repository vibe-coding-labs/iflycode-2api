import React, { useEffect, useState } from 'react';
import {
  Table, Typography, Tag, Button, InputNumber, Space, Spin,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { api } from '../api';

interface LogEntry {
  id: number;
  api_key: string;
  model: string;
  endpoint: string;
  stream: number;
  status_code: number;
  latency_ms: number;
  created_at: string;
}

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState(200);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await api.getLogs(limit);
      setLogs(data);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchLogs(); }, []);

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
    },
    {
      title: '账号',
      dataIndex: 'api_key',
      key: 'api_key',
      width: 150,
      render: (text: string) => <Typography.Text code>{text || '-'}</Typography.Text>,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      width: 150,
      render: (text: string) => text || <Tag>默认</Tag>,
    },
    {
      title: '端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
      width: 200,
    },
    {
      title: '流式',
      dataIndex: 'stream',
      key: 'stream',
      width: 80,
      render: (v: number) => v ? <Tag color="blue">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 100,
      render: (v: number) => {
        const color = v < 400 ? 'green' : v < 500 ? 'orange' : 'red';
        return <Tag color={color}>{v}</Tag>;
      },
    },
    {
      title: '延迟',
      dataIndex: 'latency_ms',
      key: 'latency_ms',
      width: 100,
      render: (v: number) => `${v}ms`,
      sorter: (a: LogEntry, b: LogEntry) => a.latency_ms - b.latency_ms,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>请求日志</Typography.Title>
        <Space>
          <span>显示条数:</span>
          <InputNumber min={10} max={1000} value={limit} onChange={v => setLimit(v || 100)} />
          <Button icon={<ReloadOutlined />} onClick={fetchLogs}>刷新</Button>
        </Space>
      </div>

      <Table
        dataSource={logs}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20, showTotal: total => `共 ${total} 条` }}
        locale={{ emptyText: '暂无请求记录' }}
        scroll={{ x: 960 }}
        size="small"
      />
    </div>
  );
};

export default Logs;
