"""Ticket 34: medication orders, round times and the derived due list.

These tests drive the API a client uses. A doctor's instruction is transcribed
once against an Admission; the order's clinical fields are frozen, so a dose
change is a stop and a new order and both stay in the record. A cross-patient
due list is derived at read time from the active orders and the round-time
convention and stored nowhere, and the board's medication counts come from the
same schedule. As-required medication, infusions and variable doses are refused
with a ``422`` rather than quietly approximated.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import medications, ward
from app.audit_actions import AuditAction
from app.models import (
    Admission,
    AuditEntry,
    MedicationOrder,
    Patient,
)

CLINICAL_AUDIT_ACTOR = "Clinical Demo User"

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

#: The four frequencies the ticket fixes, and the clock times each maps to.
EXPECTED_FREQUENCIES: dict[str, list[str]] = {
    "once_daily": ["08:00"],
    "twice_daily": ["08:00", "20:00"],
    "three_times_daily": ["08:00", "14:00", "20:00"],
    "four_times_daily": ["06:00", "12:00", "18:00", "22:00"],
}

BASE_ORDER: dict[str, str] = {
    "drug": "Amoxicillin",
    "dose": "500 mg",
    "route": "oral",
    "frequency": "once_daily",
    "instructed_by": "Dr Okafor",
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


def discharge(client: TestClient, admission_id: int) -> Any:
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def round_times(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/ward/medications/round-times")
    assert response.status_code == 200, response.text
    return response.json()


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


def orders(client: TestClient, admission_id: int) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/ward/admissions/{admission_id}/medication-orders"
    )
    assert response.status_code == 200, response.text
    return response.json()["orders"]


def stop_order(client: TestClient, order_id: int) -> Any:
    return client.post(f"/api/ward/medication-orders/{order_id}/stop")


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


def _due_times(doses: list[dict[str, Any]]) -> list[datetime]:
    """The due instants of a due-list response, parsed, so the ``Z``/``+00:00``
    spelling a serializer chooses is not what the assertion turns on."""
    return [datetime.fromisoformat(dose["due_at"]) for dose in doses]


def _row_counts(client: TestClient) -> dict[str, int]:
    session_factory = client.app.state.session_factory
    models = (Admission, AuditEntry, MedicationOrder, Patient)
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
    """Fix the clocks so overdue and due are deterministic.

    The board captures its clock in ``app.ward`` and the due list derives against
    the clock in ``app.medications``; both bind ``utc_now`` at import, so both are
    patched to the one instant.
    """
    monkeypatch.setattr(medications, "utc_now", lambda: instant)
    monkeypatch.setattr(ward, "utc_now", lambda: instant)
    return instant


# --------------------------------------------------------------------------- #
# The round-time convention
# --------------------------------------------------------------------------- #


def test_the_round_times_route_serves_the_four_frequencies(
    clinical_client: TestClient,
) -> None:
    body = round_times(clinical_client)

    served = {item["key"]: item for item in body["frequencies"]}
    assert set(served) == set(EXPECTED_FREQUENCIES)
    for key, times in EXPECTED_FREQUENCIES.items():
        assert served[key]["times"] == times
        assert served[key]["label"]
        assert served[key]["label"] != key


# --------------------------------------------------------------------------- #
# Transcribing an order
# --------------------------------------------------------------------------- #


def test_a_medication_order_is_transcribed_and_reads_back(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = write_order(clinical_client, admission_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["admission_id"] == admission_id
    assert body["drug"] == "Amoxicillin"
    assert body["dose"] == "500 mg"
    assert body["route"] == "oral"
    assert body["frequency"] == "once_daily"
    assert body["instructed_by"] == "Dr Okafor"
    assert body["status"] == "active"
    assert body["stopped_at"] is None

    (stored,) = orders(clinical_client, admission_id)
    assert stored["id"] == body["id"]


def test_an_order_requires_a_known_admission(
    clinical_client: TestClient,
) -> None:
    response = write_order(clinical_client, 999_999)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


def test_an_order_on_a_discharged_admission_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = write_order(clinical_client, admission_id)

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A discharged Admission cannot take new Medication Orders"
    }


def test_an_unknown_frequency_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = write_order(clinical_client, admission_id, frequency="hourly")

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "Unknown medication frequency"}


@pytest.mark.parametrize(
    ("frequency", "detail"),
    [
        ("prn", "As-required (PRN) medication is out of scope for the due list"),
        (
            "continuous_infusion",
            "Continuous infusions are out of scope for the due list",
        ),
        (
            "variable_dose",
            "Variable-dose medication is out of scope for the due list",
        ),
    ],
)
def test_the_awkward_frequencies_are_refused_explicitly(
    clinical_client: TestClient, frequency: str, detail: str
) -> None:
    """A due list that silently mishandled these would be worse than one that
    says it does not cover them, so the refusal names the case."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = write_order(clinical_client, admission_id, frequency=frequency)

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": detail}


