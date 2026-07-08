# iFlyCode 2API

> **🏁 项目已归档 — 上游服务已彻底下线**
>
> 2026-07-08 确认：`iflycode.xfyun.cn` 域名已停止解析（NXDOMAIN），所有 API 端点返回 502，SSO 登录页面已不可访问。该项目已无法继续使用，代码库作为协议翻译代理的参考实现保留。
>
> 详见下方 [项目终止说明](#-上游服务已停服)。

---

## ⚠️ 上游服务已停服

### TL;DR

**iFlyCode 云端服务已彻底下线，本项目已无法使用。** 代码库作为参考实现和逆向分析成果存档。

### 时间线

| 时间 | 状态 |
|------|------|
| 2026-05 之前 | 项目正常运行，iFlyCode 服务可用 |
| 2026-06-10 | 首次排查：iFlyCode 后端 API 返回 502，CDN/TLS 正常 |
| 2026-07-08 | **最终确认：`iflycode.xfyun.cn` 域名已停止解析（NXDOMAIN），SSO 登录页完全不可访问** |

### 2026-07-08 最终排查结果

| 测试项 | 结果 | 含义 |
|--------|------|------|
| `iflycode.xfyun.cn` DNS 解析 | **NXDOMAIN** | 域名已不存在 |
| `iflycode-xfsaas.xfyun.cn` API 端点 | **502 Bad Gateway** | 后端无响应 |
| `chooseIdentity` 登录页面 | **连接失败** | 域名无解析 |
| `www.xfyun.cn`（讯飞主站） | **200 OK** | 仅 iFlyCode 服务下线 |

### 结论

```
2026-06: 域名可解析 → CDN可达 → 后端502（服务停服但仍保留域名）
2026-07: 域名停止解析（NXDOMAIN）→ 连域名都未续费
```

**iFlyCode 产品已从讯飞平台下线，无恢复可能。**

---

## 项目历史

本项目是一个协议翻译代理，将 OpenAI/Anthropic API 格式的请求翻译为讯飞星火飞码（iFlyCode）的上游 API，让 Claude Code、Codex 等 AI 编程工具能够使用星火飞码的 AI 能力。

### 实现的功能

- 兼容 OpenAI 和 Anthropic 两种 API 格式，流式非流式都行
- 多账号池，自动轮换
- Chat 和 Coding 两种模式，Coding 模式支持工具调用
- 自带管理面板（React + Ant Design），看统计、查日志、管账号
- 免费额度限制配置（每日请求上限、每月 Token 上限）
- HTTP API 批量导入账号
- 守护进程模式，崩了自动重启
- 300 次交互压测 0 错误通过

### 相关项目

- [iflycode-RE](https://github.com/vibe-coding-labs/iflycode-RE) — 星火飞码插件的逆向分析，本项目基于它实现

## License

MIT