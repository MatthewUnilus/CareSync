"""Ticket 31: admission, move and discharge each write exactly one audit entry.

Every ward mutation shares the transaction of its change (ADR 0007): admitting,
moving and discharging each append one attributable entry, and charting a set
against a stay names that Admission as the entry's subject. The log is read back
through the Administrator-only route, as an Administrator does.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

from app.audit_actions import AuditAction

CLINICAL_AUDIT_ACTOR = "Clinical Demo User"

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
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def open_encounter(client: TestClient, patient_id: int) -> int:
    response = client.post(
        "/api/clinical/encounters",
        json={
            "patient_id": patient_id,
            "intake": {"presenting_complaint": "Shortness of breath"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def admit(
    client: TestClient,
    patient_id: int,
    encounter_id: int | None = None,
    ward: str = "Ward A",
    bed: str = "3",
):
    return client.post(
        "/api/ward/admissions",
        json={
            "patient_id": patient_id,
            "ward": ward,
            "bed": bed,
            "encounter_id": encounter_id,
        },
    )


def move(client: TestClient, admission_id: int, ward: str, bed: str):
    return client.post(
        f"/api/ward/admissions/{admission_id}/move",
        json={"ward": ward, "bed": bed},
    )


def discharge(client: TestClient, admission_id: int):
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def login_as_administrator(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert response.status_code == 200


def audit_log(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    login_as_administrator(client)
    response = client.get("/api/administrator/audit-log", params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def actions(entries: list[dict[str, Any]]) -> list[str]:
    return [entry["action"] for entry in entries]


def test_admitting_a_patient_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    admission_id = admit(
        clinical_client, patient_id, encounter_id=encounter_id
    ).json()["id"]

    entries = [
        entry
        for entry in audit_log(clinical_client)
        if entry["action"] == AuditAction.admit_patient.value
    ]

    (entry,) = entries
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["encounter_id"] == encounter_id
    assert entry["action_label"] == "Patient admitted"
    assert datetime.fromisoformat(entry["recorded_at"]).tzinfo is not None


def test_a_direct_admission_writes_one_entry_with_no_encounter(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admit(clinical_client, patient_id)

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.admit_patient.value
    ]

    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] is None
    assert entry["admission_id"] is not None


def test_a_refused_admission_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    """A refused mutation leaves no record, because it never happened."""
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_encounter = open_encounter(clinical_client, first)

    refused = admit(clinical_client, second, encounter_id=first_encounter)
    assert refused.status_code == 409, refused.text

    assert AuditAction.admit_patient.value not in actions(audit_log(clinical_client))


def test_a_location_move_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]

    assert move(clinical_client, admission_id, "Ward B", "12").status_code == 200

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.move_admission.value
    ]
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Admission location moved"
    # The move is recorded, so a reader can see where the Patient went.
    assert entry["detail"] == "Ward A / 3 -> Ward B / 12"


def test_discharging_a_patient_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]

    assert discharge(clinical_client, admission_id).status_code == 200

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.discharge_patient.value
    ]
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Patient discharged"


def test_charting_against_an_admission_names_it_as_the_subject(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]

    charted = clinical_client.post(
        f"/api/clinical/admissions/{admission_id}/observations",
        json={
            "pain_level": 4,
            "illness_duration_hours": 12,
            "temperature_c": 37.0,
            "heart_rate_bpm": 80,
            "respiratory_rate_bpm": 16,
            "blood_pressure": {"systolic": 120, "diastolic": 78},
            "oxygen_saturation_percent": 98,
            "notes": None,
        },
    )
    assert charted.status_code == 201, charted.text

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.chart_observation.value
    ]
    assert entry["admission_id"] == admission_id
    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] is None


def test_the_audit_log_filters_to_a_single_admission(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    first = admit(clinical_client, patient_id, ward="Ward A", bed="1").json()["id"]
    second = admit(clinical_client, patient_id, ward="Ward B", bed="2").json()["id"]
    assert move(clinical_client, first, "Ward C", "9").status_code == 200

    entries = audit_log(clinical_client, admission_id=first)

    assert actions(entries) == [
        AuditAction.admit_patient.value,
        AuditAction.move_admission.value,
    ]
    assert {entry["admission_id"] for entry in entries} == {first}
    assert second not in {entry["admission_id"] for entry in entries}
