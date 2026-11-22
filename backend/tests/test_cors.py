from fastapi.testclient import TestClient

PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}


def test_native_webview_origin_may_call_the_api_with_credentials(
    client: TestClient,
) -> None:
    response = client.options(
        "/api/auth/login",
        headers={"Origin": "http://localhost", **PREFLIGHT_HEADERS},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_is_not_granted_cors(client: TestClient) -> None:
    response = client.options(
        "/api/auth/login",
        headers={"Origin": "https://not-caresync.example", **PREFLIGHT_HEADERS},
    )

    assert "access-control-allow-origin" not in response.headers
