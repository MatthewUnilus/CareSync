"""Shared-device session safety (ticket 38).

A session on a shared ward tablet locks when nobody has touched it, and a nurse
can lock and hand over deliberately. The lock is enforced on the server: a
locked session is refused by every authenticated route, not merely hidden by
the client. These tests drive the HTTP seam only, like ``test_logout`` and
``test_session_expiry``.
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"

# The status a locked session is refused with. Distinct from 401 so the client
# can tell "locked, unlock me" from "signed out, sign in again".
LOCKED_STATUS = 423


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )
    assert response.status_code == 200
    token = client.cookies.get("caresync_session")
    assert token
    return token


@pytest.fixture
def lockable_client(db_path: Path) -> Iterator[TestClient]:
    """A client whose idle window and unlock limits are short and explicit."""
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        session_idle_seconds=1,
        session_unlock_max_attempts=3,
        session_unlock_lockout_seconds=60,
        seed_demo_users=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_a_locked_session_is_refused_by_the_api(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )
    assert login.status_code == 200
    token = client.cookies.get("caresync_session")
    assert token
    assert client.get("/api/auth/me").status_code == 200

    lock = client.post("/api/auth/lock")
    assert lock.status_code == 204

    me = client.get("/api/auth/me")
    assert me.status_code == LOCKED_STATUS
    assert me.json() == {"detail": "Session locked"}

    # A clinical route is refused too, so the lock is not only on the auth
    # surface. This is the server-side enforcement the ticket turns on.
    assert client.get("/api/clinical/access").status_code == LOCKED_STATUS

    # Replaying the cookie by hand, as a reviewer with a tool would, changes
    # nothing: the refusal is the server's, not the client's.
    replay = client.get(
        "/api/auth/me",
        headers={"Cookie": f"caresync_session={token}"},
    )
    assert replay.status_code == LOCKED_STATUS


def test_a_session_idle_past_the_configured_window_is_refused(
    lockable_client: TestClient,
) -> None:
    _login(lockable_client)
    assert lockable_client.get("/api/auth/me").status_code == 200

    time.sleep(1.2)

    idle = lockable_client.get("/api/auth/me")
    assert idle.status_code == LOCKED_STATUS
    assert idle.json() == {"detail": "Session locked"}


def test_unlocking_with_the_right_credential_resumes_the_same_session(
    lockable_client: TestClient,
) -> None:
    token = _login(lockable_client)
    assert lockable_client.post("/api/auth/lock").status_code == 204

    unlock = lockable_client.post(
        "/api/auth/unlock",
        json={"password": CLINICAL_PASSWORD},
    )
    assert unlock.status_code == 200
    assert unlock.json()["email"] == CLINICAL_EMAIL

    # The same session token still works: unlocking is a credential check on
    # the existing session, not a fresh sign-in that issues a new token.
    assert lockable_client.cookies.get("caresync_session") == token
    assert lockable_client.get("/api/auth/me").status_code == 200
    assert lockable_client.get("/api/clinical/access").status_code == 200


def test_an_idle_session_survives_and_can_be_unlocked(
    lockable_client: TestClient,
) -> None:
    _login(lockable_client)
    time.sleep(1.2)
    assert lockable_client.get("/api/auth/me").status_code == LOCKED_STATUS

    # The session row survived the inactivity lock, so the right credential
    # resumes it rather than starting over.
    unlock = lockable_client.post(
        "/api/auth/unlock",
        json={"password": CLINICAL_PASSWORD},
    )
    assert unlock.status_code == 200
    assert lockable_client.get("/api/auth/me").status_code == 200


def test_unlocking_with_the_wrong_credential_is_refused_and_rate_limited(
    lockable_client: TestClient,
) -> None:
    _login(lockable_client)
    assert lockable_client.post("/api/auth/lock").status_code == 204

    wrong = {"password": "not-the-password"}
    for _ in range(3):
        refused = lockable_client.post("/api/auth/unlock", json=wrong)
        assert refused.status_code == 401
        assert refused.json() == {"detail": "Invalid password"}

    # The fourth attempt is rate-limited even when the password is right, so a
    # locked tablet is not an unattended guessing surface.
    blocked = lockable_client.post(
        "/api/auth/unlock",
        json={"password": CLINICAL_PASSWORD},
    )
    assert blocked.status_code == 429
    assert "try again" in blocked.json()["detail"].lower()
    assert lockable_client.get("/api/auth/me").status_code == LOCKED_STATUS


def test_a_valid_unlocked_session_is_unaffected(client: TestClient) -> None:
    _login(client)

    for _ in range(3):
        assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/clinical/access").status_code == 200


def test_unlock_is_refused_without_a_session(client: TestClient) -> None:
    response = client.post(
        "/api/auth/unlock",
        json={"password": CLINICAL_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_switch_user_signs_out_and_returns_to_sign_in(client: TestClient) -> None:
    token = _login(client)

    switch = client.post("/api/auth/switch-user")

    assert switch.status_code == 204
    set_cookie = switch.headers["set-cookie"]
    assert "caresync_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert client.get("/api/auth/me").status_code == 401

    # The session row is gone: the old token cannot be replayed by whoever
    # picks the tablet up next.
    replay = client.get(
        "/api/auth/me",
        headers={"Cookie": f"caresync_session={token}"},
    )
    assert replay.status_code == 401