def test_a_missing_field_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = clinical_client.post(
        f"/api/ward/admissions/{admission_id}/medication-orders",
        json={"drug": "Amoxicillin", "dose": "500 mg"},
    )

    assert response.status_code == 422, response.text


def test_orders_read_back_oldest_first(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    first = write_order(clinical_client, admission_id, drug="Amoxicillin").json()
    second = write_order(clinical_client, admission_id, drug="Paracetamol").json()

    rows = orders(clinical_client, admission_id)

    assert [row["id"] for row in rows] == [first["id"], second["id"]]


# --------------------------------------------------------------------------- #
# Stopping an order and the dose change
# --------------------------------------------------------------------------- #


def test_stopping_an_order_records_the_instant_and_stops_the_doses(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]

    response = stop_order(clinical_client, order_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "stopped"
    assert body["stopped_at"] is not None
    assert datetime.fromisoformat(body["stopped_at"]).tzinfo is not None

    (stored,) = orders(clinical_client, admission_id)
    assert stored["status"] == "stopped"


def test_stopping_an_unknown_order_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = stop_order(clinical_client, 999_999)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Medication order not found"}


def test_stopping_an_already_stopped_order_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]
    first = stop_order(clinical_client, order_id)
    assert first.status_code == 200, first.text
    first_instant = first.json()["stopped_at"]

    second = stop_order(clinical_client, order_id)

    assert second.status_code == 409, second.text
    assert second.json() == {
        "detail": "A stopped Medication Order cannot be stopped again"
    }
    (stored,) = orders(clinical_client, admission_id)
    assert stored["stopped_at"] == first_instant


def test_a_dose_change_is_a_stop_and_a_new_order(
    clinical_client: TestClient,
) -> None:
    """Both the stopped order and the order that replaced it stay in the record."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    first = write_order(
        clinical_client, admission_id, dose="500 mg"
    ).json()
    assert stop_order(clinical_client, first["id"]).status_code == 200
    second = write_order(
        clinical_client, admission_id, dose="1 g"
    ).json()

    rows = orders(clinical_client, admission_id)

    assert [row["id"] for row in rows] == [first["id"], second["id"]]
    kept, replaced = rows
    assert kept["status"] == "stopped"
    assert kept["dose"] == "500 mg"
    assert replaced["status"] == "active"
    assert replaced["dose"] == "1 g"


# --------------------------------------------------------------------------- #
# The derived due list
# --------------------------------------------------------------------------- #


def test_the_due_list_derives_doses_and_marks_overdue(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()

    response = due(
        clinical_client, "2026-11-19T00:00:00+00:00", "2026-11-21T00:00:00+00:00"
    )

    assert response.status_code == 200, response.text
    doses = response.json()["doses"]
    assert _due_times(doses) == [
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
    ]
    assert all(dose["overdue"] is True for dose in doses)
    assert {dose["order_id"] for dose in doses} == {order["id"]}
    assert {dose["admission_id"] for dose in doses} == {admission_id}
    assert all(dose["patient"]["id"] == patient_id for dose in doses)
    assert {dose["drug"] for dose in doses} == {"Amoxicillin"}
    assert {dose["dose"] for dose in doses} == {"500 mg"}
    assert {dose["route"] for dose in doses} == {"oral"}
    # The overdue boundary is the server's clock, not a client calculation.
    assert fixed == datetime(2026, 11, 20, 9, 30, tzinfo=UTC)


def test_a_future_dose_is_not_overdue(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )

    response = due(
        clinical_client, "2026-11-25T00:00:00+00:00", "2026-11-26T00:00:00+00:00"
    )

    doses = response.json()["doses"]
    assert _due_times(doses) == [datetime(2026, 11, 25, 8, 0, tzinfo=UTC)]
    assert doses[0]["overdue"] is False


def test_the_due_window_is_inclusive_from_and_exclusive_to(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )

    response = due(
        clinical_client, "2026-11-19T08:00:00+00:00", "2026-11-20T08:00:00+00:00"
    )

    doses = response.json()["doses"]
    # The dose on the ``from`` boundary is in; the one on the ``to`` boundary is out.
    assert _due_times(doses) == [datetime(2026, 11, 19, 8, 0, tzinfo=UTC)]


def test_the_due_list_is_sorted_by_due_time(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        frequency="twice_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )

    response = due(
        clinical_client, "2026-11-19T00:00:00+00:00", "2026-11-20T00:00:00+00:00"
    )

    due_times = _due_times(response.json()["doses"])
    assert due_times == [
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 20, 0, tzinfo=UTC),
    ]


def test_a_stopped_order_keeps_prior_doses_and_omits_later_ones(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop ends the schedule from that instant; it does not rewrite the past.

    The doses already due while the order was live stay in the list, and the
    doses from the stop onward do not appear.
    """
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert stop_order(clinical_client, order_id).status_code == 200

    response = due(
        clinical_client, "2026-11-19T00:00:00+00:00", "2026-11-22T00:00:00+00:00"
    )

    # 19th and 20th 08:00 were due before the 20th 09:30 stop; 21st 08:00 is after.
    assert _due_times(response.json()["doses"]) == [
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 20, 8, 0, tzinfo=UTC),
    ]


