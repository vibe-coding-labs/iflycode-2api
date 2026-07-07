# 可用模型列表展示 — 模型元数据 + 详情页展示

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在账号详情页展示该账号可用的 iFlyCode/SparkDesk 模型列表，包含模型名称、domain 代码、参数量、上下文长度、能力描述等元数据，让用户对账号可用模型有清晰认知。

**Architecture:** 创建 sparkModels.ts 静态模型元数据映射（domain 代码 → 名称/参数量/上下文/能力）→ 后端 get_account_models 返回完整模型对象（modelCode + modelName + tokenExhausted + checked）→ 前端用表格展示模型列表，合并 API 返回的可用状态与静态元数据 → 默认模型选择器也展示完整模型名称。

**Tech Stack:** React 18, Ant Design 5, FastAPI, Python 3.12

**Risks:**
- queryUserFuncModelList 对免费账号返回空列表 — 缓解：始终展示全部已知 SparkDesk 模型，API 返回的模型标记为"已授权"，其余标记为"未授权"
- 模型元数据需手动维护 — 缓解：集中在一个文件 sparkModels.ts，从讯飞官方文档获取

---

### Task 1: 后端改进模型列表 API + 前端添加模型元数据

**Depends on:** None
**Files:**
- Modify: `iflycode_proxy/db.py:323-334`（get_account_models 返回完整模型对象）
- Modify: `iflycode_proxy/client.py:117-128`（list_models 返回完整数据）
- Create: `web/src/data/sparkModels.ts`
- Modify: `web/src/api.ts:63-64`（更新 getAccountModels 返回类型）
- Modify: `web/src/pages/AccountDetail.tsx:110-112,206-220`（模型列表展示区域）

- [ ] **Step 1: 修改 client.py 的 list_models 方法 — 返回完整模型数据而非仅 modelCode**

文件: `iflycode_proxy/client.py:117-128`（替换 list_models 方法）

```python
    def list_models(self) -> List[Dict]:
        try:
            resp = self._http.post(
                f"{MODEL_LIST_ENDPOINT}?token={self.token}",
                headers=self._headers(),
                json={"token": self.token},
            )
            data = resp.json()
            raw = data.get("obj") or data.get("data") or []
            # Flatten FunctionModelInfo -> codeModelList
            models = []
            for item in raw:
                if isinstance(item, dict):
                    code_list = item.get("codeModelList")
                    if isinstance(code_list, list):
                        models.extend(code_list)
                    elif item.get("modelCode"):
                        models.append(item)
            return models
        except Exception as e:
            log.warning("Failed to fetch models: %s", e)
            return []
```

- [ ] **Step 2: 修改 db.py 的 get_account_models 方法 — 返回完整模型对象列表**

文件: `iflycode_proxy/db.py:323-334`（替换 get_account_stats 方法之后的 get_account_models 方法）

```python
    def get_account_models(self, api_key: str) -> List[Dict]:
        acc = self.get_account(api_key)
        if not acc:
            return []
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["token"], acc.get("user_id", ""))
            models_data = client.list_models()
            client.close()
            result = []
            for m in models_data:
                if not isinstance(m, dict):
                    continue
                result.append({
                    "modelCode": m.get("modelCode", m.get("name", "")),
                    "modelName": m.get("modelName", m.get("name", "")),
                    "modelId": m.get("modelId", ""),
                    "checked": m.get("checked", False),
                    "tokenExhausted": m.get("tokenExhausted", False),
                })
            return result
        except Exception:
            return []
```

- [ ] **Step 3: 创建 sparkModels.ts — SparkDesk 已知模型元数据静态映射**

```typescript
// web/src/data/sparkModels.ts

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
```

- [ ] **Step 4: 更新 api.ts 的 getAccountModels 返回类型**

文件: `web/src/api.ts:63-64`（替换 getAccountModels 行）

