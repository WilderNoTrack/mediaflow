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
    image_model: str = "gpt-image-2"
    image_size: str = "1024x1536"
    image_timeout: float = 180.0

    # 选题来源
    weibo_cookie: str = ""
    source_timeout: float = 12.0

    # 运行
    mediaflow_data_dir: Path = SERVER_DIR / "data"
    mediaflow_host: str = "127.0.0.1"
    mediaflow_port: int = 8765
    mediaflow_open_browser: bool = True
    worker_concurrency: int = 2
    scheduler_interval_seconds: int = 60

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
