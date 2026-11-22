"""The system names itself CareSync at the API seam (ticket 28).

The rename is mechanical but wide: the app title, the settings prefix and the
default cookie name all have to land together, or a running server reads the
wrong settings against a client that expects the old cookie. These tests pin
the three seams a caller can observe over HTTP.
"""

from fastapi.testclient import TestClient

from app.config import Settings


def test_openapi_metadata_says_caresync(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "CareSync API"


def test_settings_read_the_caresync_prefix(monkeypatch) -> None:
    monkeypatch.setenv("CARESYNC_SESSION_COOKIE_NAME", "custom_session")

    assert Settings().session_cookie_name == "custom_session"


def test_the_old_prefix_is_not_read(monkeypatch) -> None:
    monkeypatch.setenv("TRIAGEASSIST_SESSION_COOKIE_NAME", "custom_session")

    assert Settings().session_cookie_name == "caresync_session"


def test_defaults_name_the_caresync_database_and_cookie() -> None:
    settings = Settings()

    assert settings.database_url == "sqlite:///./caresync.db"
    assert settings.session_cookie_name == "caresync_session"
