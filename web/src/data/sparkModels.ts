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
  tier: 'free' | 'paid' | 'premium';
  tierLabel: string;
  supportsToolUse: boolean;
  supportsCoding: boolean;
  permissionCode?: string;
}

/** Determine model type from upstream permissionCode. */
export function getModelTypeFromPermission(permissionCode: string): 'chat' | 'coding' {
  if (permissionCode === 'INLINE_CHAT') return 'coding';
  return 'chat';
}

/** Determine model type label for display. */
export function getModelTypeLabel(model: SparkModelInfo): string {
  if (model.permissionCode) {
    return getModelTypeFromPermission(model.permissionCode) === 'coding' ? 'Coding' : 'Chat';
  }
  return model.supportsCoding ? 'Coding' : 'Chat';
}

export const SPARK_MODELS: SparkModelInfo[] = [
  {
    domain: '4.0Ultra',
    name: '星火 4.0 Ultra',
    params: '~293B (MoE, 激活~30B)',
    contextLength: 32768,
    maxOutput: 32768,
    description: '最新旗舰模型，已升级至 X1.5 快思考模式，推荐使用',
    capabilities: ['系统角色', '联网搜索（标准/深度）', '搜索来源返回', '搜索插件'],
    status: 'available',
    tier: 'premium',
    tierLabel: '旗舰版',
    supportsToolUse: true,
    supportsCoding: true,
  },
  {
    domain: 'max-32k',
    name: '星火 Max-32K',
    params: '~100B+',
    contextLength: 32768,
    maxOutput: 32768,
    description: 'Max 长上下文版本，32K 上下文窗口（即将下线）',
    capabilities: ['联网搜索', '搜索来源返回', '搜索插件'],
    status: 'deprecated',
    deprecatedDate: '2026-03-10',
    tier: 'paid',
    tierLabel: '专业版',
    supportsToolUse: true,
    supportsCoding: true,
  },
  {
    domain: 'generalv3.5',
    name: '星火 Max',
    params: '~100B+',
    contextLength: 8192,
    maxOutput: 8192,
    description: 'Max 标准版本（即将下线）',
    capabilities: ['系统角色', '联网搜索', '搜索来源返回', '搜索插件'],
    status: 'deprecated',
    deprecatedDate: '2026-03-10',
    tier: 'paid',
    tierLabel: '专业版',
    supportsToolUse: true,
    supportsCoding: true,
  },
  {
    domain: 'pro-128k',
    name: '星火 Pro-128K',
    params: '~30B',
    contextLength: 131072,
    maxOutput: 131072,
    description: 'Pro 长上下文版本，128K 上下文窗口',
    capabilities: ['联网搜索', '搜索插件'],
    status: 'available',
    tier: 'paid',
    tierLabel: '专业版',
    supportsToolUse: true,
    supportsCoding: true,
  },
  {
    domain: 'generalv3',
    name: '星火 Pro',
    params: '~30B',
    contextLength: 8192,
    maxOutput: 8192,
    description: 'Pro 标准版本',
    capabilities: ['联网搜索', '搜索插件'],
    status: 'available',
    tier: 'paid',
    tierLabel: '专业版',
    supportsToolUse: true,
    supportsCoding: false,
  },
  {
    domain: 'lite',
    name: '星火 Lite',
    params: '~10B',
    contextLength: 4096,
    maxOutput: 8192,
    description: '轻量免费版本，适合简单任务',
    capabilities: [],
    status: 'available',
    tier: 'free',
    tierLabel: '免费',
    supportsToolUse: false,
    supportsCoding: false,
  },
  {
    domain: 'kjwx',
    name: '科技文献大模型',
    params: '~30B',
    contextLength: 0,
    maxOutput: 0,
    description: '针对学术论文问答、写作和垂直领域优化',
    capabilities: ['学术论文', '文献检索'],
    status: 'available',
    tier: 'paid',
    tierLabel: '专业版',
    supportsToolUse: false,
    supportsCoding: false,
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

export const TIER_EXPLANATION = `模型可用性取决于你的讯飞开放平台账号等级：

- **免费**：所有账号均可使用
- **专业版**：需在讯飞开放平台购买或开通对应模型的权限
- **旗舰版**：需在讯飞开放平台购买旗舰版套餐

如果模型显示"未授权"，说明当前账号未开通该模型的权限。
请前往 讯飞开放平台控制台 → 我的应用 → 添加对应模型的服务。

提示：即使未授权，你也可以选择模型并发送请求，但服务器可能返回错误。`;
