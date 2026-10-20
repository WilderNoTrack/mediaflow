"""在线版登录：用户名 + 密码，签名 Cookie。

- 本地版（MEDIAFLOW_AUTH=none）不需要登录，所有数据属于默认用户。
- 在线版（MEDIAFLOW_AUTH=password）：管理员在「成员管理」里给人开账号，不开放注册。
- 密码用 scrypt 加盐哈希；Cookie 里是 用户ID.过期时间.版本号.签名，改密码 / 停用后旧登录立即失效。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, func, select

from mediaflow.config import get_settings
from mediaflow.domain.models import LOCAL_USER_ID, ChatMessage, ChatRole, Job, JobKind, User, utcnow

COOKIE = "mf_session"
MAX_AGE = 30 * 24 * 3600
CN = timezone(timedelta(hours=8))


class QuotaExceeded(ValueError):
    pass


def enabled() -> bool:
    return get_settings().mediaflow_auth.strip().lower() == "password"


# ── 密码 ────────────────────────────────────────────────────────────────


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(got, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def check_password_rule(pw: str) -> None:
    if len(pw) < 8:
        raise ValueError("密码至少 8 位")


# ── 登录 Cookie ─────────────────────────────────────────────────────────


def _secret() -> bytes:
    s = get_settings().mediaflow_secret
    if not s:
        raise RuntimeError("在线版需要设置 MEDIAFLOW_SECRET（一串随机长字符串）")
    return s.encode()


def _sign(msg: str) -> str:
    return hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()[:40]


def make_token(u: User) -> str:
    msg = f"{u.id}.{int(time.time()) + MAX_AGE}.{u.token_version}"
    return f"{msg}.{_sign(msg)}"


def user_from_token(s: Session, token: str | None) -> User | None:
    if not token:
        return None
    try:
        uid, exp, ver, sig = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(f"{uid}.{exp}.{ver}")) or int(exp) < time.time():
        return None
    u = s.get(User, uid)
    if u is None or u.disabled or str(u.token_version) != ver:
        return None
    return u


# ── 登录防爆破：同一用户名连续错 5 次，锁 10 分钟（进程内，够几个人用） ─────

_fails: dict[str, list[float]] = {}
_lock = threading.Lock()
MAX_FAILS, LOCK_SECONDS = 5, 600


def login(s: Session, username: str, password: str) -> User:
    key = username.strip().lower()
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(key, []) if now - t < LOCK_SECONDS]
        _fails[key] = recent
        if len(recent) >= MAX_FAILS:
            raise PermissionError("密码错太多次了，10 分钟后再试")
    u = s.exec(select(User).where(func.lower(User.username) == key)).first()
    if u is None or u.disabled or not verify_password(password, u.password_hash):
        with _lock:
            _fails.setdefault(key, []).append(now)
        raise PermissionError("用户名或密码不对" if u is None or not u.disabled else "这个账号已停用，联系管理员")
    with _lock:
        _fails.pop(key, None)
    u.last_login_at = utcnow()
    s.add(u)
    s.commit()
    return u


# ── 管理员 ──────────────────────────────────────────────────────────────


def bootstrap_admin(s: Session) -> None:
    """在线版首次启动：还没有任何可登录的管理员，就按环境变量建一个。
    沿用本地版的默认用户，这样从本地版迁过来的数据直接归管理员。"""
    if not enabled():
        return
    if s.exec(select(User).where(User.is_admin == True, User.password_hash != "")).first():  # noqa: E712
        return
    cfg = get_settings()
    if not cfg.mediaflow_admin_password:
        raise RuntimeError("在线版首次启动需要设置 MEDIAFLOW_ADMIN_PASSWORD（管理员密码）")
    check_password_rule(cfg.mediaflow_admin_password)
    u = s.get(User, LOCAL_USER_ID) or User(id=LOCAL_USER_ID)
    u.username, u.name = cfg.mediaflow_admin_user.strip() or "admin", "管理员"
    u.password_hash, u.is_admin, u.disabled = hash_password(cfg.mediaflow_admin_password), True, False
    s.add(u)
    s.commit()


def create_user(s: Session, username: str, password: str, *, name: str = "", is_admin: bool = False) -> User:
    username = username.strip()
    if not username or len(username) > 40 or any(c.isspace() for c in username):
        raise ValueError("用户名不能为空、不能有空格，40 个字以内")
    check_password_rule(password)
    if s.exec(select(User).where(func.lower(User.username) == username.lower())).first():
        raise ValueError("这个用户名已经有人用了")
    u = User(username=username, name=name.strip() or username, password_hash=hash_password(password), is_admin=is_admin)
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def set_password(s: Session, u: User, password: str) -> None:
    check_password_rule(password)
    u.password_hash, u.token_version = hash_password(password), u.token_version + 1
    s.add(u)
    s.commit()


# ── 每日用量 ────────────────────────────────────────────────────────────


def _today_start() -> datetime:
    now = datetime.now(CN)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def usage_today(s: Session, user_id: str) -> dict:
    since = _today_start()
    writes = s.exec(select(func.count()).select_from(Job).where(
        Job.user_id == user_id, Job.kind == JobKind.write_draft, col(Job.created_at) >= since)).one()
    chats = s.exec(select(func.count()).select_from(ChatMessage).where(
        ChatMessage.user_id == user_id, ChatMessage.role == ChatRole.user, col(ChatMessage.created_at) >= since)).one()
    return {"writes": int(writes), "chats": int(chats)}


def check_quota(s: Session, user_id: str, what: str) -> None:
    """普通成员每天写稿 / 对话次数上限（在线版才限，管理员不限）。超了抛 QuotaExceeded（400）。"""
    if not enabled():
        return
    u = s.get(User, user_id)
    if u is None or u.is_admin:
        return
    cfg = get_settings()
    limit = cfg.mediaflow_daily_writes if what == "writes" else cfg.mediaflow_daily_chats
    if limit and usage_today(s, user_id)[what] >= limit:
        raise QuotaExceeded(f"今天{'写稿' if what == 'writes' else '和小媒聊天'}的次数用完了（每天 {limit} 次），明天再来，或者找管理员调高")
