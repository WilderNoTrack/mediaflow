"""FastAPI 应用：挂接口、托管前端构建产物、启动后台 worker 和自动模式调度。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mediaflow import __version__
from mediaflow.api import accounts, drafts, misc, topics
from mediaflow.config import get_settings
from mediaflow.db import init_db
from mediaflow.jobs.queue import JobConflict, recover_interrupted, worker_loop
from mediaflow.jobs.scheduler import scheduler_loop
from mediaflow.llm.client import LLMError, LLMNotConfigured

logger = logging.getLogger("mediaflow")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

    for r in (accounts.router, topics.router, drafts.router, misc.router):
        app.include_router(r)

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

    app.mount("/files/images", StaticFiles(directory=get_settings().images_dir, check_dir=False), name="images")

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = WEB_DIST / path
            if path and f.is_file():
                return FileResponse(f)
            return FileResponse(WEB_DIST / "index.html")

    return app
