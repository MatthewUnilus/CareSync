from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from TRIAGEASSIST_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TRIAGEASSIST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./triageassist.db"
    session_ttl_seconds: int = 8 * 60 * 60
    session_cookie_name: str = "triageassist_session"
    session_cookie_secure: bool = False
    seed_demo_users: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
