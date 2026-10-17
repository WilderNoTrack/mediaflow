# AGENTS.md

给参与本项目的 AI 编码助手和开发者的说明。

## 项目概览

- `server/`：Python 3.11+ / FastAPI / SQLModel（SQLite）/ Alembic，包名 `mediaflow`，用 `uv` 管理依赖。
- `web/`：React 18 + Vite + TypeScript + Tailwind v4 + TanStack Query，接口类型由 OpenAPI 生成（`src/api/schema.d.ts`）。
- 生产形态：后端直接托管 `web/dist`，本地单进程运行，端口 8765。

## 后端结构

| 路径 | 职责 |
| --- | --- |
| `mediaflow/domain/models.py` | 数据表（全部带 `user_id`，为多用户预留） |
| `mediaflow/domain/schemas.py` | 接口请求/响应结构 |
| `mediaflow/llm/client.py` | DeepSeek 封装（OpenAI 兼容）、`complete_json` 带修复重试；测试用 `set_llm` 注入假模型 |
| `mediaflow/agents/context.py` | 由代码组装账号上下文（定位、规矩、近期稿件），**不让模型传 account_id** |
| `mediaflow/agents/checks.py` | 硬性检查（标题长度、正文长度、标签、敏感词、查重） |
| `mediaflow/agents/pipeline.py` | 写稿流水线：写 → 检查 + 评审 → 改写（≤3 轮）→ 保存 |
| `mediaflow/agents/manager.py` | 运营管家：工具绑定到当前账号，工具调用结果写入对话记忆，每账号一把锁 |
| `mediaflow/agents/learning.py` | 从用户修改和反馈中提炼规矩（需用户确认） |
| `mediaflow/sources/` | 热榜来源，单个来源失败不影响其它 |
| `mediaflow/jobs/` | 基于数据库的任务队列（写稿、配图）与自动模式调度 |
| `mediaflow/api/` | 路由 |

## 约定

- 账号归属由代码保证：所有接口通过 `owned_account` / `owned_draft` 依赖校验；模型工具里不出现账号 ID。
- 耗时操作（写稿、配图）走任务队列，接口立即返回 Job，前端轮询 `/api/jobs`。
- 改表结构必须加 Alembic 迁移：`cd server && uv run alembic revision --autogenerate -m "..."`，启动时自动迁移。
- 不做自动发布；导出是唯一出口。
- 文案、提示词、界面文字使用中文。

## 必跑检查

```bash
cd server && uv run pytest            # 测试全部离线，使用 tests/fakes.py 的假模型和假来源
cd web && npx tsc --noEmit && npm run build
```

改了后端接口：启动后端后在 `web/` 执行 `npm run gen:api`，并提交更新后的 `schema.d.ts`。
