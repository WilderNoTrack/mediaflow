"""集中配置：全部来自环境变量 / server/.env，代码里不再散落 os.getenv。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVER_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout: float = 120.0
    llm_max_retries: int = 3

    # 配图
    image_api_key: str = ""
    image_endpoint: str = "https://grsai.dakka.com.cn/v1/api/generate"
    image_model: str = "gpt-image-2.5"
    image_size: str = "3:4"           # 只对不认识的模型生效；内置模型按各自参数出 3:4 竖图
    image_timeout: float = 300.0
    image_concurrency: int = 3

    # 选题来源
    weibo_cookie: str = ""
    zhihu_access_secret: str = ""
    qianfan_api_key: str = ""
    douyin_cookie: str = ""
    bilibili_cookie: str = ""
    xhs_cookie: str = ""
    source_timeout: float = 12.0

    # 运行
    mediaflow_data_dir: Path = SERVER_DIR / "data"
    mediaflow_host: str = "127.0.0.1"
    mediaflow_port: int = 8765
    mediaflow_open_browser: bool = True
    worker_concurrency: int = 2
    scheduler_interval_seconds: int = 60

    # 在线版（部署到服务器给几个人用）
    mediaflow_auth: str = "none"        # none=本地单人版，不用登录；password=账号密码登录
    mediaflow_secret: str = ""          # 登录 Cookie 的签名密钥，password 模式必填（随机长字符串）
    mediaflow_admin_user: str = "admin"  # 首次启动时自动建的管理员
    mediaflow_admin_password: str = ""
    mediaflow_daily_writes: int = 20    # 每个普通成员每天最多写几篇（0=不限），管理员不限
    mediaflow_daily_chats: int = 200    # 每个普通成员每天最多和小媒说几句（0=不限）

    @property
    def data_dir(self) -> Path:
        p = Path(self.mediaflow_data_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def images_dir(self) -> Path:
        p = self.data_dir / "images"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'mediaflow.db'}"

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def image_configured(self) -> bool:
        return bool(self.image_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
