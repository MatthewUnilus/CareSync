"""The three Activity Reports, exercised at the HTTP API seam.

Every figure is derived on demand from stored rows — arrival and departure
instants on the Encounter, and Triage Assessment rows — so the tests set those
instants explicitly and pass the day the Report is asked about. No test depends
on the wall clock: the one that exercises the default day freezes the server's
clock.

The Reports are read-only: computing one takes no clinical action and writes
nothing.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, update

from conftest import (
    HIGH_AGE,
    HIGH_INTAKE,
    LOW_AGE,
    LOW_INTAKE,
    MEDIUM_AGE,
    MEDIUM_INTAKE,
)
from app.models import Encounter, Override, Patient, TriageAssessment

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}


DAY = date(2026, 3, 10)

_UNSET = object()


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc
    )


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


def login(client: TestClient, credentials: dict[str, str]) -> None:
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 200, response.text


def login_as_administrator(client: TestClient) -> None:
    login(client, ADMINISTRATOR_CREDENTIALS)


def place_instants(
    client: TestClient,
    encounter_id: int,
    *,
    arrived_at: datetime | None = None,
    assessed_at: datetime | None = None,
    departed_at: Any = _UNSET,
) -> None:
    """Write the stored instants a Report reads.

    A departure instant is written directly so the test controls the clock;
    ``assessed_at`` is frozen by the model's append-only guard, so it is placed
    with a Core update, which is test setup rather than a supported edit.
    """
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        encounter = session.get(Encounter, encounter_id)
        assert encounter is not None
        if arrived_at is not None:
            encounter.arrived_at = arrived_at
        if departed_at is not _UNSET:
            encounter.departed_at = departed_at
        if assessed_at is not None:
            session.execute(
                update(TriageAssessment)
                .where(TriageAssessment.encounter_id == encounter_id)
                .values(assessed_at=assessed_at)
            )
        session.commit()


def append_assessment(
    client: TestClient,
    encounter_id: int,
    *,
    assessed_at: datetime,
    final_decision: str,
    machine_recommendation: str,
) -> int:
    """Append a second Assessment, as ticket 10's Re-assessment will.

    It copies the stored snapshot of the assessment it supersedes and is built
    here rather than through a route so this ticket stays independent of 10.
    """
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        previous = session.scalars(
            select(TriageAssessment)
            .where(TriageAssessment.encounter_id == encounter_id)
            .order_by(TriageAssessment.id)
        ).all()[-1]
        values = {
            attribute.key: getattr(previous, attribute.key)
            for attribute in sa_inspect(previous).mapper.column_attrs
            if attribute.key != "id"
        }
        values.update(
            assessed_at=assessed_at,
            final_decision=final_decision,
            machine_recommendation=machine_recommendation,
            supersedes_assessment_id=previous.id,
        )
        reassessment = TriageAssessment(**values)
        session.add(reassessment)
        session.commit()
        return reassessment.id


def fetch_daily(client: TestClient, day: date | None = None) -> dict[str, Any]:
    url = "/api/administrator/reports/daily-queue"
    if day is not None:
        url = f"{url}?day={day.isoformat()}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def fetch_priority(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/administrator/reports/priority-distribution")
    assert response.status_code == 200, response.text
    return response.json()


def fetch_performance(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/administrator/reports/performance")
    assert response.status_code == 200, response.text
    return response.json()


def counts_by_level(report: dict[str, Any]) -> dict[str, int]:
    return {
        level["urgency_level"]: level["encounters"] for level in report["levels"]
    }


def test_daily_queue_counts_the_days_volume_and_throughput(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    arrived_and_departed = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    arrived_late = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)
    departed_only = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    still_awaiting = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    place_instants(
        clinical_client,
        arrived_and_departed["id"],
        arrived_at=at(DAY, 8),
        departed_at=at(DAY, 9),
    )
    place_instants(
        clinical_client,
        arrived_late["id"],
        arrived_at=at(DAY, 23, 30),
        departed_at=at(DAY + timedelta(days=1), 1),
    )
    place_instants(
        clinical_client,
        departed_only["id"],
        arrived_at=at(DAY - timedelta(days=1), 8),
        departed_at=at(DAY, 10),
    )
    place_instants(
        clinical_client,
        still_awaiting["id"],
        arrived_at=at(DAY, 12),
        departed_at=None,
    )

    login_as_administrator(clinical_client)
    report = fetch_daily(clinical_client, DAY)

    assert report["day"] == "2026-03-10"
    # Volume is arrivals on the day; throughput is departures on the day. An
    # Encounter that arrived the day before can contribute throughput, and one
    # that arrives late can contribute volume without throughput.
    assert report["volume"] == 3
    assert report["throughput"] == 2
    assert report["awaiting"] == 1
    assert datetime.fromisoformat(report["starts_at"]) == at(DAY, 0)
    assert datetime.fromisoformat(report["ends_at"]) == at(
        DAY + timedelta(days=1), 0
    )


def test_the_days_boundary_is_half_open(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    at_midnight = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    just_before = open_encounter(clinical_client, patient_id, LOW_INTAKE)

    place_instants(
        clinical_client,
        at_midnight["id"],
        arrived_at=at(DAY, 0),
        departed_at=at(DAY, 0),
    )
    place_instants(
        clinical_client,
        just_before["id"],
        arrived_at=at(DAY - timedelta(days=1), 23, 59),
        departed_at=at(DAY - timedelta(days=1), 23, 59),
    )

    login_as_administrator(clinical_client)
    report = fetch_daily(clinical_client, DAY)

    # Midnight belongs to the day that starts; the instant before belongs to
    # the previous day.
    assert report["volume"] == 1
    assert report["throughput"] == 1


def test_daily_queue_defaults_to_the_servers_day(
    clinical_client: TestClient, monkeypatch
) -> None:
    from app.routers import administrator

    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY, 13),
        departed_at=None,
    )

    frozen_now = at(DAY, 15)
    monkeypatch.setattr(administrator, "utc_now", lambda: frozen_now)

    login_as_administrator(clinical_client)
    report = fetch_daily(clinical_client)

    assert report["day"] == "2026-03-10"
    assert report["volume"] == 1
    assert report["awaiting"] == 1


def test_priority_distribution_counts_one_governing_level_per_encounter(
    clinical_client: TestClient,
) -> None:
    low_first = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Ada Lovelace", LOW_AGE),
        LOW_INTAKE,
    )
    open_encounter(
        clinical_client,
        register_patient(clinical_client, "Alan Turing", HIGH_AGE),
        HIGH_INTAKE,
    )
    medium = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Grace Hopper", MEDIUM_AGE),
        MEDIUM_INTAKE,
    )
    reassessed = open_encounter(
        clinical_client,
        register_patient(clinical_client, "Katherine Johnson", LOW_AGE),
        LOW_INTAKE,
    )

    # A second Assessment governs the Encounter: its Final Decision is the one
    # counted, and the Encounter still counts once rather than twice.
    append_assessment(
        clinical_client,
        reassessed["id"],
        assessed_at=at(DAY, 8, 30),
        final_decision="High",
        machine_recommendation="Low",
    )
    # A departed Encounter is still part of the distribution.
    place_instants(
        clinical_client,
        medium["id"],
        arrived_at=at(DAY, 7),
        departed_at=at(DAY, 9),
    )

    login_as_administrator(clinical_client)
    report = fetch_priority(clinical_client)

    assert report["total"] == 4
    assert counts_by_level(report) == {"High": 2, "Medium": 1, "Low": 1}
    assert [level["urgency_level"] for level in report["levels"]] == [
        "High",
        "Medium",
        "Low",
    ]


def test_performance_averages_waiting_and_processing_for_departed_encounters(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    first = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    second = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    awaiting = open_encounter(clinical_client, patient_id, MEDIUM_INTAKE)

    place_instants(
        clinical_client,
        first["id"],
        arrived_at=at(DAY, 8),
        assessed_at=at(DAY, 8, 10),
        departed_at=at(DAY, 9, 10),
    )
    place_instants(
        clinical_client,
        second["id"],
        arrived_at=at(DAY, 9),
        assessed_at=at(DAY, 9, 5),
        departed_at=at(DAY, 9, 35),
    )
    place_instants(
        clinical_client,
        awaiting["id"],
        arrived_at=at(DAY, 10),
        assessed_at=at(DAY, 10, 5),
        departed_at=None,
    )

    login_as_administrator(clinical_client)
    report = fetch_performance(clinical_client)

    # Waiting is the whole Encounter, arrival to Departure; processing is the
    # part from the governing Assessment to Departure. Only departed
    # Encounters have a departure instant, so only they are summarised.
    assert report["completed"] == 2
    assert report["average_waiting_seconds"] == 3150
    assert report["average_processing_seconds"] == 2700
    assert [entry["encounter_id"] for entry in report["entries"]] == [
        first["id"],
        second["id"],
    ]
    assert report["entries"][0]["waiting_seconds"] == 4200
    assert report["entries"][0]["processing_seconds"] == 3600
    assert report["entries"][1]["waiting_seconds"] == 2100
    assert report["entries"][1]["processing_seconds"] == 1800


def test_performance_processing_starts_from_the_governing_assessment(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY, 8),
        assessed_at=at(DAY, 8, 10),
        departed_at=at(DAY, 9, 30),
    )
    append_assessment(
        clinical_client,
        encounter["id"],
        assessed_at=at(DAY, 9),
        final_decision="High",
        machine_recommendation="Low",
    )

    login_as_administrator(clinical_client)
    (entry,) = fetch_performance(clinical_client)["entries"]

    # Waiting is unaffected by re-assessment; processing restarts from the
    # Assessment that now governs.
    assert entry["waiting_seconds"] == 5400
    assert entry["processing_seconds"] == 1800


def test_performance_is_empty_without_a_departure(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    open_encounter(clinical_client, patient_id, HIGH_INTAKE)

    login_as_administrator(clinical_client)
    report = fetch_performance(clinical_client)

    assert report == {
        "completed": 0,
        "average_waiting_seconds": 0,
        "average_processing_seconds": 0,
        "entries": [],
    }


def test_reports_follow_a_change_to_the_records_and_revert_with_them(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, age=HIGH_AGE)
    encounter = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY, 8),
        assessed_at=at(DAY, 8, 10),
        departed_at=at(DAY, 9, 10),
    )

    login_as_administrator(clinical_client)
    baseline_daily = fetch_daily(clinical_client, DAY)
    baseline_priority = fetch_priority(clinical_client)
    baseline_performance = fetch_performance(clinical_client)
    assert baseline_daily["volume"] == 1
    assert baseline_daily["throughput"] == 1
    assert counts_by_level(baseline_priority) == {"High": 1, "Medium": 0, "Low": 0}
    assert baseline_performance["completed"] == 1

    # Change the stored records: the Encounter moves to another day and loses
    # its departure instant, and its Final Decision changes.
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY - timedelta(days=2), 8),
        departed_at=None,
    )
    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        assessment = session.get(TriageAssessment, encounter["assessment"]["id"])
        assert assessment is not None
        assessment.final_decision = "Low"
        session.commit()

    changed_daily = fetch_daily(clinical_client, DAY)
    changed_priority = fetch_priority(clinical_client)
    changed_performance = fetch_performance(clinical_client)

    assert changed_daily["volume"] == 0
    assert changed_daily["throughput"] == 0
    assert counts_by_level(changed_priority) == {"High": 0, "Medium": 0, "Low": 1}
    assert changed_performance["completed"] == 0

    # Revert the records: every figure returns to its earlier value.
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY, 8),
        departed_at=at(DAY, 9, 10),
    )
    with session_factory() as session:
        assessment = session.get(TriageAssessment, encounter["assessment"]["id"])
        assert assessment is not None
        assessment.final_decision = "High"
        session.commit()

    assert fetch_daily(clinical_client, DAY) == baseline_daily
    assert fetch_priority(clinical_client) == baseline_priority
    assert fetch_performance(clinical_client) == baseline_performance


def test_computing_a_report_writes_nothing(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    first = open_encounter(clinical_client, patient_id, HIGH_INTAKE)
    second = open_encounter(clinical_client, patient_id, LOW_INTAKE)
    place_instants(
        clinical_client,
        first["id"],
        arrived_at=at(DAY, 8),
        assessed_at=at(DAY, 8, 10),
        departed_at=at(DAY, 9, 10),
    )
    place_instants(
        clinical_client,
        second["id"],
        arrived_at=at(DAY, 10),
        departed_at=None,
    )

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        before = _stored_state(session)

    login_as_administrator(clinical_client)
    fetch_daily(clinical_client, DAY)
    fetch_priority(clinical_client)
    fetch_performance(clinical_client)

    with session_factory() as session:
        after = _stored_state(session)

    assert after == before


def _stored_state(session) -> dict[str, Any]:
    """The rows a Report reads, in a form that exposes any write."""
    encounters = session.scalars(select(Encounter).order_by(Encounter.id)).all()
    assessments = session.scalars(
        select(TriageAssessment).order_by(TriageAssessment.id)
    ).all()
    overrides = session.scalars(select(Override).order_by(Override.id)).all()
    patients = session.scalars(select(Patient).order_by(Patient.id)).all()
    return {
        "patients": [
            (patient.id, patient.full_name, patient.registered_at)
            for patient in patients
        ],
        "encounters": [
            (
                encounter.id,
                encounter.arrived_at,
                encounter.departed_at,
                encounter.presenting_complaint,
            )
            for encounter in encounters
        ],
        "assessments": [
            (
                assessment.id,
                assessment.assessed_at,
                assessment.machine_recommendation,
                assessment.final_decision,
            )
            for assessment in assessments
        ],
        "overrides": [
            (override.id, override.assessment_id, override.reason)
            for override in overrides
        ],
    }


def test_the_reports_are_administrator_only(clinical_client: TestClient) -> None:
    for path in (
        "/api/administrator/reports/daily-queue",
        "/api/administrator/reports/priority-distribution",
        "/api/administrator/reports/performance",
    ):
        response = clinical_client.get(path)

        assert response.status_code == 403
        assert response.json() == {"detail": "Role not permitted"}


def test_the_reports_require_authentication(client: TestClient) -> None:
    for path in (
        "/api/administrator/reports/daily-queue",
        "/api/administrator/reports/priority-distribution",
        "/api/administrator/reports/performance",
    ):
        response = client.get(path)

        assert response.status_code == 401
        assert response.json() == {"detail": "Not authenticated"}
