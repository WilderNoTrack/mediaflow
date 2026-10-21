"""FastAPI 应用：挂接口、托管前端构建产物、启动后台 worker 和自动模式调度。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mediaflow import __version__
from mediaflow.api import accounts, auth as auth_api, drafts, misc, settings, topics
from mediaflow.api.deps import current_user
from mediaflow.config import get_settings
from mediaflow.db import init_db, session_scope
from mediaflow.jobs.queue import JobConflict, recover_interrupted, worker_loop
from mediaflow.jobs.scheduler import scheduler_loop
from mediaflow.llm.client import LLMError, LLMNotConfigured

logger = logging.getLogger("mediaflow")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from mediaflow.services import auth

    with session_scope() as s:
        auth.bootstrap_admin(s)
    if auth.enabled():
        auth._secret()  # 没配签名密钥直接启动失败，别等到登录时才发现
    n = recover_interrupted()
    if n:
        logger.warning("上次有 %d 个任务没跑完，已标记为失败", n)
    tasks = []
    if app.state.background:
        s = get_settings()
        tasks = [asyncio.create_task(worker_loop(s.worker_concurrency)),
                 asyncio.create_task(scheduler_loop(s.scheduler_interval_seconds))]
    yield
    for t in tasks:
        t.cancel()


def create_app(*, background: bool = True) -> FastAPI:
    app = FastAPI(title="MediaFlow", version=__version__, lifespan=lifespan)
    app.state.background = background

    # 仅开发时 Vite (5173) 跨域访问需要；生产由后端直接托管前端，同源
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    app.include_router(auth_api.router)
    app.include_router(auth_api.admin)
    login = [Depends(current_user)]  # 在线版：除了登录接口，全部要先登录
    for r in (accounts.router, topics.router, drafts.router, misc.router, settings.router):
        app.include_router(r, dependencies=login)

    @app.exception_handler(LookupError)
    async def _404(_: Request, e: LookupError):
        return JSONResponse({"detail": str(e).strip("'\"")}, status_code=404)

    @app.exception_handler(ValueError)
    async def _400(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(JobConflict)
    async def _409(_: Request, e: JobConflict):
        return JSONResponse({"detail": str(e), "job_id": e.job.id}, status_code=409)

    @app.exception_handler(LLMNotConfigured)
    async def _503(_: Request, e: LLMNotConfigured):
        return JSONResponse({"detail": str(e)}, status_code=503)

    @app.exception_handler(LLMError)
    async def _502(_: Request, e: LLMError):
        return JSONResponse({"detail": str(e)}, status_code=502)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/files/images/{path:path}", include_in_schema=False)
    def image_file(path: str, u=Depends(current_user)):
        """配图只给本人看：第一级目录是草稿 ID，对得上才返回。_refs（对标原图缓存）登录即可看，_test 只给管理员。"""
        from mediaflow.domain.models import Draft
        from mediaflow.services import auth

        root = get_settings().images_dir.resolve()
        f = (root / path).resolve()
        if root not in f.parents or not f.is_file():
            raise HTTPException(404)
        top = f.relative_to(root).parts[0]
        if auth.enabled() and top != "_refs":
            if top == "_test":
                ok = u.is_admin
            else:
                with session_scope() as s:
                    d = s.get(Draft, top)
                    ok = d is not None and d.user_id == u.id
            if not ok:
                raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "private, max-age=86400"})

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            root = WEB_DIST.resolve()
            f = (root / path).resolve()
            if path and root in f.parents and f.is_file():  # 防止 ../ 读到前端目录以外的文件
                return FileResponse(f)
            return FileResponse(WEB_DIST / "index.html")

    return app
