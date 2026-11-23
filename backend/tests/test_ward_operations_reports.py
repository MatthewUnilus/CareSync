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


def test_administrator_is_refused_every_clinical_ward_route(
    client: TestClient,
) -> None:
    """An administrator cannot perform a clinical ward action."""
    login(client, ADMINISTRATOR)
    refused = [
        ("POST", "/api/ward/admissions", {"patient_id": 1, "ward": "A", "bed": "1"}),
        ("GET", "/api/ward/board", None),
        ("GET", "/api/ward/note-templates", None),
        ("GET", "/api/ward/staff", None),
        ("POST", "/api/ward/admissions/1/tasks", {"description": "x"}),
    ]
    for method, path, body in refused:
        response = client.request(method, path, json=body)
        assert response.status_code == 403, f"{method} {path} was not refused"
