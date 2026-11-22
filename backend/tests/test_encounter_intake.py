"""Opening and correcting a visit's reason, at the API boundary.

A visit carries a reason, not vital signs: until the Observation chart lands
(ticket 30) a visit has nowhere to keep vitals, so the visit payload is
reason-only and vitals posted to it are refused with ``422`` rather than
silently dropped.
"""

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

REASON = "Crushing chest pain since this morning"

# One non-reason field at a time: every vital sign, plus notes, must be refused
# by a visit route until the Observation chart exists.
VITALS = [
    {"pain_level": 8},
    {"illness_duration_hours": 6},
    {"temperature_c": 37.2},
    {"heart_rate_bpm": 104},
    {"respiratory_rate_bpm": 20},
    {"blood_pressure": {"systolic": 148, "diastolic": 92}},
    {"oxygen_saturation_percent": 94},
    {"notes": "Diabetic, on metformin"},
]


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


def open_visit(client: TestClient, patient_id: int, **reason_overrides: Any):
    return client.post(
        "/api/clinical/encounters",
        json={
            "patient_id": patient_id,
            "intake": {"presenting_complaint": REASON, **reason_overrides},
        },
    )


def correct_reason(client: TestClient, encounter_id: int, **overrides: Any):
    return client.put(
        f"/api/clinical/encounters/{encounter_id}/intake",
        json={"presenting_complaint": REASON, **overrides},
    )


def test_clinical_user_opens_a_visit_with_a_reason(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)

    response = open_visit(clinical_client, patient_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["patient"]["id"] == patient_id
    assert body["patient"]["full_name"] == "Ada Lovelace"
    # The reason is kept on the visit; there is no intake/vitals block.
    assert body["reason_for_visit"] == REASON
    assert body["status"] == "open"


def test_a_patient_may_hold_many_visits(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)

    first = open_visit(clinical_client, patient_id)
    second = open_visit(
        clinical_client, patient_id, presenting_complaint="Follow-up review"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["patient"]["id"] == patient_id
    assert second.json()["patient"]["id"] == patient_id


@pytest.mark.parametrize("extra", VITALS)
def test_opening_a_visit_refuses_vitals(
    clinical_client: TestClient, extra: dict[str, Any]
) -> None:
    """Vitals posted to a visit are refused, not silently dropped."""
    patient_id = register_patient(clinical_client)

    response = open_visit(clinical_client, patient_id, **extra)

    assert response.status_code == 422


def test_a_visit_reason_is_required(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)

    assert open_visit(clinical_client, patient_id, presenting_complaint="   ").status_code == 422
    assert (
        clinical_client.post(
            "/api/clinical/encounters",
            json={"patient_id": patient_id, "intake": {}},
        ).status_code
        == 422
    )


def test_the_reason_for_a_visit_can_be_corrected(
    clinical_client: TestClient,
) -> None:
    """Nothing freezes the reason any more: the engine's inputs are gone."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_visit(clinical_client, patient_id).json()["id"]

    response = correct_reason(
        clinical_client, encounter_id, presenting_complaint="Chest tightness on exertion"
    )

    assert response.status_code == 200, response.text
    assert response.json()["reason_for_visit"] == "Chest tightness on exertion"
    fetched = clinical_client.get(f"/api/clinical/encounters/{encounter_id}")
    assert fetched.json()["reason_for_visit"] == "Chest tightness on exertion"


def test_correcting_a_visit_reason_leaves_arrived_at_untouched(
    clinical_client: TestClient,
) -> None:
    """The arrival instant is the server's, and a correction never re-stamps it.

    ``arrived_at`` anchors the visit: reports and histories order on it, and it
    is written once at creation. Correcting the reason edits the reason and
    nothing else, so the instant must come back unchanged and timezone-aware
    rather than being recomputed to the moment of the correction.
    """
    patient_id = register_patient(clinical_client)
    opened = open_visit(clinical_client, patient_id).json()
    arrived_at = opened["arrived_at"]
    # The server speaks an aware UTC instant, not a bare local timestamp.
    assert datetime.fromisoformat(arrived_at).tzinfo is not None

    corrected = correct_reason(
        clinical_client,
        encounter_id=opened["id"],
        presenting_complaint="Chest tightness on exertion",
    )

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["arrived_at"] == arrived_at
    fetched = clinical_client.get(f"/api/clinical/encounters/{opened['id']}")
    assert fetched.json()["arrived_at"] == arrived_at


def test_a_visit_reason_can_be_corrected_after_the_visit_ends(
    clinical_client: TestClient,
) -> None:
    """Nothing freezes the reason, not even the end of the visit (ticket 26).

    The old locked-intake rule is gone, so a correction after the end instant is
    an ordinary correction: it succeeds, it is attributed, and the visit stays
    ended. A correction is not a reopening.
    """
    patient_id = register_patient(clinical_client)
    encounter_id = open_visit(clinical_client, patient_id).json()["id"]
    ended = clinical_client.post(f"/api/clinical/encounters/{encounter_id}/end")
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "ended"

    corrected = correct_reason(
        clinical_client, encounter_id, presenting_complaint="Cause found: reflux"
    )

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["reason_for_visit"] == "Cause found: reflux"
    # The reason changes; the visit does not come back to life.
    assert corrected.json()["status"] == "ended"

    # The correction is attributable: an Administrator reads it back on the visit.
    login = clinical_client.post(
        "/api/auth/login", json=ADMINISTRATOR_CREDENTIALS
    )
    assert login.status_code == 200
    entries = clinical_client.get(
        "/api/administrator/audit-log", params={"encounter_id": encounter_id}
    ).json()["entries"]
    assert [entry["action"] for entry in entries] == [
        "open_encounter",
        "end_encounter",
        "correct_visit_reason",
    ]


@pytest.mark.parametrize("extra", VITALS)
def test_correcting_a_visit_reason_refuses_vitals(
    clinical_client: TestClient, extra: dict[str, Any]
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_visit(clinical_client, patient_id).json()["id"]

    response = correct_reason(clinical_client, encounter_id, **extra)

    assert response.status_code == 422
    # The stored reason is unchanged by the refused request.
    assert (
        clinical_client.get(f"/api/clinical/encounters/{encounter_id}").json()[
            "reason_for_visit"
        ]
        == REASON
    )


def test_a_visit_must_belong_to_a_known_patient(
    clinical_client: TestClient,
) -> None:
    response = open_visit(clinical_client, 999_999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_correcting_an_unknown_visit_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = correct_reason(clinical_client, 999999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter not found"}


def test_recent_visits_are_listed_newest_first(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    older = open_visit(clinical_client, patient_id).json()
    newer = open_visit(
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
    assert encounters[0]["reason_for_visit"] == "Shortness of breath"


def test_administrator_cannot_open_or_correct_a_visit(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    encounter_id = open_visit(client, register_patient(client)).json()["id"]

    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    opened = open_visit(client, 1)
    corrected = correct_reason(client, encounter_id)
    listed = client.get("/api/clinical/encounters")
    fetched = client.get(f"/api/clinical/encounters/{encounter_id}")

    for response in (opened, corrected, listed, fetched):
        assert response.status_code == 403
        assert response.json() == {"detail": "Role not permitted"}


def test_visit_routes_require_authentication(client: TestClient) -> None:
    assert open_visit(client, 1).status_code == 401
    assert correct_reason(client, 1).status_code == 401
    assert client.get("/api/clinical/encounters").status_code == 401
    assert client.get("/api/clinical/encounters/1").status_code == 401
