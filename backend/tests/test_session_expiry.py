import time

from fastapi.testclient import TestClient

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"


def test_session_stops_working_once_its_expiry_has_passed(
    short_session_client: TestClient,
) -> None:
    login = short_session_client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )
    assert login.status_code == 200

    token = short_session_client.cookies.get("caresync_session")
    assert token

    assert short_session_client.get("/api/auth/me").status_code == 200

    time.sleep(1.2)

    expired = short_session_client.get(
        "/api/auth/me",
        headers={"Cookie": f"caresync_session={token}"},
    )
    assert expired.status_code == 401
    assert expired.json() == {"detail": "Not authenticated"}
