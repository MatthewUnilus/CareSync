"""An Administrator is refused every Clinical route, at the API boundary.

Hiding buttons is not enforcement. These cases drive each Clinical route that
exists today with a valid request body and an Administrator session, and assert
that the role guard refuses it before the handler can run.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.routers import clinical

LOW_INTAKE = {
    "presenting_complaint": "Mild headache for a day",
    "pain_level": 2,
    "illness_duration_hours": 24,
    "temperature_c": 36.8,
    "heart_rate_bpm": 78,
    "blood_pressure": {"systolic": 120, "diastolic": 80},
    "oxygen_saturation_percent": 98,
    "notes": None,
}

PATIENT = {
    "full_name": "Ada Lovelace",
    "age": 36,
    "sex": "female",
    "contact_phone": "07700 900123",
    "contact_email": None,
}

# (HTTP method, route template, concrete path, JSON body)
CLINICAL_ROUTE_CASES: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("GET", "/api/clinical/access", "/api/clinical/access", None),
    ("POST", "/api/clinical/patients", "/api/clinical/patients", PATIENT),
    (
        "POST",
        "/api/clinical/encounters",
        "/api/clinical/encounters",
        {"patient_id": 1, "intake": LOW_INTAKE},
    ),
    (
        "GET",
        "/api/clinical/encounters",
        "/api/clinical/encounters",
        None,
    ),
    ("GET", "/api/clinical/queue", "/api/clinical/queue", None),
    (
        "GET",
        "/api/clinical/encounters/{encounter_id}",
        "/api/clinical/encounters/1",
        None,
    ),
    (
        "PUT",
        "/api/clinical/encounters/{encounter_id}/intake",
        "/api/clinical/encounters/1/intake",
        LOW_INTAKE,
    ),
]


def _clinical_route_methods() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in clinical.router.routes
        for method in getattr(route, "methods", set())
    }


def test_the_cases_cover_every_clinical_route_that_exists_today() -> None:
    covered = {(method, template) for method, template, _, _ in CLINICAL_ROUTE_CASES}

    assert covered == _clinical_route_methods()


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
    login = client.post(
        "/api/auth/login",
        json={
            "email": "administrator@example.com",
            "password": "administrator-password",
        },
    )
    assert login.status_code == 200

    response = client.request(method, path, json=body)

    assert response.status_code == 403, (
        f"{method} {template} should refuse an Administrator"
    )
    assert response.json() == {"detail": "Role not permitted"}
