import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"
ADMINISTRATOR_PASSWORD = "administrator-password"


def test_clinical_user_starts_session_with_valid_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["email"] == CLINICAL_EMAIL
    assert response.json()["role"] == "clinical"

    set_cookie = response.headers["set-cookie"]
    assert "triageassist_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == CLINICAL_EMAIL
    assert me.json()["role"] == "clinical"


def test_clinical_user_is_refused_with_invalid_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    assert client.get("/api/auth/me").status_code == 401


def test_unknown_email_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": CLINICAL_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_password_is_never_stored_in_plain_text(client: TestClient, db_path: Path) -> None:
    client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )

    with sqlite3.connect(db_path) as connection:
        stored_hashes = [row[0] for row in connection.execute("SELECT password_hash FROM users")]

    assert stored_hashes
    for stored_hash in stored_hashes:
        assert stored_hash.startswith("$argon2")

    database_bytes = db_path.read_bytes()
    assert CLINICAL_PASSWORD.encode() not in database_bytes
    assert ADMINISTRATOR_PASSWORD.encode() not in database_bytes


def test_session_cookie_lifetime_follows_the_configured_expiry(db_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=120,
        seed_demo_users=True,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
        )

    assert response.status_code == 200
    assert "Max-Age=120" in response.headers["set-cookie"]
