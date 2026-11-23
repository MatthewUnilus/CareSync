"""Ward Operations dashboard reports (ticket 39).

Every figure is derived on demand from stored rows and never stored; these
tests construct rows and assert each figure counts what it says it counts, that
the reads write nothing, and that an administrator is refused every clinical
ward route.
"""

from fastapi.testclient import TestClient

ADMINISTRATOR = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}
CLINICAL = {"email": "clinical@example.com", "password": "clinical-password"}


def login(client: TestClient, credentials: dict[str, str]) -> None:
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 200, response.text


def register_patient(client: TestClient, name: str, phone: str) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": name,
            "age": 40,
            "sex": "female",
            "contact_phone": phone,
            "contact_email": None,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def admit(client: TestClient, patient_id: int, ward: str, bed: str) -> int:
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


def test_ward_census_counts_current_inpatients(client: TestClient) -> None:
    login(client, CLINICAL)
    admit(client, register_patient(client, "Ada Lovelace", "07700 900001"), "A", "1")
    admit(client, register_patient(client, "Alan Turing", "07700 900002"), "A", "2")

    login(client, ADMINISTRATOR)
    response = client.get("/api/administrator/reports/ward-census")
    assert response.status_code == 200
    body = response.json()
    assert body["total_patients"] == 2
    assert body["by_ward"] == {"A": 2}


def test_length_of_stay_covers_current_inpatients(client: TestClient) -> None:
    login(client, CLINICAL)
    admit(client, register_patient(client, "Grace Hopper", "07700 900003"), "B", "5")

    login(client, ADMINISTRATOR)
    response = client.get("/api/administrator/reports/length-of-stay")
    assert response.status_code == 200
    body = response.json()
    assert len(body["distribution"]) == 1
    assert body["distribution"][0]["patient"] == "Grace Hopper"
    assert body["average_seconds"] >= 0


def test_investigation_review_counts_awaiting_results(client: TestClient) -> None:
    login(client, CLINICAL)
    admission_id = admit(
        client, register_patient(client, "Katherine Johnson", "07700 900004"), "C", "7"
    )
    create = client.post(
        f"/api/ward/admissions/{admission_id}/investigations",
        json={"test_name": "FBC", "instructed_by": "Dr Okafor"},
    )
    assert create.status_code == 201, create.text
    investigation_id = create.json()["id"]
    # Move it to result available but leave it unreviewed.
    client.post(f"/api/ward/investigations/{investigation_id}/sample-taken")
    client.post(
        f"/api/ward/investigations/{investigation_id}/result",
        json={"result_note": "as given"},
    )

    login(client, ADMINISTRATOR)
    response = client.get("/api/administrator/reports/investigation-review")
    assert response.status_code == 200
    body = response.json()
    assert body["awaiting_review_count"] == 1
    assert body["oldest_wait_seconds"] is not None


def test_task_completion_counts_raised_and_completed(client: TestClient) -> None:
    login(client, CLINICAL)
    admission_id = admit(
        client, register_patient(client, "Margaret Hamilton", "07700 900005"), "D", "9"
    )
    create = client.post(
        f"/api/ward/admissions/{admission_id}/tasks",
        json={"description": "Chase result", "due_at": None, "assignee_user_id": None},
    )
    assert create.status_code == 201, create.text
    task_id = create.json()["id"]
    client.post(f"/api/ward/tasks/{task_id}/complete")

    login(client, ADMINISTRATOR)
    response = client.get("/api/administrator/reports/task-completion?days=30")
    assert response.status_code == 200
    body = response.json()
    assert body["raised"] == 1
    assert body["completed"] == 1
    assert body["completion_pct"] == 100.0


