"""Override: a Clinical user disagrees with a Machine Recommendation.

These tests drive the HTTP API. An Override sets a different Final Decision on
the governing Triage Assessment of an awaiting Encounter, records who performed
it and why, and leaves the Machine Recommendation exactly as the engine wrote
it. The Queue is a sort, so the same read that showed the old order must show
the new one afterwards.
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.assessments import create_triage_assessment
from app.models import Encounter, TriageAssessment
from app.overrides import (
    DECISION_UNCHANGED_DETAIL,
    ENCOUNTER_DEPARTED_DETAIL,
    NOT_GOVERNING_DETAIL,
)

# The fixed set, verbatim from CONTEXT.md "Override Reason".
FIXED_REASONS = (
    "vitals inconsistent with recommendation",
    "symptom not captured",
    "clinical gestalt",
    "patient deteriorating",
    "duplicate entry",
    "other",
)

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

MEDIUM_INTAKE = {**LOW_INTAKE, "pain_level": 6, "presenting_complaint": "Abdominal pain"}

HIGH_INTAKE = {**LOW_INTAKE, "pain_level": 9, "presenting_complaint": "Chest pain"}


def register_patient(client: TestClient, full_name: str = "Ada Lovelace") -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": full_name,
            "age": 36,
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


def override(
    client: TestClient,
    encounter: dict[str, Any],
    **payload: Any,
):
    body = {
        "assessment_id": encounter["assessment"]["id"],
        "final_decision": "High",
        "reason": "clinical gestalt",
        **payload,
    }
    return client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json=body,
    )


def queue_entries(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/clinical/queue")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_a_clinical_user_sets_a_different_final_decision(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = override(clinical_client, encounter, final_decision="Low")

    assert response.status_code == 200, response.text
    assessment = response.json()["assessment"]
    assert assessment["final_decision"] == "Low"
    assert assessment["machine_recommendation"] == "Medium"


def test_the_override_records_the_reason_and_who_performed_it(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = override(
        clinical_client,
        encounter,
        final_decision="High",
        reason="patient deteriorating",
    )

    assert response.status_code == 200, response.text
    record = response.json()["assessment"]["override"]
    assert record["reason"] == "patient deteriorating"
    assert record["free_text"] is None
    assert record["performed_by"]["display_name"] == "Clinical Demo User"
    assert datetime.fromisoformat(record["performed_at"]).tzinfo is not None


@pytest.mark.parametrize("reason", FIXED_REASONS)
def test_every_reason_from_the_fixed_set_is_accepted(
    clinical_client: TestClient,
    reason: str,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    payload: dict[str, Any] = {"reason": reason}
    if reason == "other":
        payload["free_text"] = "Something the fixed set does not cover"

    response = override(clinical_client, encounter, final_decision="High", **payload)

    assert response.status_code == 200, response.text
    assert response.json()["assessment"]["override"]["reason"] == reason


def test_a_reason_outside_the_fixed_set_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = override(
        clinical_client,
        encounter,
        final_decision="High",
        reason="because I said so",
    )

    assert response.status_code == 422
    detail = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()
    assert detail["assessment"]["final_decision"] == "Medium"
    assert detail["assessment"]["override"] is None


def test_an_override_without_a_reason_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    body = {
        "assessment_id": encounter["assessment"]["id"],
        "final_decision": "High",
    }
    response = clinical_client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json=body,
    )

    assert response.status_code == 422
    detail = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()
    assert detail["assessment"]["final_decision"] == "Medium"
    assert detail["assessment"]["override"] is None


def test_free_text_is_accepted_only_for_the_other_reason(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    refused = override(
        clinical_client,
        encounter,
        final_decision="High",
        reason="clinical gestalt",
        free_text="I just know",
    )
    assert refused.status_code == 422

    accepted = override(
        clinical_client,
        encounter,
        final_decision="High",
        reason="other",
        free_text="  Something unusual  ",
    )
    assert accepted.status_code == 200, accepted.text
    record = accepted.json()["assessment"]["override"]
    assert record["reason"] == "other"
    assert record["free_text"] == "Something unusual"


def test_an_override_must_actually_change_the_final_decision(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = override(clinical_client, encounter, final_decision="Medium")

    assert response.status_code == 409
    assert response.json() == {"detail": DECISION_UNCHANGED_DETAIL}
    detail = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()
    assert detail["assessment"]["override"] is None


def test_a_departed_encounter_cannot_be_overridden(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(Encounter, encounter["id"])
        assert stored is not None
        stored.departed_at = datetime.now(timezone.utc)
        session.commit()

    response = override(clinical_client, encounter, final_decision="High")

    assert response.status_code == 409
    assert response.json() == {"detail": ENCOUNTER_DEPARTED_DETAIL}


def test_only_the_governing_assessment_can_be_overridden(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    # Simulate what ticket 10 will do through its own route: append a second
    # Assessment, which becomes the governing one.
    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(Encounter, encounter["id"])
        assert stored is not None
        create_triage_assessment(session, stored)
        session.commit()

    # The detail route exposes the governing Assessment's id.
    detail = clinical_client.get(f"/api/clinical/encounters/{encounter['id']}").json()
    governing_id = detail["assessment"]["id"]
    assert governing_id != encounter["assessment"]["id"]

    refused = override(
        clinical_client,
        encounter,  # carries the superseded Assessment's id
        final_decision="High",
    )
    assert refused.status_code == 409
    assert refused.json() == {"detail": NOT_GOVERNING_DETAIL}

    accepted = clinical_client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json={
            "assessment_id": governing_id,
            "final_decision": "High",
            "reason": "clinical gestalt",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["assessment"]["final_decision"] == "High"


def test_the_machine_recommendation_is_byte_identical_after_an_override(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    before = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()["assessment"]

    response = override(
        clinical_client,
        encounter,
        final_decision="Low",
        reason="vitals inconsistent with recommendation",
    )
    assert response.status_code == 200, response.text

    after = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()["assessment"]
    assert after["machine_recommendation"] == before["machine_recommendation"]
    assert after["machine_recommendation"] == "High"
    assert after["snapshot"] == before["snapshot"]
    assert after["final_decision"] == "Low"

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(TriageAssessment, encounter["assessment"]["id"])
        assert stored is not None
        assert stored.machine_recommendation == "High"


def test_the_override_cannot_carry_a_machine_recommendation(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)

    response = override(
        clinical_client,
        encounter,
        final_decision="Low",
        machine_recommendation="Low",
    )

    assert response.status_code == 422
    after = clinical_client.get(
        f"/api/clinical/encounters/{encounter['id']}"
    ).json()["assessment"]
    assert after["machine_recommendation"] == "High"
    assert after["final_decision"] == "High"


def test_the_queue_reorders_immediately_on_an_override(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    medium = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    low = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        medium["id"],
        low["id"],
    ]

    response = override(clinical_client, low, final_decision="High")
    assert response.status_code == 200, response.text

    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        low["id"],
        medium["id"],
    ]

    response = override(clinical_client, low, final_decision="Medium")
    assert response.status_code == 200, response.text

    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        medium["id"],
        low["id"],
    ]


def test_the_card_carries_an_override_flag_when_the_decisions_differ(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    (before,) = queue_entries(clinical_client)
    assert before["override_flag"] is False

    override(clinical_client, encounter, final_decision="Low")

    (after,) = queue_entries(clinical_client)
    assert after["override_flag"] is True
    assert after["urgency_level"] == "Low"
    assert after["assessment"]["machine_recommendation"] == "Medium"
    assert after["assessment"]["final_decision"] == "Low"


def test_the_override_flag_is_its_own_state_name(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    override(clinical_client, encounter, final_decision="Low")

    (entry,) = queue_entries(clinical_client)

    assert entry["override_flag"] is True
    # Ticket 08 adds the unclassified flag as a separate field; this one is
    # about human disagreement only, never a generic "flagged" concept.
    assert "flagged" not in entry
    assert "unclassified" not in entry


def test_the_fixed_reason_list_is_exposed_by_the_api(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/clinical/override-reasons")

    assert response.status_code == 200, response.text
    assert tuple(response.json()["reasons"]) == FIXED_REASONS


def test_an_unknown_encounter_cannot_be_overridden(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.post(
        "/api/clinical/encounters/9999/override",
        json={
            "assessment_id": 1,
            "final_decision": "High",
            "reason": "clinical gestalt",
        },
    )

    assert response.status_code == 404


def test_an_administrator_is_refused_an_override(client: TestClient) -> None:
    clinical = client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    assert clinical.status_code == 200
    patient_id = register_patient(client)
    encounter = open_encounter(client, patient_id, MEDIUM_INTAKE)
    assert client.post("/api/auth/logout").status_code in (200, 204)

    login = client.post(
        "/api/auth/login",
        json={
            "email": "administrator@example.com",
            "password": "administrator-password",
        },
    )
    assert login.status_code == 200

    response = override(client, encounter, final_decision="High")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_an_unauthenticated_request_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/clinical/encounters/1/override",
        json={
            "assessment_id": 1,
            "final_decision": "High",
            "reason": "clinical gestalt",
        },
    )

    assert response.status_code == 401
