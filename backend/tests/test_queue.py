"""The Queue, exercised at the HTTP API seam.

The Queue is a sort over awaiting Encounters: Urgency Level first, then arrival
time so equally urgent Encounters are first-in-first-out. It is not a stored
sequence, so these tests assert the order the API returns after real actions.
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

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

# The shipped interim classifier separates these three presentations. Age is one
# of its inputs and comes from the Patient, so each fixture carries the age the
# Patient is registered with. The pain levels are recorded on the Assessment but
# do not move this artefact; see README "Prioritization Engine and the Queue".


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


def queue_entries(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/clinical/queue")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_the_queue_is_ordered_by_urgency_then_arrival(
    clinical_client: TestClient,
) -> None:
    low_patient = register_patient(clinical_client, "Ada Lovelace", LOW_AGE)
    medium_patient = register_patient(clinical_client, "Grace Hopper", MEDIUM_AGE)
    high_patient = register_patient(clinical_client, "Alan Turing", HIGH_AGE)

    low = open_encounter(clinical_client, low_patient, LOW_INTAKE)
    high_first = open_encounter(clinical_client, high_patient, HIGH_INTAKE)
    medium = open_encounter(clinical_client, medium_patient, MEDIUM_INTAKE)
    high_second = open_encounter(
        clinical_client, high_patient, {**HIGH_INTAKE, "pain_level": 10}
    )

    entries = queue_entries(clinical_client)

    assert [entry["encounter_id"] for entry in entries] == [
        high_first["id"],
        high_second["id"],
        medium["id"],
        low["id"],
    ]
    assert [entry["urgency_level"] for entry in entries] == [
        "High",
        "High",
        "Medium",
        "Low",
    ]


def test_equally_urgent_encounters_are_first_in_first_out(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    arrived = [
        open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)["id"]
        for _ in range(3)
    ]

    entries = queue_entries(clinical_client)

    assert [entry["encounter_id"] for entry in entries] == arrived


def test_only_awaiting_encounters_appear_in_the_queue(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, "Alan Turing", HIGH_AGE)
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

    entries = queue_entries(clinical_client)

    assert [entry["encounter_id"] for entry in entries] == [awaiting["id"]]


def test_each_entry_carries_the_card_fields_the_board_renders(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)

    response = clinical_client.get("/api/clinical/queue")

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["as_of"]).tzinfo is not None

    (entry,) = body["entries"]
    assert entry["encounter_id"] == encounter["id"]
    assert entry["patient"]["full_name"] == "Ada Lovelace"
    assert entry["intake"] == HIGH_INTAKE
    assert entry["assessment"]["machine_recommendation"] == "High"
    assert entry["urgency_level"] == "High"


def test_time_waiting_is_computed_from_arrival_at_read_time(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    (entry,) = queue_entries(clinical_client)

    assert entry["encounter_id"] == encounter["id"]
    assert entry["arrived_at"] == encounter["arrived_at"]
    assert isinstance(entry["waiting_seconds"], int)
    assert 0 <= entry["waiting_seconds"] < 60


def test_the_final_decision_governs_the_queue_order(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    high = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    medium = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        high["id"],
        medium["id"],
    ]

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        assessment = session.get(TriageAssessment, high["assessment"]["id"])
        assert assessment is not None
        assessment.final_decision = "Low"
        session.commit()

    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        medium["id"],
        high["id"],
    ]

    detail = clinical_client.get(f"/api/clinical/encounters/{high['id']}").json()
    assert detail["assessment"]["machine_recommendation"] == "High"
    assert detail["assessment"]["final_decision"] == "Low"


def test_the_per_encounter_detail_carries_its_assessment(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = clinical_client.get(f"/api/clinical/encounters/{encounter['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["assessment"]["machine_recommendation"] == "Medium"
    assert body["assessment"]["snapshot"] == {**MEDIUM_INTAKE, "age": MEDIUM_AGE}
    assert body["intake"] == MEDIUM_INTAKE


def test_the_queue_is_clinical_only(client: TestClient) -> None:
    assert client.get("/api/clinical/queue").status_code == 401

    assert (
        client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS).status_code
        == 200
    )
    response = client.get("/api/clinical/queue")
    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}
