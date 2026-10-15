# MediaFlow AGENTS.md

## OVERVIEW

- **Project**: MediaFlow（媒力）— AI 驱动的小红书账号运营平台
- **Type**: Monorepo（FastAPI 后端 + React 18/Vite 前端 + 独立的 xiaohongshu-mcp 子服务）
- **核心心智模型**: 一切围绕**小红书账号**（`XiaohongshuAccount`）组织。账号既是发布目标，
  也是内容定位配置的载体（主题/受众/文案风格/配图风格/选题类型/关键词/长期要求）。
  用户在「账号工作台」和账号管家 Agent 对话来完善这份配置，再由内容创作 Agent 按配置产出图文。

> 旧版的「龙虾（Lobster）AI 员工 + UserPreference 全局偏好」体系**已删除**。
> 如果在旧文档、旧分支或数据库里看到 `Lobster` / `UserPreference` / `ConversationHistory` /
> `Content.lobster_id`，那是历史遗留，不要基于它写新代码。详见文末「已移除的旧体系」。

## WHERE TO LOOK

| 目的 | 位置 |
|------|------|
| 后端入口 / 路由挂载 | `backend/main.py`（端口 8000） |
| 路由聚合 | `backend/routers/__init__.py` → `api_router` |
| 数据模型（单文件） | `backend/models.py` |
| 数据库初始化 + 增量迁移 | `backend/database.py` |
| JWT / 认证 / 服务注入 | `backend/dependencies.py` |
| 自动运营调度器 | `backend/scheduler.py` |
| **主力业务逻辑** | `backend/routers/accounts_workspace.py`（~1.3k 行，账号工作台全部接口） |
| **Agent 核心** | `backend/services/agent/`（core / manager / tools） |
| 前端入口 | `frontend/src/main.tsx` → `src/app/App.tsx` → `src/app/routes.tsx` |
| **主力前端页面** | `frontend/src/app/pages/account-workspace.tsx`（~2.2k 行） |

## CODE MAP

```
backend/
├── main.py                  # FastAPI 入口，CORS，挂载 /uploads，startup 启动调度器
├── models.py                # 全部 SQLAlchemy 模型（单文件，无 models/ 目录）
├── database.py              # engine / SessionLocal / get_db / migrate_db / init_db
├── dependencies.py          # SECRET_KEY、hash_password、create_token、get_current_user、服务注入
├── scheduler.py             # APScheduler 后台调度，定时触发自动运营
├── payment.py               # 支付宝集成（在 main.py 中单独挂载，不在 api_router 里）
├── routers/                 # 9 个 router，全部汇入 api_router
├── services/                # 业务服务
│   ├── agent/               # ReAct Agent（见下方「AGENT 架构」）
│   │   ├── core.py          # AgentRunner：内容创作 ReAct 主循环
│   │   ├── manager.py       # ManagerAgent：对话式账号管家
│   │   └── tools.py         # 工具定义 + 实现 + 注册表
│   ├── ai_service.py        # DeepSeek 文本生成（生成/改写/评估/提示词扩写）
│   ├── auto_agent.py        # 自动运营：判断到点 + 调用 AgentRunner 产出
│   ├── image_service.py     # AI 配图（gpt-image-2）
│   ├── topic_search.py      # 多平台选题搜索 + AI 分析
│   ├── douyin_search_playwright.py  # 抖音搜索（Playwright）
│   ├── email_service.py     # SMTP 验证码邮件
│   ├── xiaohongshu_mcp.py       # 单账号 MCP 客户端
│   └── multi_account_client.py  # 多账号管理客户端
├── tests/                   # pytest（conftest.py 提供 client/db_session/test_user/test_account）
└── uploads/                 # 上传与 AI 生成的图片，由 main.py 挂载为静态目录

frontend/src/
├── main.tsx                 # React 入口
├── i18n.ts                  # 中英文案表（以中文原文为 key）
├── app/
│   ├── App.tsx              # 应用外壳
│   ├── routes.tsx           # createBrowserRouter 配置
│   ├── components/          # AuthGuard/GuestGuard + figma/ + ui/
│   └── pages/               # 8 个页面组件
└── components/              # 跨页面业务组件（账号选择/发布对话框等）+ ui/
```

## 数据模型（`backend/models.py`）

```
User ─┬─ Subscription                 订阅（trial/basic/pro/enterprise）
      ├─ XiaohongshuAccount ─┬─ Topic                选题库（每账号独立）
      │   （账号 = 配置载体）  ├─ AccountConversation  与账号管家的对话历史
      │                       ├─ Content              内容草稿
      │                       └─ PublishLog           发布结果日志
      ├─ XiaohongshuAccountBinding    user_id ↔ MCP 侧 account_id 的映射
      ├─ Content (user_id)            不挂账号的独立草稿也直接归属用户
      ├─ ContentConfig                键值配置
      └─ PublishTask                  发布任务与状态追踪

EmailVerificationCode                 注册/找回密码验证码（独立表）
```

