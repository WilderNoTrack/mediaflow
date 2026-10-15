# Backend Routers

父文档：`../../AGENTS.md`

## Routers（9 个，全部汇入 `api_router`）

| Router | 文件 | Prefix | 用途 |
|--------|------|--------|------|
| auth | `auth.py` | `/api/auth` | 注册 / 登录 / 发送邮箱验证码 / 重置密码 |
| users | `users.py` | `/api/user` | 资料读写、头像、改密、通知设置、注销账号、导出数据 |
| contents | `contents.py` | `/api/contents` | 草稿 CRUD、AI 改写、单张/批量配图、图片上传 |
| publish | `publish.py` | `/api/publish` | 发布到小红书、发布任务与状态查询 |
| config | `config.py` | `/api/config` | 用户键值配置读写 |
| upload | `upload.py` | `/api/upload` | 通用图片上传 |
| xiaohongshu_accounts | `xiaohongshu_accounts.py` | `/api/xiaohongshu/accounts` | 多账号绑定、二维码登录、登录状态、设默认 |
| agent | `agent.py` | `/api/agent` | 账号管家对话 / 内容创作，**均为 SSE 流式** |
| accounts_workspace | `accounts_workspace.py` | `/api/workspace` | **账号工作台主力接口**（22 端点） |

> `payment.py` 在 `backend/` 根目录，前缀 `/api/payment`，由 `main.py` 单独 `include_router`，
> **不在** `api_router` 里。

### `/api/workspace` 端点分组（`accounts_workspace.py`）

| 分组 | 端点 |
|------|------|
| 账号 | `POST/GET /accounts`、`GET/PUT /accounts/{id}/profile` |
| 管家对话 | `POST /accounts/{id}/chat`(SSE)、`GET /accounts/{id}/chat-history`、`POST /accounts/{id}/extract-config` |
| 选题 | `POST /accounts/{id}/suggest-keywords`、`POST /accounts/{id}/search-topics`、`POST /accounts/{id}/search-topics-stream`(SSE)、`GET /accounts/{id}/topics`、`PUT /accounts/{id}/topics/{topic_id}/status` |
| 内容 | `POST /accounts/{id}/generate`、`GET /accounts/{id}/contents` |
| 自动运营 | `GET/PUT /accounts/{id}/auto`、`POST /accounts/{id}/auto/run` |
| 外链抓取 | `GET /bilibili-video-detail`、`POST /xhs-note-detail`、`GET /weixin-article-detail`、`GET /weibo-detail`、`GET /baidu-link-detail` |

外链抓取端点用于把用户贴的参考链接正文喂给选题分析，**不做鉴权之外的用户隔离**（无副作用的只读抓取）。

## Router Pattern

prefix 写在 router 自身，`include_router` 时不再叠加：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from dependencies import get_current_user

router = APIRouter(prefix="/api/<name>", tags=["<name>"])


@router.post("/endpoint")
def endpoint(
    req: RequestModel,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {...}          # 直接返回 dict，本项目没有 Pydantic 响应模型层
```

## Aggregation（`__init__.py`）

```python
from fastapi import APIRouter
from .auth import router as auth_router
# ... 其余 8 个

api_router = APIRouter()
api_router.include_router(auth_router)
# ... 其余 8 个

__all__ = ["api_router"]
```

## 扩展步骤

1. 建 `backend/routers/new.py`，按上面的 Router Pattern 写
2. `__init__.py` 里 `from .new import router as new_router`
3. `api_router.include_router(new_router)`

`main.py` 已经 `include_router(api_router)`，无需再改。

## 本目录约定

- **鉴权**：需要登录的端点一律 `user: User = Depends(get_current_user)`
- **所有权校验**：拿到资源必须验归属，别只按 id 查
  - 账号：`accounts_workspace.py::_check_account_owner(account_id, user, db)`
  - 内容：`contents.py::_get_owned_content(content_id, user, db)`
    —— 要同时检查 `Content.user_id` 和 `Content.account_id → account.user_id` **两条归属路径**
- **局部 import**：函数体内 `from models import ...` 是本项目常见写法，用于打断循环依赖
- **SSE**：同步 Agent 跑在 `ThreadPoolExecutor`，用 `loop.call_soon_threadsafe` 把
  `on_event` 回调转进 asyncio 队列，再 `StreamingResponse` 推出去；照抄 `agent.py` 的写法
- **优雅降级**：依赖 xiaohongshu-mcp / 微博 / 抖音的端点，在外部服务不可用时返回部分数据
  或降级标记，不要抛 500

## Anti-Patterns

| 问题 | 位置 |
|------|------|
| 重复的 `# type: ignore`（同行写了两次） | `auth.py:66` |
| 散落的 `# type: ignore`（SQLAlchemy 动态属性绕过） | `auth.py:105,126,129,217,218,220` |
| `accounts_workspace.py` 已 ~1.3k 行 | 继续加端点前考虑按领域拆分 |
