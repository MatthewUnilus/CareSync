"""Ticket 35: medication administrations — the record of what happened to a dose.

These tests drive the API a client uses. A dose is recorded once per (order, due
time) as given, withheld, refused or unavailable; where it was not given a reason
explains the omission, and the free text is permitted only for ``other``. A slot
cannot be recorded twice, a dose with a past due time can still be recorded and is
marked late rather than refused, and a recorded slot leaves the due list and the
board's outstanding counts while the record stays readable through the grid and
the admission history. Recording writes exactly one Audit Entry in the same
transaction; a refused recording writes none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import administrations, medications, ward
from app.audit_actions import AuditAction
from app.models import (
    Admission,
    AuditEntry,
    MedicationAdministration,
    MedicationOrder,
    Patient,
)

CLINICAL_AUDIT_ACTOR = "Clinical Demo User"

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

BASE_ORDER: dict[str, str] = {
    "drug": "Amoxicillin",
    "dose": "500 mg",
    "route": "oral",
    "frequency": "once_daily",
    "instructed_by": "Dr Okafor",
}

#: The fixed reason vocabulary the contract names, and which keys require text.
EXPECTED_REASONS: dict[str, bool] = {
    "not_available": False,
    "patient_refused": False,
    "withheld": False,
    "patient_nil_by_mouth": False,
    "other": True,
}


def _iso(value: datetime) -> str:
    return value.isoformat()


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


def admit(
    client: TestClient,
    patient_id: int,
    ward: str = "Ward A",
    bed: str = "3",
) -> int:
    response = client.post(
        "/api/ward/admissions",
        json={
            "patient_id": patient_id,
            "ward": ward,
            "bed": bed,
            "encounter_id": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def write_order(
    client: TestClient, admission_id: int, **overrides: Any
) -> Any:
    payload: dict[str, Any] = {
        **BASE_ORDER,
        "start_at": _iso(datetime.now(UTC)),
    }
    payload.update(overrides)
    return client.post(
        f"/api/ward/admissions/{admission_id}/medication-orders",
        json=payload,
    )


def stop_order(client: TestClient, order_id: int) -> Any:
    return client.post(f"/api/ward/medication-orders/{order_id}/stop")


def discharge(client: TestClient, admission_id: int) -> Any:
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def record(
    client: TestClient,
    order_id: int,
    *,
    due_at: str,
    outcome: str = "given",
    reason_key: str | None = None,
    reason_text: str | None = None,
) -> Any:
    return client.post(
        f"/api/ward/medication-orders/{order_id}/administrations",
        json={
            "due_at": due_at,
            "outcome": outcome,
            "reason_key": reason_key,
            "reason_text": reason_text,
        },
    )


def reasons(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/medication-administration-reasons")
    assert response.status_code == 200, response.text
    return response.json()["reasons"]


def grid(
    client: TestClient, order_id: int, start: str, end: str
) -> Any:
    return client.get(
        f"/api/ward/medication-orders/{order_id}/administration-grid",
        params={"from": start, "to": end},
    )


def history(client: TestClient, admission_id: int, start: str, end: str) -> Any:
    return client.get(
        f"/api/ward/admissions/{admission_id}/medication-administrations",
        params={"from": start, "to": end},
    )


def due(client: TestClient, start: str, end: str) -> Any:
    return client.get(
        "/api/ward/medications/due", params={"from": start, "to": end}
    )


def board(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/board")
    assert response.status_code == 200, response.text
    return response.json()["admissions"]


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


def _due_times(slots: list[dict[str, Any]]) -> list[datetime]:
    return [datetime.fromisoformat(slot["due_at"]) for slot in slots]


def _row_counts(client: TestClient) -> dict[str, int]:
    session_factory = client.app.state.session_factory
    models = (
        Admission,
        AuditEntry,
        MedicationAdministration,
        MedicationOrder,
        Patient,
    )
    with session_factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model)
            )
            for model in models
        }


def _patch_now(
    monkeypatch: pytest.MonkeyPatch, instant: datetime
) -> datetime:
    """Fix the clocks so the state of a slot is deterministic.

    The board captures its clock in ``app.ward``, the due list and the counts in
    ``app.medications``, and the grid's slot states in ``app.administrations``;
    all bind ``utc_now`` at import, so all three are patched to the one instant.
    """
    monkeypatch.setattr(medications, "utc_now", lambda: instant)
    monkeypatch.setattr(ward, "utc_now", lambda: instant)
    monkeypatch.setattr(administrations, "utc_now", lambda: instant)
    return instant


# --------------------------------------------------------------------------- #
# The reason vocabulary
# --------------------------------------------------------------------------- #


def test_the_reason_vocabulary_is_served(
    clinical_client: TestClient,
) -> None:
    served = {reason["key"]: reason for reason in reasons(clinical_client)}

    assert set(served) == set(EXPECTED_REASONS)
    for key, requires_text in EXPECTED_REASONS.items():
        assert served[key]["requires_text"] is requires_text
        assert served[key]["label"]
        assert served[key]["label"] != key


def test_only_the_other_reason_requires_free_text(
    clinical_client: TestClient,
) -> None:
    requiring = {
        reason["key"]
        for reason in reasons(clinical_client)
        if reason["requires_text"]
    }

    assert requiring == {"other"}


# --------------------------------------------------------------------------- #
# Recording a dose
# --------------------------------------------------------------------------- #


def test_a_given_dose_is_recorded_and_reads_back(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["order_id"] == order_id
    assert body["admission_id"] == admission_id
    assert body["drug"] == "Amoxicillin"
    assert body["dose"] == "500 mg"
    assert body["route"] == "oral"
    assert datetime.fromisoformat(body["due_at"]) == datetime(
        2026, 11, 19, 8, 0, tzinfo=UTC
    )
    assert body["outcome"] == "given"
    assert body["reason"] is None
    assert datetime.fromisoformat(body["recorded_at"]).tzinfo is not None
    assert body["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert body["late"] is True  # 2026-11-19 is in the past at run time


def test_an_unknown_order_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = record(
        clinical_client,
        999_999,
        due_at="2026-11-19T08:00:00+00:00",
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Medication order not found"}


def test_a_slot_cannot_be_recorded_twice(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    first = record(
        clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
    )
    assert first.status_code == 201, first.text

    second = record(
        clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
    )

    assert second.status_code == 409, second.text
    assert second.json() == {"detail": "This dose slot has already been recorded"}
    # Refused, not merged: one row exists for the slot.
    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        count = session.scalar(
            select(func.count()).select_from(MedicationAdministration)
        )
    assert count == 1


def test_a_late_dose_is_accepted_and_marked_late(
    clinical_client: TestClient,
) -> None:
    """A dose given after its round time is recorded and marked late, not refused."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2020, 1, 1, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2020-01-02T08:00:00+00:00",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["outcome"] == "given"
    assert body["late"] is True
    assert datetime.fromisoformat(body["recorded_at"]) > datetime.fromisoformat(
        body["due_at"]
    )


