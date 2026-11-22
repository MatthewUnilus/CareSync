"""Ticket 31: ward admission, discharge and the board, at the HTTP API seam.

These tests drive the API a client uses. A Patient is admitted, appears on the
board with the others, is moved, and is discharged at the end of the stay. The
board is the ward's working view: for each open stay, the Patient's latest
Observation and the counts of what the record shows is outstanding, ordered so
the work that is overdue comes first. Reading it changes nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import ward
from app.medications import MedicationCounts
from app.models import Admission, AuditEntry, Encounter, Observation, Patient

CLINICAL_CREDENTIALS = {
    "email": "clinical@example.com",
    "password": "clinical-password",
}

REASON = "Shortness of breath on exertion"


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
        json={"patient_id": patient_id, "intake": {"presenting_complaint": REASON}},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def readings(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pain_level": 4,
        "illness_duration_hours": 12,
        "temperature_c": 37.0,
        "heart_rate_bpm": 80,
        "respiratory_rate_bpm": 16,
        "blood_pressure": {"systolic": 120, "diastolic": 78},
        "oxygen_saturation_percent": 98,
        "notes": None,
    }
    data.update(overrides)
    return data


def chart_admission(client: TestClient, admission_id: int, **overrides: Any):
    return client.post(
        f"/api/clinical/admissions/{admission_id}/observations",
        json=readings(**overrides),
    )


def admit(
    client: TestClient,
    patient_id: int,
    ward_name: str = "Ward A",
    bed: str = "3",
    encounter_id: int | None = None,
):
    return client.post(
        "/api/ward/admissions",
        json={
            "patient_id": patient_id,
            "ward": ward_name,
            "bed": bed,
            "encounter_id": encounter_id,
        },
    )


def move(client: TestClient, admission_id: int, ward_name: str, bed: str):
    return client.post(
        f"/api/ward/admissions/{admission_id}/move",
        json={"ward": ward_name, "bed": bed},
    )


def discharge(client: TestClient, admission_id: int):
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def board(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/board")
    assert response.status_code == 200, response.text
    return response.json()["admissions"]


def history(client: TestClient, patient_id: int) -> list[dict[str, Any]]:
    response = client.get(
        "/api/ward/admissions", params={"patient_id": patient_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["admissions"]


def _row_counts(client: TestClient) -> dict[str, int]:
    session_factory = client.app.state.session_factory
    models = (Admission, AuditEntry, Observation, Patient, Encounter)
    with session_factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model)
            )
            for model in models
        }


def test_a_patient_is_admitted_directly_and_appears_on_the_board(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)

    response = admit(clinical_client, patient_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ward"] == "Ward A"
    assert body["bed"] == "3"
    assert body["status"] == "open"
    assert body["discharged_at"] is None
    assert body["encounter_id"] is None
    assert body["patient"]["id"] == patient_id

    rows = board(clinical_client)
    assert [row["id"] for row in rows] == [body["id"]]


def test_admitting_from_an_encounter_links_the_visit(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    response = admit(clinical_client, patient_id, encounter_id=encounter_id)

    assert response.status_code == 201, response.text
    assert response.json()["encounter_id"] == encounter_id


def test_admitting_requires_a_known_patient(
    clinical_client: TestClient,
) -> None:
    response = admit(clinical_client, 999_999)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Patient not found"}


def test_admitting_requires_a_known_encounter(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)

    response = admit(clinical_client, patient_id, encounter_id=999_999)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Encounter not found"}


def test_admitting_another_patients_encounter_is_refused(
    clinical_client: TestClient,
) -> None:
    """The visit and the stay must belong to the same Patient, or refuse."""
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_encounter = open_encounter(clinical_client, first)

    response = admit(clinical_client, second, encounter_id=first_encounter)

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Encounter belongs to another patient"}


def test_a_location_move_is_recorded_and_shows_on_the_board(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]

    response = move(clinical_client, admission_id, "Ward B", "12")

    assert response.status_code == 200, response.text
    assert response.json()["ward"] == "Ward B"
    assert response.json()["bed"] == "12"
    # The board always says where the Patient is.
    (row,) = board(clinical_client)
    assert (row["ward"], row["bed"]) == ("Ward B", "12")


def test_moving_a_discharged_admission_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]
    assert discharge(clinical_client, admission_id).status_code == 200

    response = move(clinical_client, admission_id, "Ward B", "1")

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "A discharged Admission cannot be moved"}


def test_discharging_leaves_the_board_and_keeps_the_history(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id, "Ward A", "5").json()["id"]

    response = discharge(clinical_client, admission_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "discharged"
    assert body["discharged_at"] is not None
    assert board(clinical_client) == []

    (kept,) = history(clinical_client, patient_id)
    assert kept["id"] == admission_id
    assert (kept["ward"], kept["bed"]) == ("Ward A", "5")


def test_discharging_a_discharged_admission_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]
    first = discharge(clinical_client, admission_id)
    assert first.status_code == 200, first.text
    first_instant = first.json()["discharged_at"]

    second = discharge(clinical_client, admission_id)

    assert second.status_code == 409, second.text
    assert second.json() == {
        "detail": (
            "An Admission that has already been discharged cannot be discharged "
            "again"
        )
    }
    # The one recorded discharge instant is not overwritten.
    (kept,) = history(clinical_client, patient_id)
    assert kept["discharged_at"] == first_instant


def test_an_unknown_admission_cannot_be_moved_or_discharged(
    clinical_client: TestClient,
) -> None:
    moved = move(clinical_client, 999_999, "Ward B", "1")
    discharged = discharge(clinical_client, 999_999)

    assert moved.status_code == 404
    assert discharged.status_code == 404
    assert moved.json() == {"detail": "Admission not found"}
    assert discharged.json() == {"detail": "Admission not found"}


def test_a_discharged_admission_keeps_its_charted_history(
    clinical_client: TestClient,
) -> None:
    """A discharged stay is closed, not deleted: its Observations remain."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]
    charted = chart_admission(clinical_client, admission_id).json()
    assert discharge(clinical_client, admission_id).status_code == 200

    response = clinical_client.get(
        f"/api/clinical/patients/{patient_id}/observations"
    )
    assert response.status_code == 200, response.text
    observations = response.json()["observations"]
    assert [item["id"] for item in observations] == [charted["id"]]
    assert observations[0]["admission_id"] == admission_id


