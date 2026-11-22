"""Ending a visit, at the HTTP API seam.

A Clinical user ends a visit with an explicit action; the end instant is written
at that moment and nothing else schedules it. The visit's condition is derived
from the one nullable ``ended_at`` column — open while it is null, ended once it
is set — so there is no second status column to drift out of step, and an ended
visit stays readable.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from conftest import VISIT_INTAKE
from app.departures import ALREADY_ENDED_DETAIL

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

CLINICAL_CREDENTIALS = {
    "email": "clinical@example.com",
    "password": "clinical-password",
}


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


def open_visit(client: TestClient, patient_id: int) -> dict[str, Any]:
    response = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient_id, "intake": VISIT_INTAKE},
    )
    assert response.status_code == 201, response.text
    return response.json()


def end(client: TestClient, encounter_id: int, **kwargs: Any):
    return client.post(f"/api/clinical/encounters/{encounter_id}/end", **kwargs)


def detail(client: TestClient, encounter_id: int) -> dict[str, Any]:
    response = client.get(f"/api/clinical/encounters/{encounter_id}")
    assert response.status_code == 200, response.text
    return response.json()


def login_as_administrator(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert response.status_code == 200, response.text


def audit_entries(client: TestClient, encounter_id: int) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/administrator/audit-log?encounter_id={encounter_id}"
    )
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_a_clinical_user_ends_an_open_visit(clinical_client: TestClient) -> None:
    encounter = open_visit(clinical_client, register_patient(clinical_client))
    assert encounter["status"] == "open"
    assert encounter["ended_at"] is None

    response = end(clinical_client, encounter["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == encounter["id"]
    assert body["status"] == "ended"
    ended_at = datetime.fromisoformat(body["ended_at"])
    assert ended_at.tzinfo is not None
    arrived_at = datetime.fromisoformat(body["arrived_at"])
    assert arrived_at <= ended_at <= datetime.now(timezone.utc) + timedelta(seconds=5)

    # The end is persisted, not just echoed.
    assert detail(clinical_client, encounter["id"])["status"] == "ended"
    assert detail(clinical_client, encounter["id"])["ended_at"] == body["ended_at"]


def test_the_caller_never_supplies_the_end_instant(
    clinical_client: TestClient,
) -> None:
    encounter = open_visit(clinical_client, register_patient(clinical_client))
    supplied = "2000-01-01T00:00:00+00:00"

    response = end(clinical_client, encounter["id"], json={"ended_at": supplied})

    assert response.status_code == 200, response.text
    recorded = datetime.fromisoformat(response.json()["ended_at"])
    assert recorded != datetime.fromisoformat(supplied)
    assert recorded > datetime.fromisoformat(encounter["arrived_at"])


def test_an_ended_visit_cannot_be_ended_again(
    clinical_client: TestClient,
) -> None:
    encounter = open_visit(clinical_client, register_patient(clinical_client))
    first = end(clinical_client, encounter["id"])
    assert first.status_code == 200
    first_instant = first.json()["ended_at"]

    second = end(clinical_client, encounter["id"])

    assert second.status_code == 409
    assert second.json() == {"detail": ALREADY_ENDED_DETAIL}
    # The one recorded end instant is not overwritten.
    assert detail(clinical_client, encounter["id"])["ended_at"] == first_instant


def test_an_unknown_visit_cannot_be_ended(clinical_client: TestClient) -> None:
    response = end(clinical_client, 999999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter not found"}


def test_reading_a_visit_never_ends_it(clinical_client: TestClient) -> None:
    """The system never closes a visit on its own initiative."""
    encounter = open_visit(clinical_client, register_patient(clinical_client))

    for _ in range(3):
        assert detail(clinical_client, encounter["id"])["status"] == "open"

    assert detail(clinical_client, encounter["id"])["ended_at"] is None


def test_ending_a_visit_writes_one_audit_entry(clinical_client: TestClient) -> None:
    encounter = open_visit(clinical_client, register_patient(clinical_client))

    assert end(clinical_client, encounter["id"]).status_code == 200

    login_as_administrator(clinical_client)
    entries = audit_entries(clinical_client, encounter["id"])

    # Opening wrote one entry, ending wrote exactly one more.
    assert [entry["action"] for entry in entries] == [
        "open_encounter",
        "end_encounter",
    ]
    end_entry = entries[-1]
    assert end_entry["encounter_id"] == encounter["id"]
    assert end_entry["action_label"] == "Encounter ended"


def test_the_two_conditions_are_open_and_ended(
    clinical_client: TestClient,
) -> None:
    encounter = open_visit(clinical_client, register_patient(clinical_client))

    assert detail(clinical_client, encounter["id"])["status"] == "open"

    assert end(clinical_client, encounter["id"]).status_code == 200

    ended = detail(clinical_client, encounter["id"])
    assert ended["status"] == "ended"
    assert ended["ended_at"] is not None
    # There is no in-treatment or left-without-being-seen condition.
    assert "in_treatment" not in ended
    assert "left_without_being_seen" not in ended


def test_an_ended_visit_counts_in_the_days_report(clinical_client: TestClient) -> None:
    """Ending a visit feeds the day's throughput, derived on read."""
    patient_id = register_patient(clinical_client)
    ended = open_visit(clinical_client, patient_id)
    open_visit(clinical_client, patient_id)
    assert end(clinical_client, ended["id"]).status_code == 200

    login_as_administrator(clinical_client)
    response = clinical_client.get("/api/administrator/reports/daily-visits")

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["volume"] == 2
    assert report["throughput"] == 1
    assert report["awaiting"] == 1


def test_an_administrator_is_refused_ending_a_visit(client: TestClient) -> None:
    assert client.post("/api/auth/login", json=CLINICAL_CREDENTIALS).status_code == 200
    encounter = open_visit(client, register_patient(client))
    assert client.post("/api/auth/logout").status_code in (200, 204)
    login_as_administrator(client)

    response = end(client, encounter["id"])

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}
    # The refused action left the visit open.
    assert client.post("/api/auth/login", json=CLINICAL_CREDENTIALS).status_code == 200
    assert detail(client, encounter["id"])["status"] == "open"


def test_an_unauthenticated_request_is_refused(client: TestClient) -> None:
    assert end(client, 1).status_code == 401
