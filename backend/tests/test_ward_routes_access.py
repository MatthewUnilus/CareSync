"""The ward routes are Clinical actions, refused to an Administrator and to nobody.

Hiding buttons is not enforcement. These cases drive every route the ward router
exposes: an Administrator session is refused with ``403`` before the handler can
run, and an unauthenticated request with ``401``. The case list is derived from
the router so a route that is added, renamed or removed cannot drift out of
coverage.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import ward

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

# A valid body per body-bearing route, keyed by (method, path template). A route
# not listed here takes no body, so it is exercised with ``None``.
_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/ward/admissions"): {
        "patient_id": 1,
        "ward": "Ward A",
        "bed": "1",
        "encounter_id": None,
    },
    ("POST", "/api/ward/admissions/{admission_id}/move"): {
        "ward": "Ward B",
        "bed": "2",
    },
    ("POST", "/api/ward/admissions/{admission_id}/medication-orders"): {
        "drug": "Amoxicillin",
        "dose": "500 mg",
        "route": "oral",
        "frequency": "once_daily",
        "start_at": "2026-11-20T08:00:00+00:00",
        "instructed_by": "Dr Okafor",
    },
}

_PATH_PARAMS = {"admission_id": "1", "order_id": "1", "id": "1"}

#: Required query strings per route template, so a route whose only missing piece
#: is a query parameter still reaches the role guard rather than a 422.
_QUERY = {
    "/api/ward/admissions": "patient_id=1",
    "/api/ward/medications/due": (
        "from=2026-11-19T00:00:00%2B00:00&to=2026-11-20T00:00:00%2B00:00"
    ),
}


def _concrete_path(template: str) -> str:
    path = template
    for name, value in _PATH_PARAMS.items():
        path = path.replace("{" + name + "}", value)
    if template in _QUERY:
        path = f"{path}?{_QUERY[template]}"
    return path


def _ward_route_cases() -> list[tuple[str, str, str, dict[str, Any] | None]]:
    cases: list[tuple[str, str, str, dict[str, Any] | None]] = []
    for route in ward.router.routes:
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            template = route.path
            cases.append(
                (
                    method,
                    template,
                    _concrete_path(template),
                    _BODIES.get((method, template)),
                )
            )
    return sorted(cases, key=lambda case: (case[1], case[0]))


WARD_ROUTE_CASES = _ward_route_cases()


@pytest.mark.parametrize(
    ("method", "template", "path", "body"),
    WARD_ROUTE_CASES,
    ids=[f"{method} {template}" for method, template, _, _ in WARD_ROUTE_CASES],
)
def test_an_administrator_is_refused_every_ward_route(
    client: TestClient,
    method: str,
    template: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    response = client.request(method, path, json=body)

    assert response.status_code == 403, (
        f"{method} {template} should refuse an Administrator"
    )
    assert response.json() == {"detail": "Role not permitted"}


@pytest.mark.parametrize(
    ("method", "template", "path", "body"),
    WARD_ROUTE_CASES,
    ids=[f"{method} {template}" for method, template, _, _ in WARD_ROUTE_CASES],
)
def test_every_ward_route_requires_authentication(
    client: TestClient,
    method: str,
    template: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    response = client.request(method, path, json=body)

    assert response.status_code == 401, (
        f"{method} {template} should require a session"
    )
