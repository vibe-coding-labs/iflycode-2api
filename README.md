# iFlyCode Proxy

将讯飞 iFlyCode (星火认知大模型) 代理为 OpenAI 兼容 API，支持 Claude Code、Codex 等工具直接接入。

## 功能

- **OpenAI 兼容** — `/v1/chat/completions`、`/v1/models` 端点，流式/非流式均支持
- **Anthropic 兼容** — `/v1/messages` 端点，支持 Claude Code 直接连接
- **账号池** — 多账号管理，自动负载均衡，API Key 轮换
- **模型选择** — Chat / Coding 双模式，支持指定上游模型
- **管理面板** — Web Dashboard 查看统计、日志、Token 消耗
- **守护进程** — 后台运行，崩溃自动重启

## 快速开始

### 安装

```bash
pip install -e .
```

### 启动

```bash
# 前台运行
iflycode-proxy serve

# 后台守护进程
iflycode-proxy serve --service

# 自定义端口
iflycode-proxy serve -p 8080
```

默认监听 `http://0.0.0.0:40419`。

### 添加账号

首次启动后，打开 `http://localhost:40420` 进入管理面板，点击「账号管理」添加讯飞开放平台的 SSO 账号。

或通过 API：

```bash
curl -X POST http://localhost:40419/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"sso_token": "你的讯飞SSO Token"}'
```

## 使用方式

### Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:40419 \
ANTHROPIC_AUTH_TOKEN="你的API Key" \
claude --dangerously-skip-permissions
```

### Codex

```bash
OPENAI_API_KEY="你的API Key" \
OPENAI_BASE_URL=http://localhost:40419/v1 \
codex
```

### OpenAI SDK (Python)

```python
from openai import OpenAI

client = OpenAI(
    api_key="你的API Key",
    base_url="http://localhost:40419/v1"
)

resp = client.chat.completions.create(
    model="iflycode-default",
    messages=[{"role": "user", "content": "用Python写一个快排"}],
    stream=True
)
for chunk in resp:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### curl

```bash
curl http://localhost:40419/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的API Key" \
  -d '{
    "model": "iflycode-default",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

## 模型说明

| Model ID | 说明 |
|----------|------|
| `iflycode-default` | 自动选择 (Chat) |
| `iflycode-default-coding` | 自动选择 (Coding) — 支持工具调用 |
| `4.0Ultra` | 星火 4.0 Ultra |
| `pro-128k` | 星火 Pro 128K |
| `generalv3` | 星火 Pro |
| `lite` | 星火 Lite (免费) |

> **注意**：上游 iFlyCode 是编程助手平台，模型会拒绝非 IT 相关问题（闲聊、翻译、角色扮演等）。适合 AI 编程场景使用。

## 管理面板截图

### 数据概览
![数据概览](docs/imgs/数据概览.png)

### 账号管理
![账号管理](docs/imgs/账号管理.png)

### 账号详情
![账号详情](docs/imgs/账号管理%20-%20账号详情.png)

### 聊天测试
![聊天测试](docs/imgs/聊天测试.png)

### 请求日志
![请求日志](docs/imgs/请求日志.png)

### 系统设置
![系统设置](docs/imgs/系统设置.png)

## API 端点

### OpenAI 兼容

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | Chat Completions (流式/非流式) |
| `/v1/models` | GET | 可用模型列表 |

### Anthropic 兼容

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/messages` | POST | Messages API (流式/非流式) |

### 管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/accounts` | GET | 账号列表 |
| `/api/accounts` | POST | 添加账号 |
| `/api/accounts/{id}` | DELETE | 删除账号 |
| `/api/accounts/{id}/renew-key` | POST | 轮换 API Key |
| `/api/accounts/{id}/models` | GET | 账号可用模型 |
| `/api/accounts/{id}/stats` | GET | 请求统计 |
| `/api/accounts/{id}/hourly-stats` | GET | 小时级统计 |
| `/api/accounts/{id}/recent-logs` | GET | 最近请求日志 |
| `/api/stats` | GET | 全局统计 |

## CLI 命令

```bash
iflycode-proxy serve [-H HOST] [-p PORT] [--service]  # 启动服务
iflycode-proxy stop-service                            # 停止守护进程
iflycode-proxy service-status                          # 查看守护进程状态
iflycode-proxy version                                 # 查看版本
```

## 技术栈

- **后端**：Python 3.12+, FastAPI, uvicorn, httpx
- **前端**：React 19, TypeScript, Vite 8, Ant Design 6, Recharts
- **数据库**：SQLite (via stdlib)

## 项目结构

```
iflycode_proxy/
├── server.py              # FastAPI 应用入口
├── openai_handler.py      # OpenAI 协议转换
├── anthropic_handler.py   # Anthropic 协议转换
├── client.py              # 上游 iFlyCode 客户端
├── credential_router.py   # 账号池 & 负载均衡
├── auth.py                # API Key 认证
├── crypto.py              # 加密工具
├── db.py                  # SQLite 数据层
├── web_api.py             # 管理 API
├── proxy_logger.py        # 请求日志
├── janitor.py             # 日志清理
├── daemon.py              # 守护进程
├── cli.py                 # CLI 入口
└── static/                # 前端构建产物

web/                       # 前端源码
├── src/
│   ├── pages/             # 页面组件
│   ├── layouts/           # 布局
│   ├── api.ts             # API 客户端
│   └── data/              # 静态数据
└── package.json
```

## License

MIT
