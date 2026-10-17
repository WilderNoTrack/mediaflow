from fastapi import Depends, HTTPException
from sqlmodel import Session

from mediaflow.db import get_session
from mediaflow.domain.models import LOCAL_USER_ID, Account, Draft


def current_user_id() -> str:
    """本地版只有一个用户。以后接登录，只改这里。"""
    return LOCAL_USER_ID


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
