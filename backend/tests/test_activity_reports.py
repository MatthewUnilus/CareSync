"""The day's visits, exercised at the HTTP API seam.

Every figure is derived on demand from stored rows — the arrival and end
instants on the Encounter — so the tests set those instants explicitly and pass
the day the Report is asked about.

The Report is read-only: computing it takes no clinical action and writes
nothing.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from conftest import VISIT_INTAKE
from app.models import Encounter
from app.timeutils import utc_now

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

CLINICAL_CREDENTIALS = {
    "email": "clinical@example.com",
    "password": "clinical-password",
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
    ended_at: Any = _UNSET,
) -> None:
    """Write the stored instants the Report reads, so no test depends on a clock."""
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        encounter = session.get(Encounter, encounter_id)
        assert encounter is not None
        if arrived_at is not None:
            encounter.arrived_at = arrived_at
        if ended_at is not _UNSET:
            encounter.ended_at = ended_at
        session.commit()


def fetch_daily(client: TestClient, day: date | None = None) -> dict[str, Any]:
    url = "/api/administrator/reports/daily-visits"
    if day is not None:
        url = f"{url}?day={day.isoformat()}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def end_visit(client: TestClient, encounter_id: int) -> None:
    response = client.post(f"/api/clinical/encounters/{encounter_id}/end")
    assert response.status_code == 200, response.text


def test_daily_visits_counts_the_days_volume_and_throughput(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    arrived_and_ended = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    arrived_late = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    ended_only = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    still_awaiting = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    place_instants(
        clinical_client,
        arrived_and_ended["id"],
        arrived_at=at(DAY, 8),
        ended_at=at(DAY, 9),
    )
    place_instants(
        clinical_client,
        arrived_late["id"],
        arrived_at=at(DAY, 23, 30),
        ended_at=at(DAY + timedelta(days=1), 1),
    )
    place_instants(
        clinical_client,
        ended_only["id"],
        arrived_at=at(DAY - timedelta(days=1), 8),
        ended_at=at(DAY, 10),
    )
    place_instants(
        clinical_client,
        still_awaiting["id"],
        arrived_at=at(DAY, 12),
        ended_at=None,
    )

    login_as_administrator(clinical_client)
    report = fetch_daily(clinical_client, DAY)

    assert report["day"] == "2026-03-10"
    # Volume is arrivals on the day; throughput is ends on the day. An Encounter
    # that arrived the day before can contribute throughput, and one that
    # arrives late can contribute volume without throughput.
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
    at_midnight = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    just_before = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    place_instants(
        clinical_client,
        at_midnight["id"],
        arrived_at=at(DAY, 0),
        ended_at=at(DAY, 0),
    )
    place_instants(
        clinical_client,
        just_before["id"],
        arrived_at=at(DAY - timedelta(days=1), 23, 59),
        ended_at=at(DAY - timedelta(days=1), 23, 59),
    )

    login_as_administrator(clinical_client)
    report = fetch_daily(clinical_client, DAY)

    # Midnight belongs to the day that starts; the instant before belongs to
    # the previous day.
    assert report["volume"] == 1
    assert report["throughput"] == 1


def test_the_performance_report_covers_ended_visits(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    ended = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    open_visit = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    place_instants(
        clinical_client,
        ended["id"],
        arrived_at=at(DAY, 8),
        ended_at=at(DAY, 8, 30),
    )
    place_instants(
        clinical_client,
        open_visit["id"],
        arrived_at=at(DAY, 9),
        ended_at=None,
    )

    login_as_administrator(clinical_client)
    response = clinical_client.get("/api/administrator/reports/performance")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed"] == 1
    assert body["average_waiting_seconds"] == 1800.0
    assert [entry["encounter_id"] for entry in body["entries"]] == [ended["id"]]


def test_reading_the_reports_writes_nothing(clinical_client: TestClient) -> None:
    """A derived figure is never stored, so reading it adds no rows."""
    from sqlalchemy import func, select

    from app.models import AuditEntry, Patient

    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    place_instants(
        clinical_client,
        encounter["id"],
        arrived_at=at(DAY, 8),
        ended_at=at(DAY, 9),
    )

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(Patient))
        audit_before = session.scalar(select(func.count()).select_from(AuditEntry))

    login_as_administrator(clinical_client)
    fetch_daily(clinical_client, DAY)
    clinical_client.get("/api/administrator/reports/performance")
    clinical_client.get("/api/administrator/audit-log")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == before
        assert (
            session.scalar(select(func.count()).select_from(AuditEntry))
            == audit_before
        )


def test_ending_a_visit_moves_it_from_awaiting_to_throughput(
    clinical_client: TestClient,
) -> None:
    """Ending a visit through the API turns a day's arrival into throughput.

    The end instant is the server's clock at the action, so the visit arrives and
    ends on the same (server's) day; both figures are read for that day.
    """
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    today = utc_now().date()

    login_as_administrator(clinical_client)
    before = fetch_daily(clinical_client, today)
    assert (before["volume"], before["awaiting"], before["throughput"]) == (1, 1, 0)

    login(clinical_client, CLINICAL_CREDENTIALS)
    end_visit(clinical_client, encounter["id"])

    login_as_administrator(clinical_client)
    after = fetch_daily(clinical_client, today)
    assert (after["volume"], after["awaiting"], after["throughput"]) == (1, 0, 1)


def test_ending_a_visit_adds_it_to_the_performance_report(
    clinical_client: TestClient,
) -> None:
    """An ended visit enters the waiting-time report; an open one stays out."""
    patient_id = register_patient(clinical_client)
    ended = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    open_visit = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    login_as_administrator(clinical_client)
    assert (
        clinical_client.get("/api/administrator/reports/performance").json()[
            "completed"
        ]
        == 0
    )

    login(clinical_client, CLINICAL_CREDENTIALS)
    end_visit(clinical_client, ended["id"])

    login_as_administrator(clinical_client)
    body = clinical_client.get("/api/administrator/reports/performance").json()

    assert body["completed"] == 1
    assert [entry["encounter_id"] for entry in body["entries"]] == [ended["id"]]
    (entry,) = body["entries"]
    assert entry["ended_at"] is not None
    assert entry["waiting_seconds"] >= 0
    assert open_visit["id"] not in {
        item["encounter_id"] for item in body["entries"]
    }
