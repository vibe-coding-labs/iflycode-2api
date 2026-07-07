# iFlyCode 2API

把讯飞星火飞码变成 OpenAI API，这样 Claude Code、Codex 这些工具就能直接用了。

> **⚠️ 项目状态：上游服务已停服**
>
> 2026-06-10 经过全面排查，确认 iFlyCode 后端服务已彻底停服。详见[项目终止说明](#-上游服务已停服)。

---

## ⚠️ 上游服务已停服

### TL;DR

**iFlyCode 云端服务已停服，该项目已无法继续使用。**

### 详细说明

#### 背景

本项目是一个协议翻译代理，将 OpenAI/Anthropic API 格式的请求翻译为讯飞星火飞码（iFlyCode）的上游 API，让 Claude Code、Codex 等 AI 编程工具能够使用星火飞码的 AI 能力。

项目的核心依赖是 `iflycode-xfsaas.xfyun.cn` 这个上游 API 端点 —— 它在之前的某个时间点开始无法连接，导致项目被搁置。

#### 2026-06-10 全面排查结果

经过对多个角度的系统性测试，结果如下：

| 测试方式 | 绕过手段 | 结果 |
|---------|---------|------|
| 默认网络（经 Clash 日本节点代理回国） | — | **502 Bad Gateway** |
| DIRECT 直连（不走代理） | `--noproxy '*'` | **502 Bad Gateway** |
| 真实 IP 直连（绕过 Clash TUN 和 fake-ip DNS） | `--resolve` 绕过全部本机代理栈 | **502 Bad Gateway** |
| Python httpx 原生客户端 | 不走系统代理 | **502 Bad Gateway** |
| 真实 IP 直连 `iflycode.xfyun.cn` 主站 | `--resolve 180.163.145.11` | **502 Bad Gateway** |
| 真实 IP 直连 `iflycode-xfsaas.xfyun.cn` API | `--resolve 124.243.239.178` | **502 Bad Gateway** |
| **对照：`www.xfyun.cn`（讯飞开放平台主站）** | 正常访问 | **200 OK ✅** |

#### 结论

```
请求 → 阿里云CDN ✓ → TLS握手 ✓ → 阿里云WAF ✓ → Tengine网关 ✓
  → 转发到iFlyCode后端源站 → ✗ 源站服务器无响应 → 返回502
```

**不是本机环境/Clash代理的问题**，我们用 `--resolve` 完全绕过了本机全部网络栈（Clash TUN + fake-ip DNS + 代理配置），直连讯飞域名背后的阿里云CDN真实IP（`124.243.239.178` 和 `180.163.145.1x`），结果一样是 502。

**不是 WAF 拦截的问题**，因为 502 页面是 `Tengine` 返回的（CDN网关），错误页明确写的是"您当前访问的网站无法响应"——CDN能连上但**后端源站没有响应**。

**是 iFlyCode 的后端服务已经彻底下线/停服了。** 对比：
- `www.xfyun.cn` 正常工作 ✅
- 所有 `iflycode-*` 子域名全部 502 ❌

#### 对之前猜测的修正

之前 README 猜测"WAF 拦截了请求"，这次深入排查后排除了这个可能——WAF 不会返回 502 错误页面，而且正常劫持请求后 WAF 放行到后端源站这一步才超时。是讯飞那边的 iFlyCode 服务本身没有再运行了。

#### 项目现状

- **此 proxy 已无法正常工作**，因为上游 API 端点已不可用
- 代码库保留作为参考实现和逆向分析成果存档
- 相关逆向分析资料见 [iflycode-RE](https://github.com/vibe-coding-labs/iflycode-RE) 项目

---

## 一分钟上手

```bash
pip install -e .
iflycode-2api serve
```

打开 http://localhost:40419 添加你的讯飞 SSO 账号，搞定。

## 怎么用

**Claude Code：**

```bash
ANTHROPIC_BASE_URL=http://localhost:40419 \
ANTHROPIC_AUTH_TOKEN="你的Key" \
claude --dangerously-skip-permissions
```

**Codex：**

```bash
OPENAI_API_KEY="你的Key" OPENAI_BASE_URL=http://localhost:40419/v1 codex
```

**Python：**

```python
from openai import OpenAI
client = OpenAI(api_key="你的Key", base_url="http://localhost:40419/v1")
print(client.chat.completions.create(
    model="iflycode-default",
    messages=[{"role": "user", "content": "写个快排"}],
).choices[0].message.content)
```

## 能干啥

- 兼容 OpenAI 和 Anthropic 两种 API 格式，流式非流式都行
- 多账号池，自动轮换，不用操心限流
- Chat 和 Coding 两种模式，Coding 模式支持工具调用
- 自带管理面板，看统计、查日志、管账号
- 可以跑守护进程，崩了自动重启

## 模型

| ID | 啥是啥 |
|----|--------|
| `iflycode-default` | 普通聊天 |
| `iflycode-default-coding` | 写代码，支持 tool_use |
| `4.0Ultra` | 星火 4.0 Ultra |
| `pro-128k` | 星火 Pro 128K 长上下文 |
| `generalv3` | 星火 Pro |
| `lite` | 星火 Lite，免费的 |

> 星火飞码本身是编程助手，问它"今天天气怎么样"会被拒绝，问代码相关的问题没问题。

## 面板长这样

![数据概览](docs/imgs/数据概览.png)
![账号管理](docs/imgs/账号管理.png)
![账号详情](docs/imgs/账号管理%20-%20账号详情.png)
![聊天测试](docs/imgs/聊天测试.png)
![请求日志](docs/imgs/请求日志.png)
![系统设置](docs/imgs/系统设置.png)

## CLI

```bash
iflycode-2api serve [-p 端口] [--service]   # 启动，--service 跑后台
iflycode-2api stop-service                   # 停后台
iflycode-2api service-status                 # 看状态
```

## 技术栈

Python + FastAPI 后端，React + Ant Design 前端，SQLite 存数据。没什么花活。

## 相关项目

- [iflycode-RE](https://github.com/vibe-coding-labs/iflycode-RE) — 星火飞码插件的逆向分析，这个 proxy 就是基于它搞出来的

## License

MIT
