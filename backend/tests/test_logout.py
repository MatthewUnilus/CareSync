from fastapi.testclient import TestClient

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"


def test_logout_ends_the_session_and_clears_the_cookie(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    token = client.cookies.get("caresync_session")
    assert token

    logout = client.post("/api/auth/logout")

    assert logout.status_code == 204
    set_cookie = logout.headers["set-cookie"]
    assert "caresync_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert client.get("/api/auth/me").status_code == 401

    replay = client.get(
        "/api/auth/me",
        headers={"Cookie": f"caresync_session={token}"},
    )
    assert replay.status_code == 401


def test_logout_without_a_session_is_harmless(client: TestClient) -> None:
    response = client.post("/api/auth/logout")

    assert response.status_code == 204