def test_a_dose_not_yet_due_is_refused(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slot ahead of the clock has not happened: recording it would remove a
    dose from the due list and the board before it fell."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 7, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-20T08:00:00+00:00",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "This dose is not yet due and cannot be recorded"
    }
    # Nothing was recorded, so the slot is still outstanding on the board.
    assert _row_counts(clinical_client)["medication_administrations"] == 0
    (row,) = board(clinical_client)
    assert row["outstanding_medication_count"] == 3


def test_a_dose_at_the_clock_is_accepted(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary is strict: a slot exactly at the clock is due, not future."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 8, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-20T08:00:00+00:00",
    )

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "given"


def test_a_discharged_admission_refuses_a_new_record(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A discharged stay takes no new clinical record of this kind, matching the
    read rule that excludes it from the due list and the board."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert discharge(clinical_client, admission_id).status_code == 200

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
    )

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": (
            "A discharged Admission cannot take new Medication Administrations"
        )
    }
    assert _row_counts(clinical_client)["medication_administrations"] == 0


# --------------------------------------------------------------------------- #
# The reason rules
# --------------------------------------------------------------------------- #


def test_a_reason_is_required_when_the_outcome_is_not_given(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="withheld",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "A reason is required when the outcome is not given"
    }


def test_a_reason_is_refused_when_the_dose_was_given(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="given",
        reason_key="withheld",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "A reason is recorded only when the outcome is not given"
    }


def test_an_unknown_reason_key_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="refused",
        reason_key="because",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "Unknown medication administration reason"
    }


def test_free_text_is_required_for_other(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    missing = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="unavailable",
        reason_key="other",
    )
    assert missing.status_code == 422, missing.text
    assert missing.json() == {
        "detail": "Free text is required for the 'other' reason"
    }

    supplied = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="unavailable",
        reason_key="other",
        reason_text="Out of stock; pharmacy informed",
    )
    assert supplied.status_code == 201, supplied.text
    assert supplied.json()["reason"] == {
        "key": "other",
        "label": "Other",
        "text": "Out of stock; pharmacy informed",
    }
    assert supplied.json()["late"] is False


