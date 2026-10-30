"""Central configuration. Every value can be overridden with a TICK_* env var or a .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = "https://dev-task.elancoapps.com/data"
    db_path: str = "data/ticks.db"
    snapshot_path: str = "data/snapshot.json"  # last good copy of the upstream payload
    http_timeout_s: float = 20.0
    max_retries: int = 5
    backoff_base_s: float = 0.5
    backoff_max_s: float = 8.0
    auto_sync_on_startup: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="TICK_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
