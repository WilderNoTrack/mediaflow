"""`uv run mediaflow` 一条命令启动。"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

import uvicorn

from mediaflow.app import WEB_DIST
from mediaflow.config import get_settings


def _reset_password(argv: list[str]) -> None:
    """mediaflow reset-password 用户名：在服务器上重置某个成员（包括管理员）的密码。"""
    import getpass

    from mediaflow.db import init_db, session_scope
    from mediaflow.domain.models import User
    from mediaflow.services import auth
    from sqlmodel import func, select

    if not argv:
        raise SystemExit("用法：mediaflow reset-password 用户名")
    init_db()
    pw = getpass.getpass("新密码（至少 8 位）：")
    with session_scope() as s:
        u = s.exec(select(User).where(func.lower(User.username) == argv[0].lower())).first()
        if u is None:
            raise SystemExit(f"没有用户 {argv[0]}")
        auth.set_password(s, u, pw)
    print("已重置，旧的登录都已失效")


def main() -> None:
    import sys

    if sys.argv[1:2] == ["reset-password"]:
        return _reset_password(sys.argv[2:])
    s = get_settings()
    p = argparse.ArgumentParser(prog="mediaflow", description="MediaFlow（本地版 / 在线版）")
    p.add_argument("--port", type=int, default=s.mediaflow_port)
    p.add_argument("--host", default=s.mediaflow_host)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--reload", action="store_true", help="开发模式：改代码自动重启")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    url = f"http://{a.host}:{a.port}"
    print(f"\n  MediaFlow 已启动 → {url}")
    from mediaflow.llm.client import llm_configured

    if not llm_configured():
        print("  ⚠ 还没填 DeepSeek API Key：打开页面后在首页「开始之前」里填")
    if not WEB_DIST.exists():
        print("  ⚠ 没找到前端构建产物：先在 web/ 下运行 npm install && npm run build")
    print(f"  数据目录：{s.data_dir}\n")
    if s.mediaflow_open_browser and not a.no_browser and WEB_DIST.exists():
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("mediaflow.app:create_app", factory=True, host=a.host, port=a.port, reload=a.reload)


if __name__ == "__main__":
    main()