def test_free_text_is_refused_for_every_reason_but_other(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="refused",
        reason_key="patient_refused",
        reason_text="Said no",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "Free text is permitted only for the 'other' reason"
    }


def test_a_coded_reason_is_recorded_with_its_label(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="withheld",
        reason_key="patient_nil_by_mouth",
    )

    assert response.status_code == 201, response.text
    assert response.json()["reason"] == {
        "key": "patient_nil_by_mouth",
        "label": "Patient nil by mouth",
        "text": None,
    }
    # A dose that was not given is never late.
    assert response.json()["late"] is False


def test_only_a_given_dose_can_be_late(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``late`` is a given dose recorded after its round time; a dose that was not
    given is never late, whatever the clock."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="twice_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    given = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T08:00:00+00:00",
        outcome="given",
    ).json()
    withheld = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T20:00:00+00:00",
        outcome="withheld",
        reason_key="patient_nil_by_mouth",
    ).json()
    refused = record(
        clinical_client,
        order_id,
        due_at="2026-11-18T08:00:00+00:00",
        outcome="refused",
        reason_key="patient_refused",
    ).json()
    unavailable = record(
        clinical_client,
        order_id,
        due_at="2026-11-18T20:00:00+00:00",
        outcome="unavailable",
        reason_key="not_available",
    ).json()

    assert given["late"] is True
    assert withheld["late"] is False
    assert refused["late"] is False
    assert unavailable["late"] is False


# --------------------------------------------------------------------------- #
# The slot must be a real round time of the order
# --------------------------------------------------------------------------- #