```typescript
  getAccountModels: (apiKey: string) =>
    request<{ models: { modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean }[] }>(`/api/accounts/${encodeURIComponent(apiKey)}/models`).then(r => r.models || []),
```

- [ ] **Step 5: 修改 AccountDetail.tsx — 添加模型列表展示区域**

文件: `web/src/pages/AccountDetail.tsx`

在文件顶部添加导入:
```typescript
import { SPARK_MODELS, getModelByDomain, formatContextLength } from '../data/sparkModels';
import type { SparkModelInfo } from '../data/sparkModels';
```

修改 state 声明（约第 110 行），将 `models: string[]` 改为:
```typescript
  const [models, setModels] = useState<{ modelCode: string; modelName: string; modelId: string; checked: boolean; tokenExhausted: boolean }[]>([]);
```

修改默认模型选择器（约第 208-220 行），替换为:
```typescript
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
                ...models.map(m => {
                  const meta = getModelByDomain(m.modelCode);
                  return { value: m.modelCode, label: m.modelName || meta?.name || m.modelCode };
                }),
              ]}
            />
          </Card>
        </Col>
```

在"端点调用统计"Card 之后（约第 276 行，`</div>` 之前），添加模型列表 Card:
```typescript
      <Card title="可用模型" style={{ marginTop: 16 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          以下为 iFlyCode/SparkDesk 支持的模型列表。已授权模型可设置为默认模型。
        </Typography.Paragraph>
        <Table
          dataSource={SPARK_MODELS.map(m => {
            const authorized = models.find(am => am.modelCode === m.domain);
            return {
              ...m,
              authorized: !!authorized,
              tokenExhausted: authorized?.tokenExhausted || false,
              key: m.domain,
            };
          })}
          columns={[
            {
              title: '模型',
              key: 'name',
              render: (_: unknown, record: SparkModelInfo & { authorized: boolean; tokenExhausted: boolean }) => (
                <Space direction="vertical" size={0}>
                  <Typography.Text strong>{record.name}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>domain: {record.domain}</Typography.Text>
                </Space>
              ),
            },
            {
              title: '参数量',
              dataIndex: 'params',
              key: 'params',
              width: 100,
            },
            {
              title: '上下文',
              key: 'context',
              width: 80,
              render: (_: unknown, record: SparkModelInfo) => formatContextLength(record.contextLength),
            },
            {
              title: '能力',
              key: 'capabilities',
              render: (_: unknown, record: SparkModelInfo) => (
                <Space size={[4, 4]} wrap>
                  {record.capabilities.map(c => <Tag key={c} color="blue">{c}</Tag>)}
                </Space>
              ),
            },
            {
              title: '状态',
              key: 'status',
              width: 100,
              render: (_: unknown, record: SparkModelInfo & { authorized: boolean; tokenExhausted: boolean }) => {
                if (record.status === 'deprecated') return <Tag color="orange">即将下线</Tag>;
                if (record.authorized && record.tokenExhausted) return <Tag color="red">次数已用尽</Tag>;
                if (record.authorized) return <Tag color="green">已授权</Tag>;
                return <Tag>未授权</Tag>;
              },
            },
          ]}
          pagination={false}
          size="small"
        />
      </Card>
```

- [ ] **Step 6: 验证前端构建**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api/web && npm run build`
Expected:
  - Exit code: 0
  - Output contains: "built in"

- [ ] **Step 7: 验证后端启动**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && lsof -ti:40419 2>/dev/null | xargs kill 2>/dev/null; sleep 1; .venv/bin/python -m iflycode_proxy.cli serve &>/tmp/iflycode-proxy.log & sleep 2 && curl -s http://localhost:40419/api/health`
Expected:
  - Output contains: `"status": "ok"`

- [ ] **Step 8: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add iflycode_proxy/client.py iflycode_proxy/db.py web/src/data/sparkModels.ts web/src/api.ts web/src/pages/AccountDetail.tsx && git commit -m "feat(ui): add SparkDesk model catalog with metadata in account detail page"`