**`XiaohongshuAccount` 是配置中心**，除了账号身份字段外还承载：

- 定位：`theme` / `target_audience` / `content_style` / `image_style` / `topic_type`
- 选题：`keywords`(JSON) / `requirements`(JSON，长期文案要求，每次生成都会遵守)
- 自动运营：`auto_enabled` / `auto_frequency` / `auto_count` / `last_auto_run`

**`Content` 有两条归属路径**，`_get_owned_content()`（`routers/contents.py`）两条都要检查：

1. `Content.user_id` — 直接归属用户（`POST /api/contents` 建的独立草稿）
2. `Content.account_id` → `XiaohongshuAccount.user_id` — 通过账号归属（Agent 产出的内容）

## AGENT 架构

两个 ReAct Agent，都是**同步**实现，由 router 放进 `ThreadPoolExecutor` 跑，
通过 `on_event()` 同步回调 + `loop.call_soon_threadsafe` 转成 SSE 推给前端。

```
ManagerAgent (manager.py)          ← 面向「账号」：对话式管家
  工具: get_account_profile / update_account_profile / list_recent_contents
        set_auto_operation / search_trending / create_post
                          │
                          │ create_post 把内容创作 Agent 当子 Agent 调用，
                          │ 子 Agent 的事件包成 {"type":"agent_progress"} 转发到同一条 SSE
                          ▼
AgentRunner (core.py)              ← 面向「一篇内容」：创作流水线
  工具: get_account_history → search_trending → generate_content
        → evaluate_content（打分，<7 分带建议重试）→ save_draft
```

**正文不经 LLM 转手（重要）**：`generate_content` 把内容存进 `AgentRunner.store`，
只返回 `draft_ref` 引用和摘要；`evaluate_content` / `save_draft` 都按 `draft_ref` 取用。
早期实现让 LLM 把全文原样抄进后两个工具的参数，导致**入库的是模型转录版而非生成版**
（可能被截断改写），且同一篇正文在 context 里往返三次。新增工具时务必沿用引用传递。

主循环的硬约束（都在代码里，不靠 prompt 自觉）：

| 约束 | 常量 | 说明 |
|------|------|------|
| 步数上限 | `MAX_STEPS=16` | 防死循环 |
| 生成次数 | `MAX_GENERATIONS=3` | 超限后工具直接拒绝并要求 save_draft |
| 墙钟预算 | `AGENT_RUN_BUDGET`（默认 900s） | 超时中止并尽量兜底保存 |
| 工具结果入 context | `MAX_TOOL_RESULT_CHAR=6000` | 截断后再进 messages |
| 同账号并发 | 进程内 `_account_lock` | 手动与定时可能撞车；多进程部署需换 DB 锁 |

流程异常收尾（LLM 提前结束 / 步数耗尽 / 超预算）时走 `_save_best()`，
它会**真的调用 save_draft 落库**并返回合法结果。

`save_draft` 存草稿后经**有界线程池** `_IMAGE_POOL` 做真实配图（先 `build_image_prompt`
扩写中文说明为英文提示词，再逐张 `ImageService.generate`），结果写回
`Content.image_status`（none/pending/done/partial/failed），失败的槽位写「生成失败」
占位图而不是静默留空。前端 `create.tsx` 每 15 秒轮询 `GET /api/contents/{id}`。

LLM 调用统一走 `services/agent/llm.py`：429/5xx/超时指数退避重试，4xx 快速失败，
并累计 token 用量。每次运行在 `AgentRun` 表留痕（步骤/评分/token/耗时/错误）。

**三条入口共用 `AgentRunner`，不要再造第四条流水线**：

| 入口 | 路径 |
|------|------|
| 工作台「立即创作」 | `POST /api/agent/run/{account_id}` |
| 管家对话中触发 | `ManagerAgent` 的 `create_post` 工具 |
| 定时自动运营 | `scheduler.py` → `auto_agent.run_all_due_accounts` → `run_account_once` |

历史教训：自动运营曾经自己实现了一套「搜选题→生成→存草稿」，结果**跳过质量评估、
配图永远停在占位图**（从不触发后台生图）、选题不去重。新增入口时务必复用 `AgentRunner`。

## API 路由

统一挂载在 `api_router`（`routers/__init__.py`），`payment` 在 `main.py` 单独挂载。