def test_a_due_time_that_is_not_a_round_time_is_refused(
    clinical_client: TestClient,
) -> None:
    """A made-up slot cannot be recorded: the answer must match a real dose."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="twice_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-19T09:00:00+00:00",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "The due time is not a round time of this Medication Order"
    }


def test_a_due_time_before_the_order_started_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 9, 0, tzinfo=UTC)),
    ).json()["id"]

    response = record(
        clinical_client,
        order_id,
        due_at="2026-11-18T08:00:00+00:00",
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "The due time is not a round time of this Medication Order"
    }


# --------------------------------------------------------------------------- #
# A recorded slot leaves the due list and the board counts
# --------------------------------------------------------------------------- #


def test_a_recorded_slot_leaves_the_due_list_and_the_board_counts(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 7, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    # Before: the 18th and 19th are overdue, the 20th 08:00 is due now.
    (before_row,) = board(clinical_client)
    assert before_row["overdue_medication_count"] == 2
    assert before_row["due_medication_count"] == 1
    assert before_row["outstanding_medication_count"] == 3
    before_doses = due(
        clinical_client,
        "2026-11-18T00:00:00+00:00",
        "2026-11-21T00:00:00+00:00",
    ).json()["doses"]
    assert _due_times(before_doses) == [
        datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
    ]

    recorded = record(
        clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
    )
    assert recorded.status_code == 201, recorded.text

    # The recorded slot is gone from both, and the counts drop by one overdue.
    (after_row,) = board(clinical_client)
    assert after_row["overdue_medication_count"] == 1
    assert after_row["due_medication_count"] == 1
    assert after_row["outstanding_medication_count"] == 2
    after_doses = due(
        clinical_client,
        "2026-11-18T00:00:00+00:00",
        "2026-11-21T00:00:00+00:00",
    ).json()["doses"]
    assert _due_times(after_doses) == [
        datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
    ]


def test_a_recorded_due_now_slot_reduces_the_due_count(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 8, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 20, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    (before_row,) = board(clinical_client)
    assert before_row["due_medication_count"] == 1
    assert before_row["outstanding_medication_count"] == 1

    assert (
        record(
            clinical_client, order_id, due_at="2026-11-20T08:00:00+00:00"
        ).status_code
        == 201
    )

    (after_row,) = board(clinical_client)
    assert after_row["due_medication_count"] == 0
    assert after_row["outstanding_medication_count"] == 0


# --------------------------------------------------------------------------- #
# The grid
# --------------------------------------------------------------------------- #


def test_the_grid_shows_what_was_due_and_what_happened(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert (
        record(
            clinical_client,
            order_id,
            due_at="2026-11-19T08:00:00+00:00",
            outcome="withheld",
            reason_key="patient_nil_by_mouth",
        ).status_code
        == 201
    )

    response = grid(
        clinical_client,
        order_id,
        "2026-11-18T00:00:00+00:00",
        "2026-11-21T00:00:00+00:00",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order"]["id"] == order_id
    assert body["order"]["drug"] == "Amoxicillin"
    assert body["order"]["frequency"] == "once_daily"
    assert body["order"]["status"] == "active"
    slots = body["slots"]
    assert _due_times(slots) == [
        datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
    ]
    # The 18th was overdue and unrecorded; the 19th was withheld; the 20th is
    # unrecorded and past its round time (the clock is 09:30).
    assert slots[0]["state"] == "overdue"
    assert slots[0]["administration"] is None
    assert slots[1]["state"] == "withheld"
    assert slots[1]["administration"]["outcome"] == "withheld"
    assert slots[1]["administration"]["reason"]["key"] == "patient_nil_by_mouth"
    assert slots[2]["state"] == "overdue"


def test_the_grid_marks_a_future_slot_pending(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 7, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 20, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    response = grid(
        clinical_client,
        order_id,
        "2026-11-20T00:00:00+00:00",
        "2026-11-23T00:00:00+00:00",
    )

    states = {
        datetime.fromisoformat(slot["due_at"]): slot["state"]
        for slot in response.json()["slots"]
    }
    assert states[datetime(2026, 11, 20, 8, 0, tzinfo=UTC)] == "due"
    assert states[datetime(2026, 11, 21, 8, 0, tzinfo=UTC)] == "pending"
    assert states[datetime(2026, 11, 22, 8, 0, tzinfo=UTC)] == "pending"


def test_the_grid_window_must_advance_and_is_capped(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]

    invalid = grid(
        clinical_client,
        order_id,
        "2026-11-20T00:00:00+00:00",
        "2026-11-20T00:00:00+00:00",
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json() == {
        "detail": "The administration window must end after it starts"
    }

    too_wide = grid(
        clinical_client,
        order_id,
        "2026-11-01T00:00:00+00:00",
        "2026-12-10T00:00:00+00:00",
    )
    assert too_wide.status_code == 422, too_wide.text
    assert too_wide.json() == {
        "detail": "The administration window may not exceed 31 days"
    }


def test_the_grid_requires_both_bounds(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]

    response = clinical_client.get(
        f"/api/ward/medication-orders/{order_id}/administration-grid"
    )

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# The admission history
# --------------------------------------------------------------------------- #


def test_the_admission_history_reads_across_the_orders(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 21, 12, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    morning = write_order(
        clinical_client,
        admission_id,
        drug="Amoxicillin",
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    evening = write_order(
        clinical_client,
        admission_id,
        drug="Paracetamol",
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 20, 12, 0, tzinfo=UTC)),
    ).json()["id"]
    assert (
        record(
            clinical_client, morning, due_at="2026-11-19T08:00:00+00:00"
        ).status_code
        == 201
    )
    # The evening order first doses at 08:00 the day after its 12:00 start.
    assert (
        record(
            clinical_client,
            evening,
            due_at="2026-11-21T08:00:00+00:00",
            outcome="refused",
            reason_key="patient_refused",
        ).status_code
        == 201
    )

    response = history(
        clinical_client,
        admission_id,
        "2026-11-18T00:00:00+00:00",
        "2026-11-22T00:00:00+00:00",
    )

    assert response.status_code == 200, response.text
    slots = response.json()["slots"]
    # The morning order doses at 08:00 from the 18th; the evening order first
    # doses at 08:00 the day after its 12:00 start on the 20th. Both orders place
    # a slot at 21st 08:00, so the history carries one slot per order and time.
    assert _due_times(slots) == [
        datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 21, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 21, 8, 0, tzinfo=UTC),
    ]
    by_key = {
        (slot["order_id"], datetime.fromisoformat(slot["due_at"])): slot
        for slot in slots
    }
    recorded = by_key[(morning, datetime(2026, 11, 19, 8, 0, tzinfo=UTC))]
    assert recorded["drug"] == "Amoxicillin"
    assert recorded["state"] == "given"
    assert recorded["administration"]["actor"]["display_name"] == (
        CLINICAL_AUDIT_ACTOR
    )
    refused = by_key[(evening, datetime(2026, 11, 21, 8, 0, tzinfo=UTC))]
    assert refused["drug"] == "Paracetamol"
    assert refused["state"] == "refused"
    assert refused["administration"]["reason"]["key"] == "patient_refused"
    # A slot with nothing recorded reads against the clock.
    unrecorded = by_key[(morning, datetime(2026, 11, 20, 8, 0, tzinfo=UTC))]
    assert unrecorded["state"] == "overdue"
    assert unrecorded["administration"] is None


def test_the_admission_history_requires_a_known_admission(
    clinical_client: TestClient,
) -> None:
    response = history(
        clinical_client,
        999_999,
        "2026-11-01T00:00:00+00:00",
        "2026-11-02T00:00:00+00:00",
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


# --------------------------------------------------------------------------- #
# Reading writes nothing
# --------------------------------------------------------------------------- #


def test_reading_the_grid_and_history_adds_no_rows(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert (
        record(
            clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
        ).status_code
        == 201
    )
    before = _row_counts(clinical_client)

    for _ in range(3):
        assert (
            grid(
                clinical_client,
                order_id,
                "2026-11-18T00:00:00+00:00",
                "2026-11-21T00:00:00+00:00",
            ).status_code
            == 200
        )
        assert (
            history(
                clinical_client,
                admission_id,
                "2026-11-18T00:00:00+00:00",
                "2026-11-21T00:00:00+00:00",
            ).status_code
            == 200
        )

    assert _row_counts(clinical_client) == before


# --------------------------------------------------------------------------- #
# Append-only
# --------------------------------------------------------------------------- #


def test_a_recorded_administration_is_never_edited_in_place(
    clinical_client: TestClient,
) -> None:
    """Append-only (ADR 0001/0007, no database triggers)."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    administration_id = record(
        clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
    ).json()["id"]

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(MedicationAdministration, administration_id)
        assert stored is not None
        stored.outcome = "withheld"
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(MedicationAdministration, administration_id)
        assert stored is not None
        assert stored.outcome == "given"


