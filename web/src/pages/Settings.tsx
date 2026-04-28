import React, { useEffect, useState } from 'react';
import {
  Card, Form, Input, InputNumber, Switch, Select, Button, Space, message, Spin, Typography,
} from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../api';

interface SettingGroup {
  title: string;
  items: SettingItem[];
}

interface SettingItem {
  key: string;
  label: string;
  type: 'text' | 'number' | 'switch' | 'select';
  placeholder?: string;
  tooltip?: string;
  options?: { value: string; label: string }[];
  numberPlaceholder?: number;
}

const SETTING_GROUPS: SettingGroup[] = [
  {
    title: '网络配置',
    items: [
      { key: 'base_url', label: 'iFlyCode API 地址', type: 'text', placeholder: 'https://iflycode-xfsaas.xfyun.cn', tooltip: 'iFlyCode 服务的基础 URL' },
      { key: 'proxy_host', label: '代理监听地址', type: 'text', placeholder: '0.0.0.0', tooltip: '代理服务器绑定的主机地址' },
      { key: 'proxy_port', label: '代理监听端口', type: 'number', numberPlaceholder: 40419, tooltip: '代理服务器绑定的端口' },
    ],
  },
  {
    title: '模型配置',
    items: [
      { key: 'default_model', label: '默认模型', type: 'text', placeholder: '留空使用服务器默认', tooltip: '未指定模型时使用的默认模型' },
      { key: 'max_tokens', label: '最大 Token 数', type: 'number', numberPlaceholder: 8000, tooltip: '单次请求的最大 token 数' },
    ],
  },
  {
    title: '连接优化',
    items: [
      { key: 'connect_timeout', label: '连接超时 (秒)', type: 'number', numberPlaceholder: 10, tooltip: '与 iFlyCode 建立连接的超时时间' },
      { key: 'read_timeout', label: '读取超时 (秒)', type: 'number', numberPlaceholder: 120, tooltip: '等待响应数据的超时时间' },
      { key: 'max_retries', label: '最大重试次数', type: 'number', numberPlaceholder: 2, tooltip: '请求失败后的最大重试次数' },
    ],
  },
  {
    title: '日志与安全',
    items: [
      { key: 'log_enabled', label: '请求日志', type: 'switch', tooltip: '记录所有 API 请求到数据库' },
      { key: 'log_retention_days', label: '日志保留天数', type: 'number', numberPlaceholder: 30, tooltip: '超过此天数的日志将自动清理' },
    ],
  },
];

const Settings: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = await api.getSettings();
      const values: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(data)) {
        if (val === 'true') values[key] = true;
        else if (val === 'false') values[key] = false;
        else if (typeof val === 'string' && /^\d+$/.test(val)) values[key] = parseInt(val, 10);
        else values[key] = val;
      }
      form.setFieldsValue(values);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { fetchSettings(); }, []);

  const handleSave = async (values: Record<string, unknown>) => {
    setSaving(true);
    try {
      const payload: Record<string, string> = {};
      for (const [key, val] of Object.entries(values)) {
        if (val === undefined || val === null) continue;
        payload[key] = String(val);
      }
      await api.updateSettings(payload);
      message.success('设置已保存');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>系统设置</Typography.Title>
        <Button icon={<ReloadOutlined />} onClick={fetchSettings}>重置</Button>
      </div>

      <Form form={form} layout="vertical" onFinish={handleSave}>
        {SETTING_GROUPS.map(group => (
          <Card key={group.title} title={group.title} style={{ marginBottom: 16 }}>
            {group.items.map(item => (
              <Form.Item
                key={item.key}
                name={item.key}
                label={item.label}
                tooltip={item.tooltip}
                valuePropName={item.type === 'switch' ? 'checked' : 'value'}
              >
                {item.type === 'text' && <Input placeholder={item.placeholder} />}
                {item.type === 'number' && <InputNumber style={{ width: '100%' }} placeholder={item.numberPlaceholder !== undefined ? String(item.numberPlaceholder) : undefined} />}
                {item.type === 'switch' && <Switch />}
                {item.type === 'select' && (
                  <Select placeholder={String(item.placeholder || '')} options={item.options} />
                )}
              </Form.Item>
            ))}
          </Card>
        ))}

        <Space>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存设置</Button>
        </Space>
      </Form>
    </div>
  );
};

export default Settings;
