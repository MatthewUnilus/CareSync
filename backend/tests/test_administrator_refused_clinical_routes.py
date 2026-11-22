"""An Administrator is refused every Clinical route, at the API boundary.

Hiding buttons is not enforcement. These cases drive every Clinical route the
router exposes with a valid request body and an Administrator session, and
assert that the role guard refuses it before the handler can run.

The case list is derived from the router rather than hard-coded, so a route that
is added, renamed or removed cannot drift out of this test's coverage.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import clinical

from conftest import VISIT_INTAKE

PATIENT = {
    "full_name": "Ada Lovelace",
    "age": 36,
    "sex": "female",
    "contact_phone": "07700 900123",
    "contact_email": None,
}

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

# A valid body per body-bearing route, keyed by (method, path template). A route
# not listed here takes no body, so the guard is exercised with ``None``.
_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/clinical/patients"): PATIENT,
    ("POST", "/api/clinical/encounters"): {
        "patient_id": 1,
        "intake": VISIT_INTAKE,
    },
    ("PUT", "/api/clinical/encounters/{encounter_id}/intake"): VISIT_INTAKE,
}

_PATH_PARAMS = {"patient_id": "1", "encounter_id": "1"}


def _concrete_path(template: str) -> str:
    path = template
    for name, value in _PATH_PARAMS.items():
        path = path.replace("{" + name + "}", value)
    return path


def _clinical_route_cases() -> list[tuple[str, str, str, dict[str, Any] | None]]:
    cases: list[tuple[str, str, str, dict[str, Any] | None]] = []
    for route in clinical.router.routes:
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


CLINICAL_ROUTE_CASES = _clinical_route_cases()


@pytest.mark.parametrize(
    ("method", "template", "path", "body"),
    CLINICAL_ROUTE_CASES,
    ids=[f"{method} {template}" for method, template, _, _ in CLINICAL_ROUTE_CASES],
)
def test_an_administrator_is_refused_every_clinical_route(
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


def test_the_removed_triage_routes_are_gone() -> None:
    """The Queue, Override and Re-assessment routes left with the engine."""
    removed_suffixes = (
        "/queue",
        "/override",
        "/override-reasons",
        "/departure",
        "/reassessment",
    )
    paths = {route.path for route in clinical.router.routes}
    assert not [path for path in paths if path.endswith(removed_suffixes)]


def test_the_end_visit_route_refuses_an_administrator(
    client: TestClient,
) -> None:
    """Ending a visit is a Clinical action, refused to an Administrator.

    The parametrized cases above cover every route the router exposes; this pins
    the end-of-visit contract explicitly, so a rename or a dropped route guard
    fails here rather than silently reducing coverage.
    """
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    response = client.post("/api/clinical/encounters/1/end")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}
