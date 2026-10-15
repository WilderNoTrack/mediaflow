import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="mediaflow-test-")
os.environ["MEDIAFLOW_DATA_DIR"] = _tmp
os.environ["DEEPSEEK_API_KEY"] = "test"
os.environ.pop("IMAGE_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from mediaflow import db as dbmod  # noqa: E402
from mediaflow.config import get_settings  # noqa: E402
from mediaflow.domain.models import LOCAL_USER_ID, Account  # noqa: E402
from mediaflow.llm import client as llm_client  # noqa: E402
from mediaflow.services import images as images_mod  # noqa: E402
from mediaflow.services import topics as topics_mod  # noqa: E402
from tests.fakes import FakeLLM, fake_fetch  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    dbmod.run_migrations(url)  # 用真实迁移建表，顺便测迁移
    engine = create_engine(url, connect_args={"check_same_thread": False})
    dbmod.set_engine(engine)
    with Session(engine) as s:
        dbmod.ensure_local_user(s)
    monkeypatch.setattr(dbmod, "init_db", lambda: None)
    monkeypatch.setattr("mediaflow.app.init_db", lambda: None)
    # 默认不联网：选题来源换成假的
    monkeypatch.setattr(topics_mod, "fetch_all", lambda kw, n: fake_fetch(kw, n))
    yield engine
    llm_client.set_llm(None)
    images_mod.set_provider_factory(None)
    get_settings.cache_clear()
    engine.dispose()
    _ = SQLModel


@pytest.fixture
def llm():
    f = FakeLLM()
    llm_client.set_llm(f)
    return f


@pytest.fixture
def session(fresh_db):
    with Session(fresh_db, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def account(session):
    a = Account(user_id=LOCAL_USER_ID, name="小鹿穿搭", theme="学生党平价穿搭", audience="大学女生",
                content_style="闺蜜聊天感", image_style="手机随手拍的生活感", keywords=["通勤穿搭"])
    session.add(a)
    session.commit()
    return a


@pytest.fixture
def client():
    from mediaflow.app import create_app

    with TestClient(create_app(background=False)) as c:
        yield c