| Router | 文件 | Prefix | 用途 |
|--------|------|--------|------|
| auth | `auth.py` | `/api/auth` | 注册 / 登录 / 邮箱验证码 / 重置密码 |
| users | `users.py` | `/api/user` | 资料、头像、改密、通知设置、注销、数据导出 |
| contents | `contents.py` | `/api/contents` | 草稿 CRUD、AI 改写、单张/批量配图、图片上传 |
| publish | `publish.py` | `/api/publish` | 发布到小红书 + 任务状态 |
| config | `config.py` | `/api/config` | 用户键值配置 |
| upload | `upload.py` | `/api/upload` | 通用图片上传 |
| xiaohongshu_accounts | `xiaohongshu_accounts.py` | `/api/xiaohongshu/accounts` | 多账号绑定、二维码登录、状态 |
| agent | `agent.py` | `/api/agent` | 账号管家对话 / 内容创作，均为 SSE |
| accounts_workspace | `accounts_workspace.py` | `/api/workspace` | **账号工作台主力接口**（22 个端点） |
| payment | `../payment.py` | `/api/payment` | 支付宝 |

`/api/workspace` 覆盖：账号增删查、定位配置读写、管家对话与历史、关键词建议、
选题搜索（含 SSE 流式）、选题库管理、内容生成、自动运营开关与手动触发、账号内容列表，
以及若干**外链正文抓取**端点（B站/小红书/微信/微博/百度），用于把参考链接喂给选题分析。

完整接口文档见 `docs/API-REFERENCE.md`。

## 前端路由（`frontend/src/app/routes.tsx`）

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | LandingPage | 落地页 |
| `/auth` | AuthPage | 登录/注册（GuestGuard） |
| `/forgot-password` | ForgotPasswordPage | 找回密码（GuestGuard） |
| `/accounts` | AccountsPage | **账号孵化中台**（主入口） |
| `/accounts/:accountId` | AccountWorkspacePage | **账号工作台**（对话/选题/内容/自动运营） |
| `/create` | CreatePage | 内容编辑器（改文案、配图、存草稿） |
| `/preview` | PreviewPage | 小红书效果预览 |
| `/settings` | SettingsPage | 账号设置 |

主流程：`/accounts` → 进入某账号 `/accounts/:id` → 内容卡片点预览 `/preview` → 点编辑 `/create`。
其余旧路径（`/dashboard*` `/chat` `/contents` `/onboarding` `/preferences` `/report`）
全部 `<Navigate>` 重定向到 `/accounts`，仅为兼容旧书签，**不要往这些路径加新功能**。

## CONVENTIONS

**后端**

- 模型全放 `models.py` 单文件；没有 `models/` 包，也没有 Pydantic schemas 层——
  请求体用 router 内就近定义的 `BaseModel`，响应直接返回 dict
- router 内的**局部 import** 是本项目的常见写法（`def` 内 `from models import ...`），
  用于打断循环依赖，跟随现有风格即可
- 数据库迁移写在 `database.py::migrate_db()`，用原生 `sqlite3` 手写增量 DDL，**不用 Alembic**；
  非 SQLite 直接 return
- 外部服务（MCP / 微博 / 抖音）不可用时**优雅降级**，返回部分数据或降级标记，不要 500

**Agent 相关**

- 工具返回的降级情况必须显式带 `fallback` / `fallback_note` / `fallback_reason` 字段，
  并在 SSE 里推 `warning` 事件——`MANAGER_SYSTEM_PROMPT` 明确要求 Agent 如实告知用户，
  **不允许隐瞒失败装作正常**
- 新增工具：在 `tools.py` 定义 `ToolDef` + `handle_xxx`，注册进 `ALL_TOOL_DEFS` / `TOOL_HANDLERS`。
  handler 会收到 `db` / `ai_service` / `store` / `counter` / `strict` 这几个上下文 kwarg，
  签名末尾请保留 `**_`
- **大段内容一律走 `store` 引用传递，不要让 LLM 复述**（见上文 AGENT 架构）
- 外部抓取内容（热榜、用户贴的链接正文）必须包进 `UNTRUSTED_OPEN/CLOSE` 标记并附
  `untrusted_data_notice`，防止 prompt injection
- `strict=True`（自动运营无人值守）时，质检服务失败**不得**按默认分放行；
  交互场景可放行但要标 `fallback` 并让 Agent 如实说明
- 不要在工具或 Agent 里临时修改传入的 ORM 对象：链路上有 `db.commit()`，
  临时值会被一并持久化（`create_post` 的 `topic_hint` 曾因此污染账号选题词）

