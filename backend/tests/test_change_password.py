from fastapi.testclient import TestClient

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"
NEW_PASSWORD = "a-new-clinical-password"


def _login(client: TestClient, password: str) -> int:
    response = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": password},
    )
    return response.status_code


def test_authenticated_user_can_change_own_password(client: TestClient) -> None:
    assert _login(client, CLINICAL_PASSWORD) == 200

    change = client.post(
        "/api/auth/password",
        json={
            "current_password": CLINICAL_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )

    assert change.status_code == 204
    assert client.get("/api/auth/me").status_code == 200

    client.post("/api/auth/logout")
    assert _login(client, CLINICAL_PASSWORD) == 401
    assert _login(client, NEW_PASSWORD) == 200


def test_password_change_is_refused_when_current_password_is_wrong(
    client: TestClient,
) -> None:
    assert _login(client, CLINICAL_PASSWORD) == 200

    change = client.post(
        "/api/auth/password",
        json={
            "current_password": "not-the-current-password",
            "new_password": NEW_PASSWORD,
        },
    )

    assert change.status_code == 400
    assert change.json() == {"detail": "Current password is incorrect"}

    client.post("/api/auth/logout")
    assert _login(client, CLINICAL_PASSWORD) == 200


def test_password_change_requires_an_authenticated_session(client: TestClient) -> None:
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": CLINICAL_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401
