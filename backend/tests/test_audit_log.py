"""The audit log: every clinical mutation leaves an attributable record.

These tests drive the HTTP API. Each of the surviving clinical mutations —
register a Patient, open an Encounter, correct the reason for a visit, end the
visit — appends exactly one entry naming who did it and what they did, and that
entry shares the transaction with the change it describes. The log is read back
through the Administrator-only route, so the tests observe it at the same seam
an Administrator does rather than reaching into the table except where the
transaction property itself is under test.
"""

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit import record_audit_entry
from app.audit_actions import (
    AUDIT_ACTION_LABELS,
    AuditAction,
    label_for,
)
from app.models import AuditEntry, Encounter, Patient, Sex, User
from app.patients import find_or_create_patient

from conftest import VISIT_INTAKE

CLINICAL_AUDIT_ACTOR = "Clinical Demo User"

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
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
    assert response.status_code in (200, 201), response.text
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


def correct_reason(
    client: TestClient,
    encounter_id: int,
    intake: dict[str, Any],
) -> Any:
    return client.put(
        f"/api/clinical/encounters/{encounter_id}/intake",
        json=intake,
    )


def end_visit(client: TestClient, encounter_id: int) -> Any:
    return client.post(f"/api/clinical/encounters/{encounter_id}/end")


def login_as_administrator(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert response.status_code == 200


def audit_log(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    """Read the log through the Administrator route, as an Administrator does."""
    login_as_administrator(client)
    response = client.get("/api/administrator/audit-log", params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def actions(entries: list[dict[str, Any]]) -> list[str]:
    return [entry["action"] for entry in entries]


def test_every_action_has_a_label() -> None:
    """The label table covers the enum exactly, so a new action cannot ship unlabelled.

    Adding an action to ``AuditAction`` without a label is the drift this ticket
    removes; the suite must fail rather than let the raw key reach the UI.
    """
    missing = [
        action for action in AuditAction if action not in AUDIT_ACTION_LABELS
    ]
    assert missing == []

    # And no label names an action that is not in the set, which would be a
    # stale row left behind by a renamed or deleted action.
    unknown = [key for key in AUDIT_ACTION_LABELS if key not in AuditAction]
    assert unknown == []


def test_a_label_is_never_the_raw_key() -> None:
    """A label is the human read; the key must not leak through it."""
    for action in AuditAction:
        label = AUDIT_ACTION_LABELS[action]
        assert label and label != action.value
        assert "_" not in label


def test_label_for_falls_back_deliberately() -> None:
    """An unrecognised value gets a defined fallback, not the raw snake_case key.

    The fallback lives server-side beside the table so both the API and any
    future caller share one rule, rather than each inventing its own.
    """
    assert label_for(AuditAction.register_patient) == (
        AUDIT_ACTION_LABELS[AuditAction.register_patient]
    )
    fallback = label_for("something_not_in_the_set")
    assert fallback != "something_not_in_the_set"
    assert "_" not in fallback


def test_the_audit_log_serves_each_actions_label(
    clinical_client: TestClient,
) -> None:
    """Every entry carries its human label beside its machine key."""
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    assert correct_reason(
        clinical_client,
        encounter["id"],
        {**VISIT_INTAKE, "presenting_complaint": "Worsening headache"},
    ).status_code == 200
    assert end_visit(clinical_client, encounter["id"]).status_code == 200

    entries = audit_log(clinical_client)

    assert actions(entries) == [
        AuditAction.register_patient.value,
        AuditAction.open_encounter.value,
        AuditAction.correct_visit_reason.value,
        AuditAction.end_encounter.value,
    ]
    for entry in entries:
        expected = AUDIT_ACTION_LABELS[AuditAction(entry["action"])]
        assert entry["action_label"] == expected


def test_registering_a_patient_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    register_patient(clinical_client)

    (entry,) = audit_log(clinical_client)

    assert entry["action"] == AuditAction.register_patient.value
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert datetime.fromisoformat(entry["recorded_at"]).tzinfo is not None
    assert entry["patient_id"] is not None
    assert entry["encounter_id"] is None


def test_opening_an_encounter_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.open_encounter.value
    ]

    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] == encounter["id"]


def test_correcting_the_visit_reason_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    response = correct_reason(
        clinical_client,
        encounter["id"],
        {**VISIT_INTAKE, "presenting_complaint": "Reassessed: chest tightness"},
    )
    assert response.status_code == 200, response.text

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.correct_visit_reason.value
    ]
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] == encounter["id"]


def test_ending_a_visit_writes_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)

    response = end_visit(clinical_client, encounter["id"])
    assert response.status_code == 200, response.text

    (entry,) = [
        item
        for item in audit_log(clinical_client)
        if item["action"] == AuditAction.end_encounter.value
    ]
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] == encounter["id"]


