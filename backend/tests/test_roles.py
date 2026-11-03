import pytest
from fastapi.testclient import TestClient

ROLE_CASES = [
    (
        "clinical@example.com",
        "clinical-password",
        "clinical",
        "/api/clinical/access",
        "/api/administrator/access",
    ),
    (
        "administrator@example.com",
        "administrator-password",
        "administrator",
        "/api/administrator/access",
        "/api/clinical/access",
    ),
]


def test_exactly_two_roles_exist(client: TestClient) -> None:
    response = client.get("/api/roles")

    assert response.status_code == 200
    roles = response.json()["roles"]
    assert [role["value"] for role in roles] == ["clinical", "administrator"]
    assert [role["label"] for role in roles] == ["Clinical", "Administrator"]


@pytest.mark.parametrize(
    ("email", "password", "expected_role", "allowed_path", "denied_path"),
    ROLE_CASES,
)
def test_role_is_enforced_at_the_api_boundary(
    client: TestClient,
    email: str,
    password: str,
    expected_role: str,
    allowed_path: str,
    denied_path: str,
) -> None:
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert login.json()["role"] == expected_role

    allowed = client.get(allowed_path)
    assert allowed.status_code == 200
    assert allowed.json()["role"] == expected_role

    denied = client.get(denied_path)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Role not permitted"}


@pytest.mark.parametrize("path", ["/api/clinical/access", "/api/administrator/access"])
def test_role_gated_routes_require_authentication(
    client: TestClient, path: str
) -> None:
    response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
