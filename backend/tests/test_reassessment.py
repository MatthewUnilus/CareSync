"""Re-assessment: a Clinical user asks for a fresh Triage Assessment.

These tests drive the HTTP API. A Re-assessment captures the Encounter's
current intake, runs the engine again, and appends a second (or later)
Assessment that records which one it superseded. The Queue is a sort on the
**most recent** Assessment's Final Decision, so the same read that showed the
old order must show the new one afterwards — and must keep showing it until
another explicit action moves it.
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import (
    HIGH_AGE,
    HIGH_INTAKE,
    LOW_AGE,
    LOW_INTAKE,
    MEDIUM_AGE,
    MEDIUM_INTAKE,
)
from app.departures import REASSESSMENT_DEPARTED_DETAIL
from app.models import Encounter, TriageAssessment
from app.overrides import NOT_GOVERNING_DETAIL

# The shipped interim classifier separates these three presentations. Age is one
# of its inputs and comes from the Patient, so a test that needs a particular
# level registers the Patient with the fixture's age.


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


def reassess(
    client: TestClient,
    encounter: dict[str, Any],
    intake: dict[str, Any],
):
    return client.post(
        f"/api/clinical/encounters/{encounter['id']}/reassessment",
        json=intake,
    )


def override(
    client: TestClient,
    encounter: dict[str, Any],
    assessment_id: int,
    **payload: Any,
):
    return client.post(
        f"/api/clinical/encounters/{encounter['id']}/override",
        json={
            "assessment_id": assessment_id,
            "final_decision": "Low",
            "reason": "clinical gestalt",
            **payload,
        },
    )


def detail(client: TestClient, encounter: dict[str, Any]) -> dict[str, Any]:
    response = client.get(f"/api/clinical/encounters/{encounter['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def queue_entries(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/clinical/queue")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_a_clinical_user_reassesses_an_awaiting_encounter(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    first_id = encounter["assessment"]["id"]

    response = reassess(clinical_client, encounter, HIGH_INTAKE)

    assert response.status_code == 201, response.text
    assessment = response.json()["assessment"]
    assert assessment["id"] != first_id
    assert assessment["machine_recommendation"] == "High"
    assert assessment["final_decision"] == "High"
    assert assessment["supersedes_assessment_id"] == first_id
    assert assessment["snapshot"] == {**HIGH_INTAKE, "age": LOW_AGE}
    # The Encounter now carries the condition the Re-assessment captured, so
    # the card's vitals agree with the Assessment that governs it.
    assert response.json()["intake"] == HIGH_INTAKE


def test_the_first_assessment_supersedes_nothing(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    assert encounter["assessment"]["supersedes_assessment_id"] is None


def test_each_reassessment_links_to_the_assessment_it_superseded(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    first_id = encounter["assessment"]["id"]

    second = reassess(clinical_client, encounter, MEDIUM_INTAKE)
    assert second.status_code == 201, second.text
    second_id = second.json()["assessment"]["id"]

    third = reassess(clinical_client, encounter, HIGH_INTAKE)
    assert third.status_code == 201, third.text
    third_id = third.json()["assessment"]["id"]

    history = detail(clinical_client, encounter)["assessments"]
    assert [assessment["id"] for assessment in history] == [
        first_id,
        second_id,
        third_id,
    ]
    assert [assessment["supersedes_assessment_id"] for assessment in history] == [
        None,
        first_id,
        second_id,
    ]


def test_earlier_assessments_remain_readable_with_their_overrides(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    first_id = encounter["assessment"]["id"]

    overridden = override(
        clinical_client,
        encounter,
        first_id,
        reason="vitals inconsistent with recommendation",
    )
    assert overridden.status_code == 200, overridden.text

    assert reassess(clinical_client, encounter, LOW_INTAKE).status_code == 201

    body = detail(clinical_client, encounter)
    first, latest = body["assessments"]
    assert first["id"] == first_id
    assert first["machine_recommendation"] == "High"
    assert first["final_decision"] == "Low"
    assert first["override"]["reason"] == "vitals inconsistent with recommendation"
    assert first["override"]["performed_by"]["display_name"] == "Clinical Demo User"
    assert latest["id"] != first_id
    assert latest["override"] is None
    # The summary Assessment is the governing one: the most recent.
    assert body["assessment"] == latest


def test_the_most_recent_assessment_governs_the_queue_position(
    clinical_client: TestClient,
) -> None:
    """Assessment A is Overridden to Low; a Re-assessment recommends High.

    The Encounter must sit where the *latest* decision puts it. The old
    Override stays on Assessment A and has no say in the order.
    """
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
    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        high["id"],
        medium["id"],
    ]

    first = high["assessment"]
    response = override(clinical_client, high, first["id"], final_decision="Low")
    assert response.status_code == 200, response.text
    assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == [
        medium["id"],
        high["id"],
    ]

    bumped = reassess(clinical_client, high, HIGH_INTAKE)
    assert bumped.status_code == 201, bumped.text
    latest = bumped.json()["assessment"]
    assert latest["machine_recommendation"] == "High"
    assert latest["final_decision"] == "High"

    entries = queue_entries(clinical_client)
    assert [entry["encounter_id"] for entry in entries] == [
        high["id"],
        medium["id"],
    ]
    governing = entries[0]
    assert governing["urgency_level"] == "High"
    assert governing["assessment"]["id"] == latest["id"]
    assert governing["assessment"]["machine_recommendation"] == "High"
    assert governing["assessment"]["final_decision"] == "High"
    # The latest decision equals the machine's, so no Override flag is shown
    # even though an earlier Assessment in the history was overridden.
    assert governing["override_flag"] is False

    history = detail(clinical_client, high)["assessments"]
    assert history[0]["final_decision"] == "Low"
    assert history[0]["override"]["reason"] == "clinical gestalt"


def test_an_override_on_a_superseded_assessment_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    superseded_id = encounter["assessment"]["id"]

    assert reassess(clinical_client, encounter, LOW_INTAKE).status_code == 201
    before = queue_entries(clinical_client)

    response = override(
        clinical_client, encounter, superseded_id, final_decision="High"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": NOT_GOVERNING_DETAIL}
    assert queue_entries(clinical_client) == before
    assert detail(clinical_client, encounter)["assessment"]["final_decision"] == "Low"


def test_a_departed_encounter_cannot_be_reassessed(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(Encounter, encounter["id"])
        assert stored is not None
        stored.departed_at = datetime.now(timezone.utc)
        session.commit()

    response = reassess(clinical_client, encounter, HIGH_INTAKE)

    assert response.status_code == 409
    assert response.json() == {"detail": REASSESSMENT_DEPARTED_DETAIL}

    body = detail(clinical_client, encounter)
    assert len(body["assessments"]) == 1
    assert body["assessment"]["machine_recommendation"] == "Medium"


def test_a_reassessment_validates_the_captured_inputs(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    response = reassess(clinical_client, encounter, {**HIGH_INTAKE, "pain_level": 0})

    assert response.status_code == 422
    body = detail(clinical_client, encounter)
    assert len(body["assessments"]) == 1
    assert body["intake"] == LOW_INTAKE


def test_an_unknown_encounter_cannot_be_reassessed(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.post(
        "/api/clinical/encounters/9999/reassessment",
        json=HIGH_INTAKE,
    )

    assert response.status_code == 404


def test_an_administrator_is_refused_a_reassessment(client: TestClient) -> None:
    clinical = client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    assert clinical.status_code == 200
    patient_id = register_patient(client, age=LOW_AGE)
    encounter = open_encounter(client, patient_id, LOW_INTAKE)
    assert client.post("/api/auth/logout").status_code in (200, 204)

    login = client.post(
        "/api/auth/login",
        json={
            "email": "administrator@example.com",
            "password": "administrator-password",
        },
    )
    assert login.status_code == 200

    response = reassess(client, encounter, HIGH_INTAKE)

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_an_unauthenticated_reassessment_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/clinical/encounters/1/reassessment",
        json=HIGH_INTAKE,
    )

    assert response.status_code == 401


def test_nothing_reorders_without_an_explicit_action(
    clinical_client: TestClient,
) -> None:
    """Reading the Queue is not an action: only Re-assessment or Override moves it."""
    low = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Ada Lovelace", LOW_AGE),
        LOW_INTAKE,
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

    expected = [high["id"], medium["id"], low["id"]]
    for _ in range(3):
        assert [entry["encounter_id"] for entry in queue_entries(clinical_client)] == (
            expected
        )

    # No Assessment was appended by any of those reads, and no Final Decision
    # moved on its own.
    for encounter in (low, high, medium):
        body = detail(clinical_client, encounter)
        assert len(body["assessments"]) == 1
        assert (
            body["assessment"]["final_decision"]
            == body["assessment"]["machine_recommendation"]
        )


def test_the_board_card_reflects_the_latest_assessment(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=LOW_AGE)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    (before,) = queue_entries(clinical_client)
    assert before["urgency_level"] == "Low"
    assert before["assessment"]["recognised_symptom_groups"] == ["headache"]

    assert reassess(clinical_client, encounter, HIGH_INTAKE).status_code == 201

    (after,) = queue_entries(clinical_client)
    assert after["encounter_id"] == encounter["id"]
    assert after["urgency_level"] == "High"
    assert after["assessment"]["machine_recommendation"] == "High"
    assert after["assessment"]["final_decision"] == "High"
    assert after["assessment"]["recognised_symptom_groups"] == ["chest pain"]
    assert after["intake"] == HIGH_INTAKE
    assert after["override_flag"] is False


@pytest.mark.parametrize("intake", [LOW_INTAKE, MEDIUM_INTAKE, HIGH_INTAKE])
def test_a_reassessment_always_records_a_fresh_machine_recommendation(
    clinical_client: TestClient,
    intake: dict[str, Any],
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    response = reassess(clinical_client, encounter, intake)

    assert response.status_code == 201, response.text
    assessment = response.json()["assessment"]
    assert assessment["final_decision"] == assessment["machine_recommendation"]
    assert assessment["snapshot"] == {**intake, "age": MEDIUM_AGE}


def test_the_superseded_assessment_stays_frozen(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=MEDIUM_AGE)
    encounter = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    first_id = encounter["assessment"]["id"]

    assert reassess(clinical_client, encounter, HIGH_INTAKE).status_code == 201

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(TriageAssessment, first_id)
        assert stored is not None
        assert stored.machine_recommendation == "Medium"
        assert stored.presenting_complaint == MEDIUM_INTAKE["presenting_complaint"]
        stored.pain_level = 10
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()
