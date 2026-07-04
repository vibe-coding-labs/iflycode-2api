import { defineConfig } from 'vitepress'

export default defineConfig({
  base: '/iflycode-2api/',
  title: '把讯飞星火飞码变成 OpenAI API — 兼容 Claude Code、Codex，多账号池，自带管理面板',
  description: '把讯飞星火飞码变成 OpenAI API — 兼容 Claude Code、Codex，多账号池，自带管理面板',
  lang: 'zh-CN',
  lastUpdated: true,
  ignoreDeadLinks: true,
  markdown: {
    lineNumbers: true,
  },
  themeConfig: {
    search: {
      provider: 'local',
    },
    nav: [
      { text: '文档首页', link: '/' },
      { text: 'GitHub', link: 'https://github.com/vibe-coding-labs/iflycode-2api' },
    ],
    sidebar: [
          { text: "把讯飞星火飞码变成 OpenAI API — 兼容 Claude Code...", items: [
            { text: "首页", link: "/" },
            { text: "iFlyCode Proxy Enhancement Plan", link: "/superpowers/plans/2026-04-29-proxy-enhancement" },
            { text: "Chat Playground Implementation Plan", link: "/superpowers/plans/2026-04-30-chat-playground" },
            { text: "账号详情页统计增强 — 请求统计 + Token 消耗 + 请求日志", link: "/superpowers/plans/2026-05-02-account-stats-enhancement" },
            { text: "账号管理UI增强 — 品牌图标 + 可点击行 + 详情统计 + Token追踪", link: "/superpowers/plans/2026-05-02-account-ui-enhancement" },
            { text: "iflycode-proxy 全栈集成测试套件 (50-100 Cases)", link: "/superpowers/plans/2026-05-02-comprehensive-test-suite" },
            { text: "可用模型列表展示 — 模型元数据 + 详情页展示", link: "/superpowers/plans/2026-05-02-model-catalog" },
            { text: "iFlyCode Proxy Service Mode (进程守护 + 自动重启)", link: "/superpowers/plans/2026-05-02-service-daemon-mode" },
            { text: "Protocol Translation Fix + Model Capability UI Plan", link: "/superpowers/plans/2026-05-03-protocol-translation-fix-and-model-capabilities" },
          ] }
        ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/vibe-coding-labs/iflycode-2api' },
    ],
    footer: {
      message: '基于 VitePress 构建',
    },
  },
})
