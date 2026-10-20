"""在线版：登录、数据隔离、管理员权限、每日用量、配图只给本人看。"""

import pytest
from fastapi.testclient import TestClient

from mediaflow.config import get_settings


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setenv("MEDIAFLOW_AUTH", "password")
    monkeypatch.setenv("MEDIAFLOW_SECRET", "test-secret-0123456789")
    monkeypatch.setenv("MEDIAFLOW_ADMIN_USER", "boss")
    monkeypatch.setenv("MEDIAFLOW_ADMIN_PASSWORD", "boss-pass-123")
    monkeypatch.setenv("MEDIAFLOW_DAILY_WRITES", "2")
    get_settings.cache_clear()
    from mediaflow.app import create_app

    app = create_app(background=False)
    with TestClient(app) as admin, TestClient(app) as mom, TestClient(app) as other:
        yield admin, mom, other
    get_settings.cache_clear()


def login(c, u, p):
    return c.post("/api/auth/login", json={"username": u, "password": p})


def test_online_flow(online):
    admin, mom, other = online
    assert admin.get("/api/accounts").status_code == 401
    assert admin.get("/api/auth/me").status_code == 401
    assert login(admin, "boss", "wrong").status_code == 401
    r = login(admin, "Boss", "boss-pass-123")
    assert r.status_code == 200 and r.json()["is_admin"] and "httponly" in r.headers["set-cookie"].lower()

    # 管理员开账号；普通成员不能开、不能改全站设置
    assert admin.post("/api/admin/users", json={"username": "mom", "password": "short"}).status_code == 400
    assert admin.post("/api/admin/users", json={"username": "mom", "password": "mom-pass-1", "name": "小美"}).status_code == 201
    assert admin.post("/api/admin/users", json={"username": "MOM", "password": "mom-pass-1"}).status_code == 400
    admin.post("/api/admin/users", json={"username": "other", "password": "other-pass-1"})
    assert login(mom, "mom", "mom-pass-1").json()["limits"]["writes"] == 2
    login(other, "other", "other-pass-1")
    assert mom.get("/api/admin/users").status_code == 403
    assert mom.put("/api/settings/llm", json={"api_key": "sk-x"}).status_code == 403
    assert mom.post("/api/settings/xiaohongshu/qrcode").status_code == 403
    assert mom.get("/api/settings/credentials").status_code == 200  # 只看配没配，可以

    # 数据隔离
    a = mom.post("/api/accounts", json={"name": "宝妈省钱", "theme": "带娃省钱"}).json()
    assert [x["id"] for x in mom.get("/api/accounts").json()] == [a["id"]]
    assert other.get("/api/accounts").json() == []
    assert other.get(f"/api/accounts/{a['id']}").status_code == 404
    assert other.post(f"/api/accounts/{a['id']}/write", json={}).status_code == 404

    # 每天写稿上限（管理员不限）
    from mediaflow.db import session_scope
    from mediaflow.domain.models import Job, JobStatus
    from sqlmodel import select

    for _ in range(2):
        assert mom.post(f"/api/accounts/{a['id']}/write", json={}).status_code == 202
        with session_scope() as s:  # 模拟写完，避免同账号并发冲突
            for j in s.exec(select(Job)).all():
                j.status = JobStatus.succeeded
                s.add(j)
            s.commit()
    r = mom.post(f"/api/accounts/{a['id']}/write", json={})
    assert r.status_code == 400 and "用完了" in r.json()["detail"]
    users = {u["username"]: u for u in admin.get("/api/admin/users").json()}
    assert users["mom"]["usage"]["writes"] == 2 and users["mom"]["accounts"] == 1

    # 停用后旧登录立即失效；重置密码后用新密码能登
    uid = users["mom"]["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"disabled": True}).json()["disabled"]
    assert mom.get("/api/accounts").status_code == 401
    assert "停用" in login(mom, "mom", "mom-pass-1").json()["detail"]
    admin.patch(f"/api/admin/users/{uid}", json={"disabled": False, "password": "new-pass-99"})
    assert login(mom, "mom", "new-pass-99").status_code == 200
    assert admin.patch(f"/api/admin/users/{users['boss']['id']}", json={"disabled": True}).status_code == 400

    # 自己改密码
    assert mom.post("/api/auth/password", json={"old_password": "x", "new_password": "abcdefgh"}).status_code == 400
    assert mom.post("/api/auth/password", json={"old_password": "new-pass-99", "new_password": "abcdefgh1"}).status_code == 204
    assert mom.get("/api/accounts").status_code == 200  # 改完自己仍是登录状态

    # 退出
    mom.post("/api/auth/logout")
    assert mom.get("/api/accounts").status_code == 401


def test_images_only_for_owner(online, tmp_path):
    admin, mom, other = online
    login(admin, "boss", "boss-pass-123")
    admin.post("/api/admin/users", json={"username": "mom", "password": "mom-pass-1"})
    admin.post("/api/admin/users", json={"username": "other", "password": "other-pass-1"})
    login(mom, "mom", "mom-pass-1")
    login(other, "other", "other-pass-1")
    a = mom.post("/api/accounts", json={"name": "a", "theme": "t"}).json()

    from mediaflow.db import session_scope
    from mediaflow.domain.models import Draft

    with session_scope() as s:
        uid = mom.get("/api/auth/me").json()["id"]
        d = Draft(user_id=uid, account_id=a["id"], title="t", body="b")
        s.add(d)
        s.commit()
        did = d.id
    p = get_settings().images_dir / did
    p.mkdir(parents=True, exist_ok=True)
    (p / "0.png").write_bytes(b"png")
    assert mom.get(f"/files/images/{did}/0.png").content == b"png"
    assert other.get(f"/files/images/{did}/0.png").status_code == 404
    for bad in ("/files/images/%2e%2e/mediaflow.db", "/files/images/..%2fmediaflow.db"):
        assert b"SQLite" not in mom.get(bad).content
    other.post("/api/auth/logout")
    assert other.get(f"/files/images/{did}/0.png").status_code == 401


def test_online_needs_secret(monkeypatch):
    monkeypatch.setenv("MEDIAFLOW_AUTH", "password")
    monkeypatch.setenv("MEDIAFLOW_SECRET", "")
    monkeypatch.setenv("MEDIAFLOW_ADMIN_PASSWORD", "boss-pass-123")
    get_settings.cache_clear()
    from mediaflow.app import create_app

    with pytest.raises(RuntimeError, match="MEDIAFLOW_SECRET"):
        with TestClient(create_app(background=False)):
            pass
    get_settings.cache_clear()


def test_spa_does_not_serve_files_outside_dist(client):
    for bad in ("/%2e%2e/%2e%2e/server/pyproject.toml", "/..%2f..%2fserver%2fpyproject.toml"):
        assert b"[project]" not in client.get(bad).content