# --------------------------------------------------------------------------- #
# The audit log and roles
# --------------------------------------------------------------------------- #


def test_recording_an_administration_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert (
        record(
            clinical_client, order_id, due_at="2026-11-19T08:00:00+00:00"
        ).status_code
        == 201
    )

    entries = [
        item
        for item in audit_log(clinical_client, admission_id=admission_id)
        if item["action"]
        == AuditAction.record_medication_administration.value
    ]
    assert len(entries) == 1
    (entry,) = entries
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Medication administration recorded"


def test_a_refused_administration_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]

    # A made-up slot and a bad reason are both refused before anything is staged.
    assert (
        record(
            clinical_client, order_id, due_at="2026-11-19T09:00:00+00:00"
        ).status_code
        == 422
    )
    assert (
        record(
            clinical_client,
            order_id,
            due_at="2026-11-19T08:00:00+00:00",
            outcome="withheld",
        ).status_code
        == 422
    )

    assert (
        AuditAction.record_medication_administration.value
        not in actions(audit_log(clinical_client, admission_id=admission_id))
    )
    # And nothing was recorded at all.
    assert _row_counts(clinical_client)["medication_administrations"] == 0


def test_an_administrator_is_refused_the_administration_routes(
    client: TestClient,
) -> None:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    reasons_refused = client.get("/api/ward/medication-administration-reasons")
    record_refused = client.post(
        "/api/ward/medication-orders/1/administrations",
        json={
            "due_at": "2026-11-19T08:00:00+00:00",
            "outcome": "given",
            "reason_key": None,
            "reason_text": None,
        },
    )
    grid_refused = client.get(
        "/api/ward/medication-orders/1/administration-grid",
        params={"from": "2026-11-01T00:00:00+00:00", "to": "2026-11-02T00:00:00+00:00"},
    )
    history_refused = client.get(
        "/api/ward/admissions/1/medication-administrations",
        params={"from": "2026-11-01T00:00:00+00:00", "to": "2026-11-02T00:00:00+00:00"},
    )

    for refused in (reasons_refused, record_refused, grid_refused, history_refused):
        assert refused.status_code == 403, refused.text
        assert refused.json() == {"detail": "Role not permitted"}


def test_the_administration_routes_require_authentication(
    client: TestClient,
) -> None:
    responses = [
        client.get("/api/ward/medication-administration-reasons"),
        client.post(
            "/api/ward/medication-orders/1/administrations",
            json={
                "due_at": "2026-11-19T08:00:00+00:00",
                "outcome": "given",
                "reason_key": None,
                "reason_text": None,
            },
        ),
        client.get(
            "/api/ward/medication-orders/1/administration-grid",
            params={
                "from": "2026-11-01T00:00:00+00:00",
                "to": "2026-11-02T00:00:00+00:00",
            },
        ),
        client.get(
            "/api/ward/admissions/1/medication-administrations",
            params={
                "from": "2026-11-01T00:00:00+00:00",
                "to": "2026-11-02T00:00:00+00:00",
            },
        ),
    ]

    for response in responses:
        assert response.status_code == 401, response.text
