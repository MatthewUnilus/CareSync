"""A Triage Assessment is the durable record of one urgency decision.

These tests drive the API and inspect the stored record through it: what was
captured, what the engine recommended, and that the recommendation cannot move
once written.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.intake import INTAKE_LOCKED_DETAIL
from app.models import TriageAssessment

LOW_INTAKE = {
    "presenting_complaint": "Mild headache for a day",
    "pain_level": 2,
    "illness_duration_hours": 24,
    "temperature_c": 36.6,
    "heart_rate_bpm": 70,
    "blood_pressure": {"systolic": 116, "diastolic": 72},
    "oxygen_saturation_percent": 99,
    "notes": None,
}

MEDIUM_INTAKE = {
    **LOW_INTAKE,
    "pain_level": 6,
    "presenting_complaint": "Abdominal pain",
    "illness_duration_hours": 12,
    "temperature_c": 36.8,
    "heart_rate_bpm": 80,
    "blood_pressure": {"systolic": 110, "diastolic": 70},
    "oxygen_saturation_percent": 94,
}

HIGH_INTAKE = {
    **LOW_INTAKE,
    "pain_level": 9,
    "presenting_complaint": "Chest pain",
    "illness_duration_hours": 2,
    "temperature_c": 38.4,
    "heart_rate_bpm": 130,
    "blood_pressure": {"systolic": 95, "diastolic": 58},
    "oxygen_saturation_percent": 88,
}

LOW_AGE = 24
MEDIUM_AGE = 80
HIGH_AGE = 78


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
            "contact_email": "ada@example.com",
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


@pytest.mark.parametrize(
    ("intake", "age", "expected", "recognised"),
    [
        (LOW_INTAKE, LOW_AGE, "Low", "headache"),
        (MEDIUM_INTAKE, MEDIUM_AGE, "Medium", "abdominal pain"),
        (HIGH_INTAKE, HIGH_AGE, "High", "chest pain"),
    ],
)
def test_completing_intake_stores_the_machine_recommendation(
    clinical_client: TestClient,
    intake: dict[str, Any],
    age: int,
    expected: str,
    recognised: str,
) -> None:
    body = open_encounter(
        clinical_client, register_patient(clinical_client, age=age), intake
    )

    assessment = body["assessment"]
    assert assessment["machine_recommendation"] == expected
    assert assessment["final_decision"] == expected
    # Recognition is a separate input, captured with the snapshot; the
    # recommendation above comes from the trained classifier.
    assert assessment["recognised_symptom_groups"] == [recognised]


def test_the_assessment_captures_an_immutable_snapshot_of_the_inputs(
    clinical_client: TestClient,
) -> None:
    body = open_encounter(
        clinical_client,
        register_patient(clinical_client, age=HIGH_AGE),
        HIGH_INTAKE,
    )

    snapshot = body["assessment"]["snapshot"]
    assert snapshot == {**HIGH_INTAKE, "age": HIGH_AGE}


def test_intake_cannot_be_corrected_once_an_assessment_exists(
    clinical_client: TestClient,
) -> None:
    encounter = open_encounter(
        clinical_client, register_patient(clinical_client), HIGH_INTAKE
    )
    assessment = encounter["assessment"]

    response = clinical_client.put(
        f"/api/clinical/encounters/{encounter['id']}/intake",
        json={**HIGH_INTAKE, "pain_level": 3},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": INTAKE_LOCKED_DETAIL}

    fetched = clinical_client.get(f"/api/clinical/encounters/{encounter['id']}").json()
    assert fetched["intake"] == HIGH_INTAKE
    assert fetched["assessment"] == assessment


def test_the_machine_recommendation_cannot_be_rewritten(
    clinical_client: TestClient,
) -> None:
    body = open_encounter(
        clinical_client, register_patient(clinical_client), HIGH_INTAKE
    )
    assessment_id = body["assessment"]["id"]
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        assessment = session.get(TriageAssessment, assessment_id)
        assert assessment is not None
        assessment.machine_recommendation = "Low"
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(TriageAssessment, assessment_id)
        assert stored is not None
        assert stored.machine_recommendation == "High"
