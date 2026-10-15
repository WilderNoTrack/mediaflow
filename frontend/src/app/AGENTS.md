# Frontend AGENTS.md

React 18 SPA。父文档：`../../../AGENTS.md`

## Stack

- React 18 + Vite 6.3.5 + TypeScript
- **React Router v7**（`react-router` 7.13，注意不是 `react-router-dom`）
- Tailwind CSS v4（`@tailwindcss/vite` 插件）
- shadcn/ui on Radix UI
- vitest + @testing-library（`src/test/setup.ts`）

## Structure

```
src/
├── main.tsx                 # 入口
├── i18n.ts                  # 中英文案表（中文原文作 key）
├── styles/
├── test/                    # vitest setup + 示例测试
├── app/
│   ├── App.tsx              # 应用外壳
│   ├── routes.tsx           # createBrowserRouter 配置
│   ├── components/
│   │   ├── AuthGuard.tsx    # AuthGuard（需登录）/ GuestGuard（已登录则跳走）
│   │   ├── figma/           # Figma 导出组件
│   │   └── ui/              # shadcn/ui primitives
│   └── pages/               # 8 个页面
└── components/              # 跨页面业务组件
    ├── AccountSelector.tsx      # 账号下拉选择
    ├── AccountManagerCard.tsx   # 账号信息卡片
    ├── AddAccountDialog.tsx     # 扫码添加账号
    ├── PublishDialog.tsx        # 发布对话框
    └── ui/
```

> `components/ui` 有两处（`app/components/ui` 和 `src/components/ui`），是历史遗留。
> 新增 shadcn 组件前先确认目标页面 import 的是哪一处。

## Routes（`routes.tsx`）

| 路径 | 组件 | Guard | 说明 |
|------|------|-------|------|
| `/` | LandingPage | — | 落地页 |
| `/auth` | AuthPage | GuestGuard | 登录 / 注册 |
| `/forgot-password` | ForgotPasswordPage | GuestGuard | 找回密码 |
| `/accounts` | AccountsPage | AuthGuard | **账号孵化中台（主入口）** |
| `/accounts/:accountId` | AccountWorkspacePage | AuthGuard | **账号工作台** |
| `/create` | CreatePage | AuthGuard | 内容编辑器 |
| `/preview` | PreviewPage | AuthGuard | 小红书效果预览 |
| `/settings` | SettingsPage | AuthGuard | 账号设置 |

**主流程**：`/accounts` → `/accounts/:id` → 内容卡片点预览 `/preview` → 点编辑 `/create`

`/dashboard*`、`/chat`、`/contents`、`/onboarding`、`/preferences`、`/report`
全部 `<Navigate replace>` 重定向到 `/accounts`，**仅为兼容旧书签，不要往这些路径加功能**。

## 页面职责

| 页面 | 行数 | 说明 |
|------|------|------|
| `account-workspace.tsx` | ~2.2k | **主力页面**：管家对话(SSE)、选题搜索、内容列表、自动运营开关 |
| `settings.tsx` | ~860 | 资料/密码/通知/导出/注销 |
| `create.tsx` | ~815 | 编辑正文与标签、AI 改写、单张/批量重新配图、存草稿 |
| `accounts.tsx` | ~320 | 账号列表与新建 |
| `preview.tsx` | ~360 | 小红书样式预览，可跳回 `/create` 编辑 |

## 关键交互模式

**SSE 消费**：`/api/agent/chat/{id}`、`/api/agent/run/{id}`、`search-topics-stream`
都是 SSE。事件类型见后端 `services/agent/core.py`：
`start` / `tool_call` / `tool_result` / `evaluation` / `warning` / `error` / `done`，
管家转发子 Agent 的事件时包一层 `{"type":"agent_progress","event":{...}}`。
`warning` 事件承载降级信息（热点搜索降级、评估失败兜底、图片生成失败），**必须展示给用户**。

**后台生图轮询**：Agent 存草稿后图片是 `placehold.co` 占位图，真实图片由后端后台线程异步写入。
`create.tsx` 每 15 秒轮询 `GET /api/contents/{id}`，直到 `images` 里出现非 placehold 的 URL。

**图片 URL 处理**：后端返回的相对路径要拼 `API_BASE`——
`const resolveImg = (url) => url?.startsWith("/") ? `${API_BASE}${url}` : url`

**页面间传参**：用 `navigate(path, { state })` 传内容对象，目标页 `useLocation().state` 取。
`create.tsx` 兼容 `imagePrompts` / `image_prompts` / `image_prompts_cn` 三种字段名。

## Conventions

- 页面文件 kebab-case，导出 PascalCase 具名组件：`export function AccountWorkspacePage()`
- `@/` 别名 → `src/`
- 文案走 `i18n.ts`，**以中文原文作 key**：`t("保存失败")`
- token 存 `localStorage.getItem("token")`，请求带 `Authorization: Bearer ${token}`

## Extension Patterns

**加页面**

1. 建 `pages/new-page.tsx`，`export function NewPage()`
2. `routes.tsx` 里 import 并注册；需登录就包 `<AuthGuard>`

**加 shadcn 组件**

```bash
cd frontend && npx shadcn@latest add <component>
```

## Vite Config 限制（`frontend/vite.config.ts`）

- 第 7-12 行：React + Tailwind 插件**均为必需**，不要删
- 第 21 行 `assetsInclude`：**永远不要**加入 `.css` / `.tsx` / `.ts`

## Anti-Patterns

| 问题 | 位置 |
|------|------|
| 重复 `className` 属性（后者覆盖前者，构建告警） | `components/ui/dialog.tsx` |
| `account-workspace.tsx` 已 ~2.2k 行 | 继续加功能前考虑拆组件 |
| 构建产物 `frontend/dist/` 被 git 跟踪 | 易产生无意义 diff |
| 单 chunk >500KB | 构建告警，可考虑 `manualChunks` 拆包 |
