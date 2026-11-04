"""Departure: a Clinical user discharges an Encounter from the Queue.

These tests drive the HTTP API. Departure is an explicit Clinical action that
records the departure instant at the moment it is performed, and nothing else:
the Encounter leaves the awaiting Queue because the Queue filters on
``departed_at``, the record stays readable, and no later clinical action is
accepted against it.

The two conditions come from the same nullable column — awaiting while
``departed_at`` is null, departed once it is set — so there is no second status
column to drift out of step.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import (
    LOW_AGE,
    LOW_INTAKE,
    MEDIUM_AGE,
    MEDIUM_INTAKE,
)
from app.departures import (
    ALREADY_DEPARTED_DETAIL,
    REASSESSMENT_DEPARTED_DETAIL,
    ensure_awaiting,
)
from app.models import Encounter
from app.overrides import ENCOUNTER_DEPARTED_DETAIL

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}



def register_patient(
    client: TestClient, full_name: str = "Ada Lovelace", age: int = 36
) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": full_name,
            "age": age,
            "sex": "female",
            "contact_phone": "07700 900123",
            "contact_email": None,
        },
    )
    assert response.status_code in (200, 201)
    return response.json()["id"]


def open_encounter(
    client: TestClient,
    patient_id: int,
    intake: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient_id, "intake": intake},
    )
    assert response.status_code == 201, response.text
    return response.json()


def depart(client: TestClient, encounter_id: int, **kwargs: Any):
    return client.post(
        f"/api/clinical/encounters/{encounter_id}/departure", **kwargs
    )


def detail(client: TestClient, encounter_id: int) -> dict[str, Any]:
    response = client.get(f"/api/clinical/encounters/{encounter_id}")
    assert response.status_code == 200, response.text
    return response.json()


def queue_ids(client: TestClient) -> list[int]:
    response = client.get("/api/clinical/queue")
    assert response.status_code == 200, response.text
    return [entry["encounter_id"] for entry in response.json()["entries"]]


def administrator_queue_ids(client: TestClient) -> list[int]:
    response = client.get("/api/administrator/queue")
    assert response.status_code == 200, response.text
    return [entry["encounter_id"] for entry in response.json()["entries"]]


def stored_encounter(client: TestClient, encounter_id: int) -> Encounter:
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        encounter = session.get(Encounter, encounter_id)
        assert encounter is not None
        return encounter


def test_a_clinical_user_departs_an_awaiting_encounter(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    assert encounter["status"] == "awaiting"
    assert encounter["departed_at"] is None

    response = depart(clinical_client, encounter["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == encounter["id"]
    assert body["status"] == "departed"
    departed_at = datetime.fromisoformat(body["departed_at"])
    assert departed_at.tzinfo is not None
    arrived_at = datetime.fromisoformat(body["arrived_at"])
    now = datetime.now(timezone.utc)
    assert arrived_at <= departed_at <= now + timedelta(seconds=5)


def test_the_caller_never_supplies_the_departure_instant(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    supplied = "2000-01-01T00:00:00+00:00"

    response = depart(clinical_client, encounter["id"], json={"departed_at": supplied})

    assert response.status_code == 200, response.text
    recorded = datetime.fromisoformat(response.json()["departed_at"])
    assert recorded != datetime.fromisoformat(supplied)
    assert recorded > datetime.fromisoformat(encounter["arrived_at"])


def test_the_departed_encounter_leaves_the_awaiting_queue(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    departing = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    staying = open_encounter(
        clinical_client, register_patient(clinical_client, "Grace Hopper", LOW_AGE), LOW_INTAKE
    )

    assert queue_ids(clinical_client) == [departing["id"], staying["id"]]

    assert depart(clinical_client, departing["id"]).status_code == 200

    # No new refresh mechanism: the existing Queue read reflects the change.
    assert queue_ids(clinical_client) == [staying["id"]]


def test_a_departed_encounter_leaves_the_administrator_board_too(
    client: TestClient,
) -> None:
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "clinical@example.com",
                "password": "clinical-password",
            },
        ).status_code
        == 200
    )
    patient_id = register_patient(client, age=MEDIUM_AGE)
    departing = open_encounter(client, patient_id, MEDIUM_INTAKE)
    staying = open_encounter(
        client, register_patient(client, "Grace Hopper", LOW_AGE), LOW_INTAKE
    )
    assert depart(client, departing["id"]).status_code == 200
    assert client.post("/api/auth/logout").status_code in (200, 204)

    assert client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS).status_code == 200

    assert administrator_queue_ids(client) == [staying["id"]]


def test_a_departed_encounter_remains_readable_with_its_record(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    overridden = clinical_client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json={
            "assessment_id": encounter["assessment"]["id"],
            "final_decision": "High",
            "reason": "patient deteriorating",
        },
    )
    assert overridden.status_code == 200, overridden.text
    before = detail(clinical_client, encounter["id"])

    assert depart(clinical_client, encounter["id"]).status_code == 200

    after = detail(clinical_client, encounter["id"])
    assert after["status"] == "departed"
    assert after["departed_at"] is not None
    assert after["patient"] == before["patient"]
    assert after["intake"] == before["intake"]
    assert after["arrived_at"] == before["arrived_at"]
    # The Triage Assessment and its Override survive departure untouched.
    assert after["assessment"] == before["assessment"]
    assert after["assessment"]["machine_recommendation"] == "Medium"
    assert after["assessment"]["final_decision"] == "High"
    assert after["assessment"]["override"]["reason"] == "patient deteriorating"

    recent = clinical_client.get("/api/clinical/encounters").json()["encounters"]
    assert encounter["id"] in [item["id"] for item in recent]


def test_a_departed_encounter_cannot_be_overridden(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    assert depart(clinical_client, encounter["id"]).status_code == 200

    response = clinical_client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json={
            "assessment_id": encounter["assessment"]["id"],
            "final_decision": "High",
            "reason": "clinical gestalt",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": ENCOUNTER_DEPARTED_DETAIL}
    after = detail(clinical_client, encounter["id"])
    assert after["assessment"]["final_decision"] == "Medium"
    assert after["assessment"]["override"] is None


def test_the_shared_guard_refuses_a_departed_encounter_for_reassessment(
    clinical_client: TestClient,
) -> None:
    """Ticket 10's Re-assessment route refuses through the same guard.

    Re-assessment does not exist yet, so this pins the contract the route will
    use: an action that needs an awaiting Encounter passes its own clear
    message and gets a ``409`` once the Encounter has departed.
    """
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    assert depart(clinical_client, encounter["id"]).status_code == 200

    departed = stored_encounter(clinical_client, encounter["id"])
    with pytest.raises(HTTPException) as raised:
        ensure_awaiting(departed, REASSESSMENT_DEPARTED_DETAIL)

    assert raised.value.status_code == 409
    assert raised.value.detail == REASSESSMENT_DEPARTED_DETAIL
    assert raised.value.detail == "A departed Encounter cannot be re-assessed"


def test_an_already_departed_encounter_cannot_be_departed_again(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    first = depart(clinical_client, encounter["id"])
    assert first.status_code == 200
    first_instant = first.json()["departed_at"]

    second = depart(clinical_client, encounter["id"])

    assert second.status_code == 409
    assert second.json() == {"detail": ALREADY_DEPARTED_DETAIL}
    # The one recorded departure instant is not overwritten.
    assert detail(clinical_client, encounter["id"])["departed_at"] == first_instant


def test_an_encounter_is_never_departed_on_the_systems_own_initiative(
    clinical_client: TestClient,
) -> None:
    """Elapsed time and repeated reads do not remove an Encounter.

    The only thing that can depart an Encounter is the action itself: here an
    Encounter that arrived three days ago is still awaiting, with no departure
    instant invented for it, after several reads of the Queue.
    """
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(Encounter, encounter["id"])
        assert stored is not None
        stored.arrived_at = datetime.now(timezone.utc) - timedelta(days=3)
        session.commit()

    for _ in range(3):
        assert encounter["id"] in queue_ids(clinical_client)

    after = detail(clinical_client, encounter["id"])
    assert after["status"] == "awaiting"
    assert after["departed_at"] is None


def test_the_two_conditions_are_awaiting_and_departed(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    assert detail(clinical_client, encounter["id"])["status"] == "awaiting"
    assert detail(clinical_client, encounter["id"])["departed_at"] is None

    assert depart(clinical_client, encounter["id"]).status_code == 200

    departed = detail(clinical_client, encounter["id"])
    assert departed["status"] == "departed"
    assert departed["departed_at"] is not None
    # There is no in-treatment or left-without-being-seen condition.
    assert "in_treatment" not in departed
    assert "left_without_being_seen" not in departed


def test_an_unknown_encounter_cannot_be_departed(
    clinical_client: TestClient,
) -> None:
    response = depart(clinical_client, 9999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter not found"}


def test_an_administrator_is_refused_a_departure(client: TestClient) -> None:
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "clinical@example.com",
                "password": "clinical-password",
            },
        ).status_code
        == 200
    )
    patient_id = register_patient(client, age=LOW_AGE)
    encounter = open_encounter(client, patient_id, LOW_INTAKE)
    assert client.post("/api/auth/logout").status_code in (200, 204)
    assert client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS).status_code == 200

    response = depart(client, encounter["id"])

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}
    assert stored_encounter(client, encounter["id"]).departed_at is None


def test_an_unauthenticated_request_is_refused(client: TestClient) -> None:
    response = depart(client, 1)

    assert response.status_code == 401
