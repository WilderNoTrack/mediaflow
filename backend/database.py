from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./mediaflow.db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _sqlite_add_column_if_missing(conn, table: str, column: str, col_type: str):
    """SQLite 不支持 IF NOT EXISTS for ALTER TABLE，用此函数安全添加列。"""
    try:
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            logger.info(f"[migrate] Added column {table}.{column}")
    except Exception as e:
        logger.warning(f"[migrate] Could not add {table}.{column}: {e}")


def migrate_db():
    """对 SQLite 数据库做增量迁移（全部用原生 sqlite3，避免 SQLAlchemy 包装的坑）。"""
    if "sqlite" not in DATABASE_URL:
        return  # PostgreSQL 等由 Alembic 管理

    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not db_path or ":memory:" in db_path:
        # 内存库无法用原生 sqlite3 按路径重连（会连到另一个空库），
        # 且 create_all 已经建好最新结构，无需增量迁移
        return
    import sqlite3 as _sq3

    def add_col(cur, table, col, col_type):
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        if col not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            logger.info(f"[migrate] Added {table}.{col}")

    with _sq3.connect(db_path) as raw:
        cur = raw.cursor()

        # xiaohongshu_accounts 新增孵化 + 自动运营字段
        for col, typ in [
            ("theme",            "VARCHAR(100)"),
            ("target_audience",  "VARCHAR(200)"),
            ("content_style",    "TEXT"),
            ("image_style",      "TEXT"),
            ("topic_type",       "TEXT"),
            ("keywords",         "TEXT"),
            ("requirements",     "TEXT"),
            ("auto_enabled",     "BOOLEAN DEFAULT 0"),
            ("auto_frequency",   "VARCHAR(20) DEFAULT 'daily'"),
            ("auto_count",       "VARCHAR(5) DEFAULT '1'"),
            ("last_auto_run",    "DATETIME"),
        ]:
            add_col(cur, "xiaohongshu_accounts", col, typ)

        # contents 新增账号关联字段 + 图片提示词 + 直接用户归属 + 质检/配图状态
        for col, typ in [
            ("account_id",    "VARCHAR(36)"),
            ("topic_id",      "VARCHAR(36)"),
            ("image_prompts", "JSON"),
            ("user_id",       "VARCHAR(36)"),
            ("image_status",  "VARCHAR(20) DEFAULT 'none'"),
            ("quality_score", "VARCHAR(5)"),
            ("needs_review",  "BOOLEAN DEFAULT 0"),
        ]:
            add_col(cur, "contents", col, typ)

        # 回填 user_id：先从旧的 lobster 归属，再从小红书账号归属
        existing_tables = {
            row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        content_cols = {row[1] for row in cur.execute("PRAGMA table_info(contents)")}

        if "lobster_id" in content_cols and "lobsters" in existing_tables:
            cur.execute("""
                UPDATE contents SET user_id = (
                    SELECT user_id FROM lobsters WHERE lobsters.id = contents.lobster_id
                )
                WHERE user_id IS NULL AND lobster_id IS NOT NULL
            """)
            logger.info(f"[migrate] 从 lobsters 回填 contents.user_id: {cur.rowcount} 行")

        if "xiaohongshu_accounts" in existing_tables:
            cur.execute("""
                UPDATE contents SET user_id = (
                    SELECT user_id FROM xiaohongshu_accounts
                    WHERE xiaohongshu_accounts.id = contents.account_id
                )
                WHERE user_id IS NULL AND account_id IS NOT NULL
            """)
            logger.info(f"[migrate] 从 xiaohongshu_accounts 回填 contents.user_id: {cur.rowcount} 行")

        # 移除历史遗留的 contents.lobster_id（旧版 Lobster 体系已废弃）。
        # SQLite 老版本不支持 DROP COLUMN，统一走重建表；按当前实际列取交集拷贝，
        # 避免把后加的列（如 image_prompts）在重建时丢掉。
        if "lobster_id" in content_cols:
            logger.info("[migrate] contents 移除 lobster_id")
            keep = [
                ("id",                  "VARCHAR(36) PRIMARY KEY"),
                ("user_id",             "VARCHAR(36)"),
                ("account_id",          "VARCHAR(36)"),
                ("topic_id",            "VARCHAR(36)"),
                ("title",               "VARCHAR(255)"),
                ("content",             "TEXT"),
                ("images",              "JSON"),
                ("image_prompts",       "JSON"),
                ("tags",                "JSON"),
                ("status",              "VARCHAR(9)"),
                ("scheduled_at",        "DATETIME"),
                ("published_at",        "DATETIME"),
                ("xiaohongshu_note_id", "VARCHAR(100)"),
                ("created_at",          "DATETIME"),
                ("updated_at",          "DATETIME"),
            ]
            ddl      = ", ".join(f"{c} {t}" for c, t in keep)
            # 目标表里有、但旧表里没有的列，拷贝时补 NULL
            copy_src = ", ".join(c if c in content_cols else "NULL" for c, _ in keep)
            copy_dst = ", ".join(c for c, _ in keep)

            cur.execute(f"CREATE TABLE contents_new ({ddl})")
            cur.execute(f"INSERT INTO contents_new ({copy_dst}) SELECT {copy_src} FROM contents")
            cur.execute("DROP TABLE contents")
            cur.execute("ALTER TABLE contents_new RENAME TO contents")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_contents_user_id ON contents (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_contents_account_id ON contents (account_id)")
            logger.info("[migrate] contents 重建完成")

        # 废弃的旧版表（Lobster 体系）保留数据不删，仅不再由 ORM 映射：
        #   lobsters / user_preferences / conversation_history

        raw.commit()


def init_db():
    from models import Base
    Base.metadata.create_all(bind=engine)
    migrate_db()