def test_the_board_shows_the_patients_latest_observation(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id).json()["id"]
    first = chart_admission(clinical_client, admission_id, heart_rate_bpm=80).json()
    second = chart_admission(clinical_client, admission_id, heart_rate_bpm=96).json()

    (row,) = board(clinical_client)

    latest = row["latest_observation"]
    assert latest["id"] == second["id"]
    assert latest["heart_rate_bpm"] == 96
    # A board row renders the Observation exactly as the chart does.
    assert latest["previous"]["heart_rate_bpm"] == 80
    assert latest["admission_id"] == admission_id
    assert latest["abnormal_fields"] == []
    assert first["id"] != latest["id"]


def test_the_latest_observation_is_null_when_nothing_is_charted(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admit(clinical_client, patient_id)

    (row,) = board(clinical_client)

    assert row["latest_observation"] is None


def test_the_board_counts_return_zero_while_the_later_features_do_not_exist(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admit(clinical_client, patient_id)

    (row,) = board(clinical_client)

    assert row["outstanding_medication_count"] == 0
    assert row["overdue_medication_count"] == 0
    assert row["due_medication_count"] == 0
    assert row["open_task_count"] == 0
    assert row["unreviewed_result_count"] == 0


def test_the_board_orders_by_bed_when_the_work_is_equal(
    clinical_client: TestClient,
) -> None:
    for bed in ("3", "1", "2"):
        admit(clinical_client, register_patient(clinical_client, f"P{bed}"), "Ward A", bed)

    beds = [row["bed"] for row in board(clinical_client)]

    assert beds == ["1", "2", "3"]


def test_the_board_orders_outstanding_work_before_bed(
    clinical_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order seam: overdue, then due, then results, then tasks, then bed.

    The counts are stubbed to prove the board's ordering reads them in the
    documented priority rather than by bed alone. The medication figures come
    through the one ``medication_counts`` seam, so overdue and due are stubbed
    together there; results and tasks keep a function each. Bed "1" has no work
    and must still sit last.
    """
    for bed in ("1", "2", "3", "4", "5"):
        admit(clinical_client, register_patient(clinical_client, f"P{bed}"), "Ward A", bed)

    def stub_counts(session, admission, *, now=None):
        return MedicationCounts(
            overdue=1 if admission.bed == "2" else 0,
            due=1 if admission.bed == "3" else 0,
            outstanding=0,
        )

    monkeypatch.setattr(ward, "medication_counts", stub_counts)
    monkeypatch.setattr(
        ward,
        "unreviewed_result_count",
        lambda session, admission: 1 if admission.bed == "4" else 0,
    )
    monkeypatch.setattr(
        ward,
        "open_task_count",
        lambda session, admission: 1 if admission.bed == "5" else 0,
    )

    beds = [row["bed"] for row in board(clinical_client)]

    assert beds == ["2", "3", "4", "5", "1"]


def test_reading_the_board_adds_no_rows(
    clinical_client: TestClient,
) -> None:
    """The board recalculates on every read and stores nothing."""
    for bed in ("1", "2"):
        admit(clinical_client, register_patient(clinical_client, f"P{bed}"), "Ward A", bed)
    before = _row_counts(clinical_client)

    for _ in range(3):
        board(clinical_client)

    assert _row_counts(clinical_client) == before


def test_one_patients_admissions_include_discharged_stays(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    first = admit(clinical_client, patient_id, "Ward A", "1").json()["id"]
    second = admit(clinical_client, patient_id, "Ward B", "2").json()["id"]
    assert discharge(clinical_client, first).status_code == 200

    rows = history(clinical_client, patient_id)

    assert [row["id"] for row in rows] == [first, second]
    assert rows[0]["status"] == "discharged"
    assert rows[1]["status"] == "open"


def test_an_admissions_history_requires_a_known_patient(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get(
        "/api/ward/admissions", params={"patient_id": 999_999}
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Patient not found"}


def test_the_admissions_history_requires_a_patient_id(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/ward/admissions")

    assert response.status_code == 422, response.text
