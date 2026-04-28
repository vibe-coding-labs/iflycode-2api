import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Table, Typography, Tag, Button, InputNumber, Space, Spin, Select,
} from 'antd';
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import { Modal, message } from 'antd';
import { api } from '../api';
import type { Account } from '../api';

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

const STATUS_FILTERS = [
  { value: 0, label: '全部状态' },
  { value: 1, label: '成功 (<400)' },
  { value: 2, label: '失败 (>=400)' },
];

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState(200);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [filterAccount, setFilterAccount] = useState<string>('');
  const [filterModel, setFilterModel] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<number>(0);
  const [autoRefresh, setAutoRefresh] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getLogs(limit, {
        api_key: filterAccount || undefined,
        model: filterModel || undefined,
        status: filterStatus || undefined,
      });
      setLogs(data);
    } catch { /* ignore */ }
    setLoading(false);
  }, [limit, filterAccount, filterModel, filterStatus]);

  useEffect(() => {
    api.listAccounts().then(setAccounts).catch(() => {});
  }, []);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (autoRefresh > 0) {
      timerRef.current = setInterval(fetchLogs, autoRefresh * 1000);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [autoRefresh, fetchLogs]);

  const handleCleanup = () => {
    Modal.confirm({
      title: '清理日志',
      content: '确定清理 30 天前的日志记录？',
      onOk: async () => {
        try {
          const result = await api.cleanupLogs(30);
          message.success(`已清理 ${result.removed} 条日志`);
          fetchLogs();
        } catch (e: unknown) {
          message.error(e instanceof Error ? e.message : '清理失败');
        }
      },
    });
  };

  const modelOptions = [...new Set(logs.map(l => l.model).filter(Boolean))].map(m => ({ value: m, label: m }));

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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>请求日志</Typography.Title>
        <Space wrap>
          <Select
            value={filterAccount}
            onChange={setFilterAccount}
            options={[{ value: '', label: '全部账号' }, ...accounts.map(a => ({ value: a.api_key, label: a.api_key }))]}
            style={{ width: 140 }}
            size="small"
          />
          <Select
            value={filterModel}
            onChange={setFilterModel}
            options={[{ value: '', label: '全部模型' }, ...modelOptions]}
            style={{ width: 140 }}
            size="small"
          />
          <Select
            value={filterStatus}
            onChange={setFilterStatus}
            options={STATUS_FILTERS}
            style={{ width: 130 }}
            size="small"
          />
          <InputNumber min={10} max={1000} value={limit} onChange={v => setLimit(v || 100)} size="small" style={{ width: 80 }} />
          <Select
            value={autoRefresh}
            onChange={setAutoRefresh}
            options={[{ value: 0, label: '不刷新' }, { value: 5, label: '5秒' }, { value: 15, label: '15秒' }, { value: 30, label: '30秒' }]}
            style={{ width: 90 }}
            size="small"
          />
          <Button size="small" icon={<ReloadOutlined />} onClick={fetchLogs}>刷新</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={handleCleanup}>清理</Button>
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
