"""The day's visits, exercised at the HTTP API seam.

Every figure is derived on demand from stored rows — the arrival and departure
instants on the Encounter — so the tests set those instants explicitly and pass
the day the Report is asked about.

The Report is read-only: computing it takes no clinical action and writes
nothing.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from conftest import HIGH_INTAKE, LOW_INTAKE, MEDIUM_INTAKE
from app.models import Encounter

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
    departed_at: Any = _UNSET,
) -> None:
    """Write the stored instants the Report reads, so no test depends on a clock."""
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        encounter = session.get(Encounter, encounter_id)
        assert encounter is not None
        if arrived_at is not None:
            encounter.arrived_at = arrived_at
        if departed_at is not _UNSET:
            encounter.departed_at = departed_at
        session.commit()


def fetch_daily(client: TestClient, day: date | None = None) -> dict[str, Any]:
    url = "/api/administrator/reports/daily-visits"
    if day is not None:
        url = f"{url}?day={day.isoformat()}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_daily_visits_counts_the_days_volume_and_throughput(
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
