from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from CARESYNC_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="CARESYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./caresync.db"

    # Session lifetime. This is the outer bound on a token, not the working
    # day: a ward tablet is shared, so a token that escapes the inactivity
    # lock (a restored tab, a copied cookie) should die within half a shift
    # rather than last the full eight hours a personal device could afford.
    # The inactivity lock is the primary control and is measured in minutes;
    # this TTL is the backstop behind it.
    session_ttl_seconds: int = 4 * 60 * 60

    # The inactivity lock: a period shorter than the session's own lifetime,
    # so a tablet left unattended locks well before the token would expire.
    # Five minutes covers a patient interaction and the walk to the next bay;
    # the next person to pick up a shared tablet is the threat being answered.
    session_idle_seconds: int = 5 * 60

    # How often an authenticated request refreshes the session's last-seen
    # instant. Without this throttle every poll of the ward board would write a
    # row, and the idle window would never be more than this far out of date.
    session_heartbeat_seconds: int = 60

    # Unlock rate limiting. A locked tablet must not be an unattended guessing
    # surface, so a run of wrong passwords blocks further attempts on the
    # session row. Counters on the row, checked in the application layer: ADR
    # 0001 forbids database triggers.
    session_unlock_max_attempts: int = 5
    session_unlock_lockout_seconds: int = 60

    session_cookie_name: str = "caresync_session"

    # Secure cookies are sent only over HTTPS, so enabling this against a plain
    # HTTP deployment silently breaks sign-in. It is what the deployment turns
    # on, not what local development runs with. See the README's "Security
    # behaviour".
    session_cookie_secure: bool = False
    seed_demo_users: bool = False

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