**前端**

- 页面文件 kebab-case，导出 PascalCase 具名组件（`export function AccountWorkspacePage()`）
- `@/` 别名指向 `src/`
- 文案走 `i18n.ts`，**以中文原文作为 key**（`t("保存失败")`）
- shadcn/ui 组件：`npx shadcn@latest add <component>`

## EXTENSION PATTERNS

**加一个 router**

1. 建 `backend/routers/new.py`，`router = APIRouter(prefix="/api/new", tags=["new"])`
2. `routers/__init__.py` 里 import 并 `api_router.include_router(new_router)`
   （prefix 写在 router 自己身上，`include_router` 不再加 prefix）

**加一个模型字段**

1. 在 `models.py` 加 `Column`
2. 在 `database.py::migrate_db()` 的对应 `add_col(...)` 列表里加一行，保证老库能平滑升级
3. 若需重建表（SQLite 改约束/删列），**按实际列取交集拷贝**，
   不要硬编码列清单——历史上硬编码导致过 `image_prompts` 数据丢失

**加一个页面**

1. 建 `frontend/src/app/pages/new-page.tsx`
2. 在 `routes.tsx` 注册，需要登录就包 `<AuthGuard>`

## ANTI-PATTERNS / 注意点

| 问题 | 位置 | 说明 |
|------|------|------|
| 密码哈希无盐 | `backend/dependencies.py:33` | 裸 `sha256`，无 salt 无 KDF。生产应换 bcrypt/argon2 |
| SECRET_KEY 有默认值 | `backend/dependencies.py:21` | 未设环境变量时回落到硬编码串，生产必须设 `SECRET_KEY` |
| CORS 全开 + 带凭证 | `backend/main.py:21-27` | `allow_origins=["*"]` 配 `allow_credentials=True`，仅适合开发 |
| `on_event` 已废弃 | `backend/main.py:36,45` | FastAPI 新版建议改用 lifespan |
| 重复的 type ignore | `backend/routers/auth.py:66` | 同行写了两次 `# type: ignore` |
| Vite 插件不可删 | `frontend/vite.config.ts:7-12` | React + Tailwind 插件均为必需 |
| assetsInclude 限制 | `frontend/vite.config.ts:21` | 永远不要把 `.css` / `.tsx` / `.ts` 加进去 |
| 重复 className | `frontend/src/components/ui/dialog.tsx` | 构建期告警，后写的覆盖前面的 |
| `dist/` 被 git 跟踪 | `frontend/dist/` | 构建产物入库，易产生无意义 diff |

## 已移除的旧体系

「龙虾（Lobster）」体系已整体删除：`Lobster` / `UserPreference` / `ConversationHistory` 三个模型、
`routers/chat.py`、`routers/lobsters.py`、`backend/schemas.py`、
前端 `chat.tsx` / `contents.tsx` / `RequirementCard.tsx`，以及
`POST /api/agent/generate`、`POST /api/contents/generate`、`/api/user/preferences*` 等端点。

`Content.lobster_id` 已由 `migrate_db()` 移除并回填为 `Content.user_id`。
数据库里的 `lobsters` / `user_preferences` / `conversation_history` **三张表数据保留未删**，
仅不再由 ORM 映射；确认不再需要后可手动 drop。

## COMMANDS

```bash
# 后端（默认 :8000）
cd backend && pip install -r requirements.txt && python main.py

# 前端（默认 :5173）
cd frontend && npm install && npm run dev
npm run build

# 测试
cd backend && pytest          # 只跑 tests/；backend/test_xhs_*.py 是会联网的手动脚本
cd frontend && npm run test   # vitest

# 一键启停（Windows，封装 scripts/services.py）
start.bat / stop.bat
```

## 环境变量

必填：`DEEPSEEK_API_KEY`、`SMTP_USER` / `SMTP_PASSWORD`、生产环境的 `SECRET_KEY`。
可选：`DATABASE_URL`（默认 `sqlite:///./mediaflow.db`）、`XIAOHONGSHU_MCP_URL`(:18060)、
`MULTI_ACCOUNT_MANAGER_URL`(:8080)、`AUTO_AGENT_ENABLED`(默认 true)、
`AUTO_AGENT_CHECK_INTERVAL`(默认 30 分钟)、图片生成与微博/抖音 Cookie 等。
全部说明见 `backend/.env.example`。

## NOTES

- **CI/CD**: 无（没有 `.github/workflows`）
- **Docker**: `docker-compose.yml` 与两个 Dockerfile 已从仓库移除
- **子模块**: `xiaohongshu-mcp` 为 git submodule；发布与多账号功能依赖它在本地运行
