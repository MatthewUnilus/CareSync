"""End-to-end: the clinical journey the UI performs, in one narrative.

Register → intake → Queue → Override → Re-assessment → Departure, then the
Administrator's view of the same records. Each step drives the HTTP API in
the order the client drives it (the client reads the fixed Override reasons
before offering the form, polls the Queue between actions, and signs in as
the Administrator only afterwards, because the session cookie holds one
user at a time). A failure anywhere breaks the chain, which is the point:
this is the flow a triage nurse performs on a live shift.
"""

from typing import Any

from fastapi.testclient import TestClient

from conftest import HIGH_AGE, HIGH_INTAKE, MEDIUM_AGE, MEDIUM_INTAKE

ADMIN_AUTH = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}


def register_patient(client: TestClient, full_name: str, age: int) -> int:
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


def open_encounter(
    client: TestClient, patient_id: int, intake: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient_id, "intake": intake},
    )
    assert response.status_code == 201, response.text
    return response.json()


def clinical_queue(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/clinical/queue")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def entry_for(entries: list[dict[str, Any]], encounter_id: int) -> dict[str, Any]:
    return next(e for e in entries if e["encounter_id"] == encounter_id)


def test_register_intake_override_reassess_depart_then_administrator_reads(
    clinical_client: TestClient,
) -> None:
    client = clinical_client

    # The client loads the fixed reason set before it can offer the Override
    # form; the reasons it will send below must come from this read.
    reasons_response = client.get("/api/clinical/override-reasons")
    assert reasons_response.status_code == 200, reasons_response.text
    assert "clinical gestalt" in reasons_response.json()["reasons"]

    # Two patients, two encounters: one takes the full journey, one stays
    # awaiting so the boards never empty out mid-test.
    journey_id = open_encounter(
        client,
        register_patient(client, "Journey Patient", age=HIGH_AGE),
        HIGH_INTAKE,
    )["id"]
    staying_id = open_encounter(
        client,
        register_patient(client, "Staying Patient", age=MEDIUM_AGE),
        MEDIUM_INTAKE,
    )["id"]

    entries = clinical_queue(client)
    assert {e["encounter_id"] for e in entries} >= {journey_id, staying_id}
    journey = entry_for(entries, journey_id)
    staying = entry_for(entries, staying_id)
    assert journey["assessment"]["final_decision"] == (
        journey["assessment"]["machine_recommendation"]
    )
    assert not journey["override_flag"]

    # Override: the human disagrees with the engine on the journey encounter.
    override_response = client.post(
        f"/api/clinical/encounters/{journey_id}/override",
        json={
            "assessment_id": journey["assessment"]["id"],
            "final_decision": "Medium",
            "reason": "clinical gestalt",
            "free_text": None,
        },
    )
    assert override_response.status_code == 200, override_response.text
    overridden = override_response.json()["assessment"]
    assert overridden["final_decision"] == "Medium"
    assert overridden["machine_recommendation"] == (
        journey["assessment"]["machine_recommendation"]
    )

    entries = clinical_queue(client)
    journey = entry_for(entries, journey_id)
    assert journey["urgency_level"] == "Medium"
    assert journey["override_flag"]

    # Re-assessment: the patient deteriorates; a new Assessment is appended
    # and becomes the one that governs. It carries no Override, so the flags
    # clear even though the earlier Override stays on record.
    reassess_response = client.post(
        f"/api/clinical/encounters/{journey_id}/reassessment",
        json=HIGH_INTAKE,
    )
    # A new resource is appended, so the API answers 201 Created.
    assert reassess_response.status_code == 201, reassess_response.text
    reassessed = reassess_response.json()["assessment"]
    assert reassessed["id"] != journey["assessment"]["id"]
    assert reassessed["final_decision"] == (
        reassessed["machine_recommendation"]
    )
    assert reassessed["override"] is None

    entries = clinical_queue(client)
    journey = entry_for(entries, journey_id)
    assert journey["assessment"]["id"] == reassessed["id"]
    assert journey["urgency_level"] == reassessed["final_decision"]
    assert not journey["override_flag"]

    # Departure: the staying encounter leaves the awaiting board, and its
    # record stays readable.
    depart_response = client.post(
        f"/api/clinical/encounters/{staying_id}/departure"
    )
    assert depart_response.status_code == 200, depart_response.text
    assert staying_id not in {e["encounter_id"] for e in clinical_queue(client)}
    record_response = client.get(f"/api/clinical/encounters/{staying_id}")
    assert record_response.status_code == 200, record_response.text
    assert record_response.json()["id"] == staying_id

    # The Administrator reads the same records through the read-only side.
    # One session cookie, so this sign-in replaces the Clinical one; every
    # Clinical step above has already happened.
    admin_login = client.post("/api/auth/login", json=ADMIN_AUTH)
    assert admin_login.status_code == 200, admin_login.text

    admin_queue_response = client.get("/api/administrator/queue")
    assert admin_queue_response.status_code == 200, admin_queue_response.text
    admin_ids = [
        e["encounter_id"] for e in admin_queue_response.json()["entries"]
    ]
    assert journey_id in admin_ids
    assert staying_id not in admin_ids

    daily = client.get("/api/administrator/reports/daily-queue")
    assert daily.status_code == 200, daily.text
    daily_body = daily.json()
    assert daily_body["volume"] == 2
    assert daily_body["throughput"] == 1
    assert daily_body["awaiting"] == 1

    distribution = client.get("/api/administrator/reports/priority-distribution")
    assert distribution.status_code == 200, distribution.text
    dist_body = distribution.json()
    assert dist_body["total"] == 2
    assert sum(level["encounters"] for level in dist_body["levels"]) == 2
    by_level = {level["urgency_level"]: level["encounters"] for level in dist_body["levels"]}
    final_levels = {
        journey_id: reassessed["final_decision"],
        staying_id: "Medium",  # never overridden
    }
    assert by_level.get("High", 0) == sum(
        1 for level in final_levels.values() if level == "High"
    )
    assert by_level.get("Medium", 0) == sum(
        1 for level in final_levels.values() if level == "Medium"
    )

    performance = client.get("/api/administrator/reports/performance")
    assert performance.status_code == 200, performance.text
    perf_body = performance.json()
    assert perf_body["completed"] == 1
    assert [e["encounter_id"] for e in perf_body["entries"]] == [staying_id]
    assert perf_body["entries"][0]["waiting_seconds"] >= 0
    assert perf_body["entries"][0]["processing_seconds"] >= 0

    accuracy = client.get("/api/administrator/reports/accuracy-evaluation")
    assert accuracy.status_code == 200, accuracy.text
    assert accuracy.json()["overrides"]["assessments"] >= 3
