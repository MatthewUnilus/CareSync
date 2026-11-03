from functools import lru_cache
from pathlib import Path

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

    # Runtime fallback provider (layer 3 of the engine). No URL means no
    # provider: an unmatched complaint degrades to the safety layer's default
    # and is marked unclassified, rather than blocking the patient. Nothing in
    # the build or the test suite requires a key, a network or a paid service.
    fallback_provider_url: str | None = None
    fallback_provider_api_key: str | None = None
    fallback_timeout_seconds: float = 2.0

    # The Accuracy Evaluation Report reads the labelled run manifest the
    # offline harness writes. A missing file is the explicit "no labelled run"
    # state, not an error and not a zero score.
    accuracy_run_path: str = str(
        Path(__file__).resolve().parent.parent
        / "evaluation"
        / "results"
        / "accuracy-evaluation.json"
    )

    # Comma-separated. The native shell has its own WebView origin, so it calls
    # the API cross-origin; these are the only origins granted credentials.
    cors_origins: str = (
        "http://localhost,"
        "http://127.0.0.1,"
        "https://localhost,"
        "capacitor://localhost,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
