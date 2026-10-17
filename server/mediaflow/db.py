"""数据库：engine、session、启动时自动迁移。"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from mediaflow.config import get_settings
from mediaflow.domain.models import LOCAL_USER_ID, User

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_engine: Engine | None = None


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - 连接级设置
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url, connect_args={"check_same_thread": False}
        )
    return _engine


def set_engine(engine: Engine) -> None:
    """测试用：替换为内存库。"""
    global _engine
    _engine = engine


def run_migrations(url: str | None = None) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    command.upgrade(cfg, "head")


def ensure_local_user(session: Session) -> None:
    if session.get(User, LOCAL_USER_ID) is None:
        session.add(User(id=LOCAL_USER_ID))
        session.commit()


def init_db() -> None:
    run_migrations()
    with Session(get_engine()) as s:
        ensure_local_user(s)


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s


def get_session() -> Iterator[Session]:
    """FastAPI 依赖。"""
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s
