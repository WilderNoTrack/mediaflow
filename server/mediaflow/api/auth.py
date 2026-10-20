"""登录 / 退出 / 我是谁，以及管理员的成员管理。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from mediaflow.api.deps import current_user, require_admin
from mediaflow.config import get_settings
from mediaflow.db import get_session
from mediaflow.domain.models import Account, Draft, User
from mediaflow.services import auth

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class MeOut(BaseModel):
    id: str
    username: str
    name: str
    is_admin: bool
    auth: str = Field(description="none=本地版不用登录；password=在线版")
    usage: dict = Field(default={}, description="今天用了多少：writes / chats")
    limits: dict = Field(default={}, description="每天上限：writes / chats，0 表示不限")


def _me(s: Session, u: User) -> MeOut:
    cfg = get_settings()
    on = auth.enabled()
    limited = on and not u.is_admin
    return MeOut(id=u.id, username=u.username or "", name=u.name, is_admin=u.is_admin or not on,
                 auth="password" if on else "none", usage=auth.usage_today(s, u.id) if on else {},
                 limits={"writes": cfg.mediaflow_daily_writes, "chats": cfg.mediaflow_daily_chats} if limited else {})


@router.post("/api/auth/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, s: Session = Depends(get_session)):
    if not auth.enabled():
        raise HTTPException(400, "本地版不需要登录")
    try:
        u = auth.login(s, body.username, body.password)
    except PermissionError as e:
        raise HTTPException(401, str(e)) from e
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, auth.make_token(u), max_age=auth.MAX_AGE, httponly=True, samesite="lax", secure=secure)
    return _me(s, u)


@router.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(auth.COOKIE)


@router.get("/api/auth/me", response_model=MeOut)
def me(u: User = Depends(current_user), s: Session = Depends(get_session)):
    return _me(s, u)


class PasswordIn(BaseModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/api/auth/password", status_code=204)
def change_password(body: PasswordIn, response: Response, request: Request, u: User = Depends(current_user),
                    s: Session = Depends(get_session)):
    if not auth.enabled():
        raise HTTPException(400, "本地版没有密码")
    if not auth.verify_password(body.old_password, u.password_hash):
        raise HTTPException(400, "原密码不对")
    auth.set_password(s, u, body.new_password)
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(auth.COOKIE, auth.make_token(u), max_age=auth.MAX_AGE, httponly=True, samesite="lax", secure=secure)


# ── 成员管理（管理员） ────────────────────────────────────────────────────


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    is_admin: bool
    disabled: bool
    created_at: datetime
    last_login_at: datetime | None
    accounts: int = 0
    drafts: int = 0
    usage: dict = {}


class UserIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)
    name: str = Field("", max_length=40)
    is_admin: bool = False


class UserPatch(BaseModel):
    password: str | None = Field(None, max_length=200)
    name: str | None = Field(None, max_length=40)
    disabled: bool | None = None
    is_admin: bool | None = None


def _count(s: Session, model, uid: str) -> int:
    return int(s.exec(select(func.count()).select_from(model).where(model.user_id == uid)).one())


def _user_out(s: Session, u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username or "", name=u.name, is_admin=u.is_admin, disabled=u.disabled,
                   created_at=u.created_at, last_login_at=u.last_login_at, accounts=_count(s, Account, u.id),
                   drafts=_count(s, Draft, u.id), usage=auth.usage_today(s, u.id))


admin = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@admin.get("/users", response_model=list[UserOut])
def list_users(s: Session = Depends(get_session)):
    rows = s.exec(select(User).where(col(User.username).is_not(None)).order_by(col(User.created_at))).all()
    return [_user_out(s, u) for u in rows]


@admin.post("/users", response_model=UserOut, status_code=201)
def add_user(body: UserIn, s: Session = Depends(get_session)):
    """给人开账号（不开放注册）。把用户名和密码发给 TA，TA 登录后可以自己改密码。"""
    return _user_out(s, auth.create_user(s, body.username, body.password, name=body.name, is_admin=body.is_admin))


@admin.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserPatch, me: User = Depends(require_admin), s: Session = Depends(get_session)):
    """重置密码、改名字、停用 / 恢复、设为管理员。停用和改密码会让 TA 的旧登录立即失效。"""
    u = s.get(User, user_id)
    if u is None or u.username is None:
        raise HTTPException(404, "成员不存在")
    if u.id == me.id and (body.disabled or body.is_admin is False):
        raise HTTPException(400, "不能停用自己或取消自己的管理员")
    if body.password:
        auth.set_password(s, u, body.password)
    if body.name is not None and body.name.strip():
        u.name = body.name.strip()
    if body.disabled is not None and body.disabled != u.disabled:
        u.disabled, u.token_version = body.disabled, u.token_version + 1
    if body.is_admin is not None:
        u.is_admin = body.is_admin
    s.add(u)
    s.commit()
    s.refresh(u)
    return _user_out(s, u)