def test_an_audit_entry_is_never_edited_in_place(
    clinical_client: TestClient,
) -> None:
    register_patient(clinical_client)
    (entry,) = audit_log(clinical_client)
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        stored = session.get(AuditEntry, entry["id"])
        assert stored is not None
        stored.action = AuditAction.open_encounter.value
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(AuditEntry, entry["id"])
        assert stored is not None
        assert stored.action == AuditAction.register_patient.value


def test_a_rolled_back_mutation_leaves_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    """The transaction property: a change and its record live or die together.

    A reason correction and its audit entry are staged in one session, then an
    unrelated constraint failure (a null reason) forces the transaction to fail
    before it commits. Neither the corrected reason nor the audit row may
    survive, which is what proves the two share a transaction rather than being
    written independently.
    """
    patient_id = register_patient(clinical_client)
    encounter = open_encounter(clinical_client, patient_id, VISIT_INTAKE)
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        stored = session.get(Encounter, encounter["id"])
        actor = session.scalar(select(User).where(User.role == "clinical"))
        assert stored is not None and actor is not None
        record_audit_entry(
            session,
            actor=actor,
            action=AuditAction.correct_visit_reason,
            patient=stored.patient,
            encounter=stored,
        )
        # Force the whole transaction to fail, as any error between a mutation
        # and its commit would. ``reason_for_visit`` is NOT NULL, so the flush
        # raises and nothing staged in this session can be committed.
        stored.reason_for_visit = None
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        check = session.get(Encounter, encounter["id"])
        assert check is not None
        assert check.reason_for_visit == VISIT_INTAKE["presenting_complaint"]
        # Registering the Patient and opening the Encounter each staged one
        # entry; the failed correction must have staged none.
        assert session.scalar(select(func.count()).select_from(AuditEntry)) == 2


def test_an_administrator_reads_the_log_and_a_clinical_user_is_refused(
    client: TestClient,
) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    assert login.status_code == 200
    register_patient(client)

    refused = client.get("/api/administrator/audit-log")
    assert refused.status_code == 403
    assert refused.json() == {"detail": "Role not permitted"}

    login_as_administrator(client)
    allowed = client.get("/api/administrator/audit-log")
    assert allowed.status_code == 200, allowed.text
    assert len(allowed.json()["entries"]) == 1


def test_the_log_filters_to_a_single_encounter(
    clinical_client: TestClient,
) -> None:
    first_patient = register_patient(clinical_client, "Ada Lovelace", 36)
    first = open_encounter(clinical_client, first_patient, VISIT_INTAKE)
    assert correct_reason(
        clinical_client,
        first["id"],
        {**VISIT_INTAKE, "presenting_complaint": "Headache worsening since morning"},
    ).status_code == 200

    second_patient = register_patient(clinical_client, "Alan Turing", 40)
    second = open_encounter(clinical_client, second_patient, VISIT_INTAKE)

    entries = audit_log(clinical_client, encounter_id=first["id"])

    assert actions(entries) == [
        AuditAction.open_encounter.value,
        AuditAction.correct_visit_reason.value,
    ]
    assert {entry["encounter_id"] for entry in entries} == {first["id"]}
    assert second["id"] not in {entry["encounter_id"] for entry in entries}


def test_registration_shares_the_route_transaction(
    clinical_client: TestClient,
) -> None:
    """The commit boundary was lifted: the route commits, not the lookup.

    If ``find_or_create_patient`` still committed internally, the Patient it
    created would be visible to a second session after this one closes without
    a commit. It must not be, because registration's audit entry and the
    Patient row have to share the route's single transaction.
    """
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        patient, created = find_or_create_patient(
            session,
            full_name="Grace Hopper",
            age=36,
            sex=Sex.female,
            contact_phone="07700 900456",
            contact_email=None,
        )
        assert created is True
        patient_id = patient.id
        # Deliberately no commit: closing the session rolls the work back.

    with session_factory() as session:
        assert session.get(Patient, patient_id) is None


def test_an_entry_names_the_actor_who_performed_the_mutation(
    clinical_client: TestClient,
) -> None:
    """The read responses carry the actor's name, not just an id.

    Reading the log through the Administrator route is the only way the tests
    observe the actor, so the name arriving there is the behaviour that matters;
    how the row is fetched (joined versus lazy) is an implementation detail the
    response must not expose.
    """
    register_patient(clinical_client)
    entries = audit_log(clinical_client)

    assert len(entries) == 1
    assert entries[0]["actor"]["display_name"] == "Clinical Demo User"
    assert entries[0]["actor"]["id"] > 0
