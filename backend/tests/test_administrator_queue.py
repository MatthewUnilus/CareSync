"""The Administrator's view of the Queue, exercised at the HTTP API seam.

An Administrator surveys the same awaiting Queue as a Clinical user, but as a
dense read-only projection. The projection must follow changes that happen
elsewhere — an Override changes the governing Final Decision, a Departure
removes the Encounter — so a poll of this route always shows current state.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from conftest import (
    HIGH_AGE,
    HIGH_INTAKE,
    LOW_AGE,
    LOW_INTAKE,
    MEDIUM_AGE,
    MEDIUM_INTAKE,
)
from app.models import Encounter, TriageAssessment



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


def login_as_administrator(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "administrator@example.com",
            "password": "administrator-password",
        },
    )
    assert response.status_code == 200


def administrator_entries(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/administrator/queue")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_the_administrator_sees_the_awaiting_queue_in_queue_order(
    clinical_client: TestClient,
) -> None:
    low = open_encounter(
        clinical_client, register_patient(clinical_client, "Ada Lovelace", LOW_AGE), LOW_INTAKE
    )
    high = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Alan Turing", HIGH_AGE),
        HIGH_INTAKE,
    )
    medium = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Grace Hopper", MEDIUM_AGE),
        MEDIUM_INTAKE,
    )

    login_as_administrator(clinical_client)
    response = clinical_client.get("/api/administrator/queue")

    assert response.status_code == 200, response.text
    body = response.json()
    assert datetime.fromisoformat(body["as_of"]).tzinfo is not None
    assert [entry["encounter_id"] for entry in body["entries"]] == [
        high["id"],
        medium["id"],
        low["id"],
    ]
    assert [entry["urgency_level"] for entry in body["entries"]] == [
        "High",
        "Medium",
        "Low",
    ]


def test_each_administrator_row_carries_the_dense_table_fields(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)

    login_as_administrator(clinical_client)
    (entry,) = administrator_entries(clinical_client)

    assert entry["encounter_id"] == encounter["id"]
    assert entry["patient_name"] == "Ada Lovelace"
    assert entry["presenting_complaint"] == HIGH_INTAKE["presenting_complaint"]
    assert isinstance(entry["waiting_seconds"], int)
    assert 0 <= entry["waiting_seconds"] < 60
    assert entry["urgency_level"] == "High"
    assert entry["machine_recommendation"] == "High"
    assert entry["final_decision"] == "High"
    assert entry["final_decision_differs"] is False


def test_the_administrator_row_reflects_an_override_on_the_next_read(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        assessment = session.get(TriageAssessment, encounter["assessment"]["id"])
        assert assessment is not None
        # Ticket 09 will perform this through an Override action; the read
        # model must not assume the two values are always equal.
        assessment.final_decision = "Low"
        session.commit()

    login_as_administrator(clinical_client)
    (entry,) = administrator_entries(clinical_client)

    assert entry["encounter_id"] == encounter["id"]
    assert entry["urgency_level"] == "Low"
    assert entry["final_decision"] == "Low"
    assert entry["machine_recommendation"] == "High"
    assert entry["final_decision_differs"] is True


def test_the_administrator_row_disappears_after_a_departure(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    departed = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    awaiting = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Ada Lovelace", LOW_AGE),
        LOW_INTAKE,
    )

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        encounter = session.get(Encounter, departed["id"])
        assert encounter is not None
        encounter.departed_at = datetime.now(timezone.utc)
        session.commit()

    login_as_administrator(clinical_client)
    entries = administrator_entries(clinical_client)

    assert [entry["encounter_id"] for entry in entries] == [awaiting["id"]]


def test_the_administrator_queue_is_administrator_only(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/administrator/queue")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_the_administrator_queue_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/administrator/queue")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
