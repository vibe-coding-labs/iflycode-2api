export interface SparkModelInfo {
  domain: string;
  name: string;
  params: string;
  contextLength: number;
  maxOutput: number;
  description: string;
  capabilities: string[];
  status: 'available' | 'deprecated' | 'upcoming';
  deprecatedDate?: string;
}

export const SPARK_MODELS: SparkModelInfo[] = [
  {
    domain: '4.0Ultra',
    name: '星火 4.0 Ultra',
    params: '未公开',
    contextLength: 32768,
    maxOutput: 32768,
    description: '最新旗舰模型，已升级至 X1.5 快思考模式，推荐使用',
    capabilities: ['系统角色', '联网搜索（标准/深度）', '搜索来源返回', '搜索插件'],
    status: 'available',
  },
  {
    domain: 'max-32k',
    name: '星火 Max-32K',
    params: '未公开',
    contextLength: 32768,
    maxOutput: 32768,
    description: 'Max 长上下文版本，32K 上下文窗口',
    capabilities: ['联网搜索', '搜索来源返回', '搜索插件'],
    status: 'deprecated',
    deprecatedDate: '2026-03-10',
  },
  {
    domain: 'generalv3.5',
    name: '星火 Max',
    params: '未公开',
    contextLength: 8192,
    maxOutput: 8192,
    description: 'Max 标准版本',
    capabilities: ['系统角色', '联网搜索', '搜索来源返回', '搜索插件'],
    status: 'deprecated',
    deprecatedDate: '2026-03-10',
  },
  {
    domain: 'pro-128k',
    name: '星火 Pro-128K',
    params: '未公开',
    contextLength: 131072,
    maxOutput: 131072,
    description: 'Pro 长上下文版本，128K 上下文窗口',
    capabilities: ['联网搜索', '搜索插件'],
    status: 'available',
  },
  {
    domain: 'generalv3',
    name: '星火 Pro',
    params: '未公开',
    contextLength: 8192,
    maxOutput: 8192,
    description: 'Pro 标准版本',
    capabilities: ['联网搜索', '搜索插件'],
    status: 'available',
  },
  {
    domain: 'lite',
    name: '星火 Lite',
    params: '未公开',
    contextLength: 4096,
    maxOutput: 8192,
    description: '轻量版本，适合简单任务',
    capabilities: [],
    status: 'available',
  },
  {
    domain: 'kjwx',
    name: '科技文献大模型',
    params: '未公开',
    contextLength: 0,
    maxOutput: 0,
    description: '针对学术论文问答、写作和垂直领域优化',
    capabilities: ['学术论文', '文献检索'],
    status: 'available',
  },
];

export function getModelByDomain(domain: string): SparkModelInfo | undefined {
  return SPARK_MODELS.find(m => m.domain === domain);
}

export function formatContextLength(tokens: number): string {
  if (tokens >= 131072) return '128K';
  if (tokens >= 32768) return '32K';
  if (tokens >= 8192) return '8K';
  if (tokens >= 4096) return '4K';
  if (tokens === 0) return '未知';
  return `${tokens}`;
}
