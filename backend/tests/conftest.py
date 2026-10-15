import os
import atexit
import shutil
import tempfile

# 必须在导入任何项目模块之前设置：database.py 的 engine 在 import 期就按
# DATABASE_URL 建好了。不设的话 TestClient(app) 触发的 startup 会对开发者的
# 真实 mediaflow.db 执行 init_db()（跑一次测试就迁移一次真库），并启动调度器。
#
# 用临时文件而非 :memory:——migrate_db() 是按路径用原生 sqlite3 重连的，
# 内存库会连到另一个空库。临时文件能真正跑一遍 create_all + 迁移。
_TMP_DIR = tempfile.mkdtemp(prefix="mediaflow-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'test.db')}"
os.environ["AUTO_AGENT_ENABLED"] = "false"
atexit.register(lambda: shutil.rmtree(_TMP_DIR, ignore_errors=True))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import get_db
from main import app
from dependencies import hash_password
from models import Base, User, XiaohongshuAccount

SQLALCHEMY_TEST_DATABASE_URL = 'sqlite:///:memory:'


@pytest.fixture(scope='function')
def test_engine():
    """每个测试一个全新的内存库。

    刻意用 function 作用域：被测代码（如 handle_save_draft、run_all_due_accounts）
    内部会自己 commit()/rollback()，共享库或外层事务包裹都挡不住互相污染。
    每测试重建最省心，且不会留下 test.db 文件。
    """
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,      # 内存库必须：所有连接共用同一个库
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope='function')
def db_session(test_engine):
    session = sessionmaker(bind=test_engine)()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(scope='function')
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture(scope='function')
def test_user(db_session):
    user = User(
        id='test-user-id',
        email='test@example.com',
        password_hash=hash_password('testpass123'),
        nickname='Test User'
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture(scope='function')
def test_account(db_session, test_user):
    account = XiaohongshuAccount(
        id='test-account-id',
        user_id=test_user.id,
        username='test_account',
        theme='测试主题',
        target_audience='测试受众',
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture(scope='function')
def auth_headers(test_user):
    from dependencies import create_token
    token = create_token(str(test_user.id))
    return {'Authorization': f'Bearer {token}'}