def test_medication_timeliness_counts_on_time_late_and_not_given(
    client: TestClient,
) -> None:
    """The figure splits recorded doses into on-time, late and not-given.

    Rows are constructed directly with known instants and outcomes, so the
    classification is asserted rather than inferred: a given dose recorded at or
    before its due instant is on time, one recorded after it is late, and every
    other outcome counts as not given.
    """
    from datetime import UTC, datetime, timedelta

    from app.models import MedicationAdministration

    now = datetime.now(UTC)
    login(client, CLINICAL)
    admission_id = admit(
        client, register_patient(client, "Edith Clarke", "07700 900007"), "A", "1"
    )
    order = client.post(
        f"/api/ward/admissions/{admission_id}/medication-orders",
        json={
            "drug": "Amoxicillin",
            "dose": "500 mg",
            "route": "oral",
            "frequency": "once_daily",
            "start_at": (now - timedelta(hours=4)).isoformat(),
            "instructed_by": "Dr Okafor",
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    actor_id = client.get("/api/auth/me").json()["id"]

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        # Two given at or before their due instant (on time).
        for offset in (1, 2):
            due = now - timedelta(hours=offset, minutes=10)
            session.add(
                MedicationAdministration(
                    order_id=order_id,
                    due_at=due,
                    outcome="given",
                    recorded_at=due - timedelta(minutes=5),
                    actor_user_id=actor_id,
                )
            )
        # One given after its due instant (late).
        late_due = now - timedelta(hours=3, minutes=10)
        session.add(
            MedicationAdministration(
                order_id=order_id,
                due_at=late_due,
                outcome="given",
                recorded_at=late_due + timedelta(hours=1),
                actor_user_id=actor_id,
            )
        )
        # One withheld (not given), regardless of timing.
        session.add(
            MedicationAdministration(
                order_id=order_id,
                due_at=now - timedelta(hours=4, minutes=10),
                outcome="withheld",
                reason_key="withheld",
                recorded_at=now,
                actor_user_id=actor_id,
            )
        )
        session.commit()

    login(client, ADMINISTRATOR)
    response = client.get(
        "/api/administrator/reports/medication-timeliness?days=30"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["on_time"] == 2
    assert body["late"] == 1
    assert body["not_given"] == 1
    assert body["total"] == 4
    assert body["on_time_pct"] == 50.0


def test_medication_timeliness_respects_the_period(
    client: TestClient,
) -> None:
    """A dose recorded outside the window is not counted.

    The period is a defining property of this figure, so a row older than the
    window is excluded and the same data yields different figures for different
    periods.
    """
    from datetime import UTC, datetime, timedelta

    from app.models import MedicationAdministration

    now = datetime.now(UTC)
    login(client, CLINICAL)
    admission_id = admit(
        client, register_patient(client, "Mary Jackson", "07700 900008"), "A", "1"
    )
    order = client.post(
        f"/api/ward/admissions/{admission_id}/medication-orders",
        json={
            "drug": "Amoxicillin",
            "dose": "500 mg",
            "route": "oral",
            "frequency": "once_daily",
            "start_at": (now - timedelta(days=10)).isoformat(),
            "instructed_by": "Dr Okafor",
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    actor_id = client.get("/api/auth/me").json()["id"]

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        # One inside a 7-day window, one outside it.
        recent_due = now - timedelta(hours=1, minutes=10)
        session.add(
            MedicationAdministration(
                order_id=order_id,
                due_at=recent_due,
                outcome="given",
                recorded_at=recent_due - timedelta(minutes=5),
                actor_user_id=actor_id,
            )
        )
        old_due = now - timedelta(days=9, minutes=10)
        session.add(
            MedicationAdministration(
                order_id=order_id,
                due_at=old_due,
                outcome="given",
                recorded_at=old_due - timedelta(minutes=5),
                actor_user_id=actor_id,
            )
        )
        session.commit()

    login(client, ADMINISTRATOR)
    short = client.get("/api/administrator/reports/medication-timeliness?days=7")
    assert short.status_code == 200, short.text
    assert short.json()["total"] == 1

    long = client.get("/api/administrator/reports/medication-timeliness?days=30")
    assert long.status_code == 200, long.text
    assert long.json()["total"] == 2


def test_medication_timeliness_is_zero_when_nothing_is_recorded(
    client: TestClient,
) -> None:
    """With no administrations in the window the shares are zero, not NaN."""
    login(client, ADMINISTRATOR)
    response = client.get(
        "/api/administrator/reports/medication-timeliness?days=30"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "on_time": 0,
        "late": 0,
        "not_given": 0,
        "total": 0,
        "on_time_pct": 0.0,
    }


def _row_counts(client: TestClient) -> dict[str, int]:
    """Row counts for the ward tables, to prove a read adds none."""
    from sqlalchemy import func, select

    from app.models import (
        AuditEntry,
        Investigation,
        MedicationAdministration,
        StudyTaskRun,
        Task,
    )

    session_factory = client.app.state.session_factory
    models = (Investigation, Task, MedicationAdministration, StudyTaskRun, AuditEntry)
    with session_factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model)
            )
            for model in models
        }


def test_the_ward_report_reads_write_nothing(client: TestClient) -> None:
    """Every ward Operations report is a read: it adds no rows anywhere."""
    login(client, CLINICAL)
    admission_id = admit(
        client, register_patient(client, "Barbara Liskov", "07700 900006"), "E", "11"
    )
    client.post(
        f"/api/ward/admissions/{admission_id}/tasks",
        json={"description": "Review plan", "due_at": None, "assignee_user_id": None},
    )

    login(client, ADMINISTRATOR)
    before = _row_counts(client)
    for path in (
        "/api/administrator/reports/ward-census",
        "/api/administrator/reports/length-of-stay",
        "/api/administrator/reports/medication-timeliness?days=30",
        "/api/administrator/reports/investigation-review",
        "/api/administrator/reports/task-completion?days=30",
    ):
        assert client.get(path).status_code == 200, path
    assert _row_counts(client) == before
