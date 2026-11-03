from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

INTAKE = {
    "presenting_complaint": "Crushing chest pain since this morning",
    "pain_level": 8,
    "illness_duration_hours": 6,
    "temperature_c": 37.2,
    "heart_rate_bpm": 104,
    "blood_pressure": {"systolic": 148, "diastolic": 92},
    "oxygen_saturation_percent": 94,
    "notes": "Diabetic, on metformin",
}


def register_patient(
    client: TestClient,
    full_name: str = "Ada Lovelace",
    contact_phone: str = "07700 900123",
) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": full_name,
            "age": 36,
            "sex": "female",
            "contact_phone": contact_phone,
            "contact_email": "ada@example.com",
        },
    )
    assert response.status_code in (200, 201)
    return response.json()["id"]


def open_encounter(
    client: TestClient,
    patient_id: int,
    **intake_overrides: Any,
):
    return client.post(
        "/api/clinical/encounters",
        json={
            "patient_id": patient_id,
            "intake": {**INTAKE, **intake_overrides},
        },
    )


def test_clinical_user_opens_an_encounter_with_intake(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)

    response = open_encounter(clinical_client, patient_id)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["patient"]["id"] == patient_id
    assert body["patient"]["full_name"] == "Ada Lovelace"
    assert body["intake"] == INTAKE


def test_arrival_instant_is_recorded_at_creation_and_never_editable(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)

    before = datetime.now(timezone.utc)
    created = open_encounter(clinical_client, patient_id)
    after = datetime.now(timezone.utc)
    assert created.status_code == 201

    arrived_at = datetime.fromisoformat(created.json()["arrived_at"])
    assert arrived_at.tzinfo is not None
    assert before <= arrived_at <= after

    corrected = clinical_client.put(
        f"/api/clinical/encounters/{created.json()['id']}/intake",
        json={**INTAKE, "pain_level": 6, "arrived_at": "1999-01-01T00:00:00Z"},
    )
    assert corrected.status_code == 409

    fetched = clinical_client.get(f"/api/clinical/encounters/{created.json()['id']}")
    assert datetime.fromisoformat(fetched.json()["arrived_at"]) == arrived_at

    no_update = clinical_client.put(
        f"/api/clinical/encounters/{created.json()['id']}",
        json={"arrived_at": "1999-01-01T00:00:00Z"},
    )
    assert no_update.status_code == 405

    assert (
        datetime.fromisoformat(
            clinical_client.get(
                f"/api/clinical/encounters/{created.json()['id']}"
            ).json()["arrived_at"]
        )
        == arrived_at
    )


def test_intake_correction_is_refused_once_an_assessment_exists(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    created = open_encounter(clinical_client, patient_id)
    encounter_id = created.json()["id"]

    corrected_intake = {
        **INTAKE,
        "presenting_complaint": "Chest tightness, worse on exertion",
        "pain_level": 5,
        "temperature_c": 36.8,
        "heart_rate_bpm": 88,
        "blood_pressure": {"systolic": 132, "diastolic": 84},
        "oxygen_saturation_percent": 97,
        "notes": None,
    }

    response = clinical_client.put(
        f"/api/clinical/encounters/{encounter_id}/intake",
        json=corrected_intake,
    )

    assert response.status_code == 409

    fetched = clinical_client.get(f"/api/clinical/encounters/{encounter_id}")
    assert fetched.json()["intake"] == INTAKE
    assert fetched.json()["patient"]["id"] == patient_id


def test_a_patient_may_hold_many_encounters(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)

    first = open_encounter(clinical_client, patient_id)
    second = open_encounter(
        clinical_client, patient_id, presenting_complaint="Follow-up review"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["patient"]["id"] == patient_id
    assert second.json()["patient"]["id"] == patient_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"presenting_complaint": "   "},
        {"pain_level": 0},
        {"pain_level": 11},
        {"illness_duration_hours": -1},
        {"illness_duration_hours": 9000},
        {"temperature_c": 29.9},
        {"temperature_c": 45.1},
        {"heart_rate_bpm": 19},
        {"heart_rate_bpm": 301},
        {"blood_pressure": {"systolic": 120, "diastolic": 120}},
        {"blood_pressure": {"systolic": 49, "diastolic": 20}},
        {"blood_pressure": {"systolic": 150, "diastolic": 19}},
        {"oxygen_saturation_percent": 49},
        {"oxygen_saturation_percent": 101},
        {"notes": "x" * 2001},
    ],
)
def test_intake_ranges_are_validated_when_opening_an_encounter(
    clinical_client: TestClient, overrides: dict[str, Any]
) -> None:
    patient_id = register_patient(clinical_client)

    response = open_encounter(clinical_client, patient_id, **overrides)

    assert response.status_code == 422


def test_intake_ranges_are_validated_when_correcting(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id).json()["id"]

    response = clinical_client.put(
        f"/api/clinical/encounters/{encounter_id}/intake",
        json={**INTAKE, "pain_level": 11},
    )

    assert response.status_code == 422
    assert (
        clinical_client.get(f"/api/clinical/encounters/{encounter_id}").json()["intake"]
        == INTAKE
    )


def test_encounter_must_belong_to_a_known_patient(
    clinical_client: TestClient,
) -> None:
    response = open_encounter(clinical_client, 999_999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_correcting_an_unknown_encounter_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.put(
        "/api/clinical/encounters/999999/intake",
        json=INTAKE,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter not found"}


def test_recent_encounters_are_listed_newest_first(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    older = open_encounter(clinical_client, patient_id).json()
    newer = open_encounter(
        clinical_client, patient_id, presenting_complaint="Shortness of breath"
    ).json()

    response = clinical_client.get("/api/clinical/encounters")

    assert response.status_code == 200
    encounters = response.json()["encounters"]
    assert [encounter["id"] for encounter in encounters] == [
        newer["id"],
        older["id"],
    ]
    assert encounters[0]["patient"]["full_name"] == "Ada Lovelace"
    assert encounters[0]["intake"]["presenting_complaint"] == "Shortness of breath"


def test_administrator_cannot_capture_or_correct_intake(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    encounter_id = open_encounter(client, register_patient(client)).json()["id"]

    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    opened = open_encounter(client, 1)
    corrected = client.put(
        f"/api/clinical/encounters/{encounter_id}/intake", json=INTAKE
    )
    listed = client.get("/api/clinical/encounters")
    fetched = client.get(f"/api/clinical/encounters/{encounter_id}")

    for response in (opened, corrected, listed, fetched):
        assert response.status_code == 403
        assert response.json() == {"detail": "Role not permitted"}


def test_intake_routes_require_authentication(client: TestClient) -> None:
    assert open_encounter(client, 1).status_code == 401
    assert client.put("/api/clinical/encounters/1/intake", json=INTAKE).status_code == 401
    assert client.get("/api/clinical/encounters").status_code == 401
    assert client.get("/api/clinical/encounters/1").status_code == 401