def test_stopping_at_a_slot_boundary_keeps_earlier_doses_only(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop instant is exclusive: a dose exactly at it is not produced."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 8, 0, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="twice_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    # Stopped at 08:00, exactly a round time.
    assert stop_order(clinical_client, order_id).status_code == 200

    response = due(
        clinical_client, "2026-11-19T00:00:00+00:00", "2026-11-21T00:00:00+00:00"
    )

    # 19th 08:00 and 20:00 are before the stop; the 20th 08:00 boundary and the
    # 20th 20:00 after it are not produced.
    assert _due_times(response.json()["doses"]) == [
        datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 19, 20, 0, tzinfo=UTC),
    ]


def test_the_due_list_includes_a_historical_stopped_orders_prior_doses(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A window wholly in the past, before the stop, still shows the doses."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert stop_order(clinical_client, order_id).status_code == 200

    response = due(
        clinical_client, "2026-11-12T00:00:00+00:00", "2026-11-14T00:00:00+00:00"
    )

    assert _due_times(response.json()["doses"]) == [
        datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
        datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
    ]


def test_a_discharged_admission_produces_no_due_doses(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )
    assert discharge(clinical_client, admission_id).status_code == 200

    response = due(
        clinical_client, "2026-11-19T00:00:00+00:00", "2026-11-21T00:00:00+00:00"
    )

    assert response.json()["doses"] == []


def test_the_due_window_has_a_strict_maximum_range(
    clinical_client: TestClient,
) -> None:
    response = due(
        clinical_client, "2026-11-01T00:00:00+00:00", "2026-11-10T00:00:00+00:00"
    )

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "The due-list window may not exceed 7 days"}


def test_the_due_window_must_advance(
    clinical_client: TestClient,
) -> None:
    response = due(
        clinical_client, "2026-11-10T00:00:00+00:00", "2026-11-10T00:00:00+00:00"
    )

    assert response.status_code == 422, response.text
    assert response.json() == {
        "detail": "The due-list window must end after it starts"
    }


