from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from mediaflow.db import get_session
from mediaflow.domain.models import LOCAL_USER_ID, Account, Draft, User
from mediaflow.services import auth


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    """本地版：固定是默认用户。在线版：从登录 Cookie 里认人，没登录 401。"""
    if not auth.enabled():
        return session.get(User, LOCAL_USER_ID) or User(id=LOCAL_USER_ID, is_admin=True)
    u = auth.user_from_token(session, request.cookies.get(auth.COOKIE))
    if u is None:
        raise HTTPException(401, "请先登录")
    return u


def current_user_id(u: User = Depends(current_user)) -> str:
    return u.id


def require_admin(u: User = Depends(current_user)) -> User:
    """改模型 Key、连平台账号这些全站共用的设置，只有管理员能动（本地版自己就是管理员）。"""
    if auth.enabled() and not u.is_admin:
        raise HTTPException(403, "这个设置只有管理员能改")
    return u


def owned_account(account_id: str, session: Session = Depends(get_session),
                  uid: str = Depends(current_user_id)) -> Account:
    acc = session.get(Account, account_id)
    if acc is None or acc.user_id != uid:
        raise HTTPException(404, "账号不存在")
    return acc


def owned_draft(draft_id: str, session: Session = Depends(get_session),
                uid: str = Depends(current_user_id)) -> Draft:
    d = session.get(Draft, draft_id)
    if d is None or d.user_id != uid:
        raise HTTPException(404, "草稿不存在")
    return d
