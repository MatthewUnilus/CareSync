"""Study instrumentation (ticket 40).

The system can time a study participant on a set task, behind a setting that is
off in normal ward use. The instrumentation measures the system, never the
nurse: it records an anonymised participant identifier and a task label, and it
never joins to a Patient. These tests drive the HTTP seam only.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

CLINICAL_EMAIL = "clinical@example.com"
CLINICAL_PASSWORD = "clinical-password"


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": CLINICAL_EMAIL, "password": CLINICAL_PASSWORD},
    )
    assert response.status_code == 200


@pytest.fixture
def instrumented_client(db_path: Path) -> Iterator[TestClient]:
    """A client with study instrumentation switched on."""
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        seed_demo_users=True,
        study_instrumentation_enabled=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def uninstrumented_client(db_path: Path) -> Iterator[TestClient]:
    """A client with the instrumentation left off, as normal ward use is."""
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        seed_demo_users=True,
        study_instrumentation_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_instrumentation_off_records_nothing(client: TestClient) -> None:
    """With the setting off, every study route is refused and no run exists."""
    _login(client)

    start = client.post(
        "/api/clinical/study-task-runs",
        json={"task_label": "handover_sheet", "participant_id": "P01"},
    )
    assert start.status_code == 403

    listing = client.get("/api/clinical/study-task-runs")
    assert listing.status_code == 403


def test_a_run_records_a_start_and_an_end(
    instrumented_client: TestClient,
) -> None:
    """On, a run records its start and end instants."""
    _login(instrumented_client)

    start = instrumented_client.post(
        "/api/clinical/study-task-runs",
        json={"task_label": "handover_sheet", "participant_id": "P01"},
    )
    assert start.status_code == 201
    run = start.json()
    assert run["task_label"] == "handover_sheet"
    assert run["participant_id"] == "P01"
    assert run["status"] == "running"
    assert run["ended_at"] is None

    end = instrumented_client.patch(
        f"/api/clinical/study-task-runs/{run['id']}/end",
        json={"participant_id": "P01"},
    )
    assert end.status_code == 200
    ended = end.json()
    assert ended["ended_at"] is not None
    assert ended["status"] == "completed"

    listing = instrumented_client.get("/api/clinical/study-task-runs")
    assert listing.status_code == 200
    assert len(listing.json()["runs"]) == 1


def test_abandoning_a_run_is_recorded_as_abandoned(
    instrumented_client: TestClient,
) -> None:
    """An abandoned run is marked abandoned, not left as a very long run."""
    _login(instrumented_client)

    start = instrumented_client.post(
        "/api/clinical/study-task-runs",
        json={"task_label": "medication_round", "participant_id": "P02"},
    )
    run_id = start.json()["id"]

    abandon = instrumented_client.patch(
        f"/api/clinical/study-task-runs/{run_id}/abandon",
        json={"participant_id": "P02"},
    )
    assert abandon.status_code == 200
    abandoned = abandon.json()
    assert abandoned["status"] == "abandoned"
    assert abandoned["ended_at"] is not None


def test_no_participant_identity_reaches_the_table(
    instrumented_client: TestClient,
) -> None:
    """The stored run carries a study identifier and no nurse identity."""
    _login(instrumented_client)

    start = instrumented_client.post(
        "/api/clinical/study-task-runs",
        json={"task_label": "ward_worklist", "participant_id": "P03"},
    )
    assert start.status_code == 201
    run = start.json()

    # The response carries only a study identifier; there is no user id, email
    # or display name field on the run at all.
    assert set(run.keys()) == {
        "id",
        "task_label",
        "participant_id",
        "started_at",
        "ended_at",
        "status",
    }
    assert run["participant_id"] == "P03"
    assert CLINICAL_EMAIL not in str(run)


def test_a_run_cannot_be_ended_by_another_participant(
    instrumented_client: TestClient,
) -> None:
    """A mismatched participant id is refused, so a run is only ended by its own."""
    _login(instrumented_client)

    start = instrumented_client.post(
        "/api/clinical/study-task-runs",
        json={"task_label": "handover_sheet", "participant_id": "P04"},
    )
    run_id = start.json()["id"]

    end = instrumented_client.patch(
        f"/api/clinical/study-task-runs/{run_id}/end",
        json={"participant_id": "P99"},
    )
    assert end.status_code == 403