def test_the_due_list_requires_both_bounds(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/ward/medications/due")

    assert response.status_code == 422, response.text


def test_reading_the_due_list_adds_no_rows(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The due list is derived at read time and stores nothing."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )
    before = _row_counts(clinical_client)

    for _ in range(3):
        assert (
            due(
                clinical_client,
                "2026-11-19T00:00:00+00:00",
                "2026-11-21T00:00:00+00:00",
            ).status_code
            == 200
        )

    assert _row_counts(clinical_client) == before


# --------------------------------------------------------------------------- #
# Frozen clinical fields
# --------------------------------------------------------------------------- #


def test_a_clinical_field_cannot_be_edited_after_it_is_written(
    clinical_client: TestClient,
) -> None:
    """Append-only clinical fields (ADR 0001/0011, no database triggers)."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(MedicationOrder, order_id)
        assert stored is not None
        stored.drug = "Something else"
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(MedicationOrder, order_id)
        assert stored is not None
        assert stored.drug == "Amoxicillin"


def test_a_stopped_order_cannot_be_reopened(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]
    assert stop_order(clinical_client, order_id).status_code == 200

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(MedicationOrder, order_id)
        assert stored is not None
        stored.stopped_at = None
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()


# --------------------------------------------------------------------------- #
# The board's medication counts
# --------------------------------------------------------------------------- #


def test_the_board_counts_doses_from_the_schedule(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overdue, due now and outstanding read the record, not a stub."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 7, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )

    (row,) = board(clinical_client)

    # 18th and 19th 08:00 are past; 20th 08:00 is within the due window of 07:30.
    assert row["overdue_medication_count"] == 2
    assert row["due_medication_count"] == 1
    assert row["outstanding_medication_count"] == 3


def test_the_board_orders_an_overdue_patient_before_an_idle_one(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    busy_patient = register_patient(clinical_client, "Ada Lovelace", 36)
    busy = admit(clinical_client, busy_patient, bed="9")
    write_order(
        clinical_client,
        busy,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    )
    idle_patient = register_patient(clinical_client, "Alan Turing", 40)
    idle = admit(clinical_client, idle_patient, bed="1")

    rows = board(clinical_client)

    # Bed order would put "1" first; outstanding medication work puts "9" first.
    assert [row["id"] for row in rows] == [busy, idle]


def test_the_board_counts_a_stopped_orders_prior_unrecorded_doses(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop ends the schedule; the doses due while it was live stay counted."""
    _patch_now(monkeypatch, datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(
        clinical_client,
        admission_id,
        start_at=_iso(datetime(2026, 11, 18, 0, 0, tzinfo=UTC)),
    ).json()["id"]
    assert stop_order(clinical_client, order_id).status_code == 200

    (row,) = board(clinical_client)

    # 18th, 19th and 20th 08:00 all fell before the 20th 09:30 stop, so they are
    # the prior unrecorded doses; the stop produces none further.
    assert row["overdue_medication_count"] == 3
    assert row["due_medication_count"] == 0
    assert row["outstanding_medication_count"] == 3


def test_the_board_counts_a_far_past_start_without_walking_every_day(
    clinical_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long-running order is counted in bounded time and correctly.

    The count is arithmetic over the span, not a walk of every day since the
    order started, so a start decades ago gives the same answer as a new one.
    """
    _patch_now(monkeypatch, datetime(2026, 11, 20, 7, 30, tzinfo=UTC))
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(
        clinical_client,
        admission_id,
        frequency="once_daily",
        start_at=_iso(datetime(2000, 1, 1, 0, 0, tzinfo=UTC)),
    )

    (row,) = board(clinical_client)

    # One dose a day from 2000-01-01; every one before the 2026-11-20 07:30 clock is
    # overdue, and the 2026-11-20 08:00 dose is the one in the due window.
    expected_overdue = (date(2026, 11, 20) - date(2000, 1, 1)).days
    assert row["overdue_medication_count"] == expected_overdue
    assert row["due_medication_count"] == 1
    assert row["outstanding_medication_count"] == expected_overdue + 1


# --------------------------------------------------------------------------- #
# The audit log and roles
# --------------------------------------------------------------------------- #


def test_recording_an_order_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_order(clinical_client, admission_id)

    (entry,) = [
        item
        for item in audit_log(clinical_client, admission_id=admission_id)
        if item["action"] == AuditAction.record_medication_order.value
    ]
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Medication order recorded"


def test_stopping_an_order_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    order_id = write_order(clinical_client, admission_id).json()["id"]
    assert stop_order(clinical_client, order_id).status_code == 200

    (entry,) = [
        item
        for item in audit_log(clinical_client, admission_id=admission_id)
        if item["action"] == AuditAction.stop_medication_order.value
    ]
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Medication order stopped"


def test_a_refused_order_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    refused = write_order(clinical_client, admission_id, frequency="prn")
    assert refused.status_code == 422, refused.text

    assert (
        AuditAction.record_medication_order.value
        not in actions(audit_log(clinical_client, admission_id=admission_id))
    )


def test_an_administrator_is_refused_the_medication_routes(
    client: TestClient,
) -> None:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    round_times_refused = client.get("/api/ward/medications/round-times")
    due_refused = client.get(
        "/api/ward/medications/due",
        params={"from": "2026-11-01T00:00:00+00:00", "to": "2026-11-02T00:00:00+00:00"},
    )

    assert round_times_refused.status_code == 403
    assert due_refused.status_code == 403
    assert round_times_refused.json() == {"detail": "Role not permitted"}
