"""Ticket 36: Investigations and the two chase lists, at the HTTP API seam.

These tests drive the API a nurse uses. A test the doctor requested is recorded
against an Admission, followed to its result and marked reviewed, and the four
states move in one order only. Two worklists fall out of the same read: results
awaiting review, and tests still awaiting a result. A result note is free text,
recorded as the laboratory gave it: the system never reads a value, never flags
an abnormal result and never suggests anything from one, so nothing here is
parsed or interpreted. Every mutation appends exactly one audit entry in the same
transaction as the change, a refused transition writes none, and the reads write
nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import investigations
from app.models import (
    Admission,
    AuditEntry,
    Investigation,
    InvestigationState,
    Patient,
    Role,
    User,
)
from app.security import hash_password

CLINICAL_CREDENTIALS = {
    "email": "clinical@example.com",
    "password": "clinical-password",
}
ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

CLINICAL_ACTOR = "Clinical Demo User"

#: The full response shape an Investigation carries. A result is described only
#: by the free-text note; no key names a value, a range, a flag, an overdue mark
#: or an interpretation, which is what the absence tests below assert.
INVESTIGATION_KEYS = {
    "id",
    "admission_id",
    "patient",
    "test_name",
    "instructed_by",
    "requested_at",
    "requested_by",
    "state",
    "sample_taken_at",
    "result_available_at",
    "result_note",
    "reviewed_at",
    "reviewed_by",
}

#: A free-text result note carrying a numeric value and an assay word, so the
#: round-trip test can prove nothing is parsed from it.
VERBATIM_NOTE = "Hb 7.2 g/dL (below range), repeat in 24h\nMCV 78 fL"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def login_as_clinical(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=CLINICAL_CREDENTIALS)
    assert response.status_code == 200, response.text


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


def discharge(client: TestClient, admission_id: int):
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def record_investigation(
    client: TestClient,
    admission_id: int,
    test_name: str = "Full blood count",
    instructed_by: str | None = None,
):
    return client.post(
        f"/api/ward/admissions/{admission_id}/investigations",
        json={"test_name": test_name, "instructed_by": instructed_by},
    )


def sample_taken(client: TestClient, investigation_id: int):
    return client.post(f"/api/ward/investigations/{investigation_id}/sample-taken")


def record_result(client: TestClient, investigation_id: int, result_note: str):
    return client.post(
        f"/api/ward/investigations/{investigation_id}/result",
        json={"result_note": result_note},
    )


def review(client: TestClient, investigation_id: int):
    return client.post(f"/api/ward/investigations/{investigation_id}/review")


def admission_investigations(
    client: TestClient, admission_id: int
) -> list[dict[str, Any]]:
    response = client.get(f"/api/ward/admissions/{admission_id}/investigations")
    assert response.status_code == 200, response.text
    return response.json()["investigations"]


def awaiting_review(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/investigations/awaiting-review")
    assert response.status_code == 200, response.text
    return response.json()["investigations"]


def awaiting_result(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/investigations/awaiting-result")
    assert response.status_code == 200, response.text
    return response.json()["investigations"]


def board(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/board")
    assert response.status_code == 200, response.text
    return response.json()["admissions"]


def audit_log(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200
    response = client.get("/api/administrator/audit-log", params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def create_user(
    client: TestClient, email: str, display_name: str, role: Role
) -> int:
    """Insert a user directly, since there is no user-creation route.

    A second Clinical user is what proves the review records the reviewer rather
    than whoever happens to be signed in first.
    """
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        user = User(
            email=email,
            display_name=display_name,
            role=role.value,
            password_hash=hash_password("second-password"),
        )
        session.add(user)
        session.commit()
        return user.id


INVESTIGATION_ACTIONS = {
    "record_investigation",
    "record_investigation_sample",
    "record_investigation_result",
    "review_investigation",
}


def investigation_actions(entries: list[dict[str, Any]]) -> list[str]:
    """Just the Investigation mutations, so the Admission's own entry is ignored."""
    return [
        entry["action"]
        for entry in entries
        if entry["action"] in INVESTIGATION_ACTIONS
    ]


def _row_counts(client: TestClient) -> dict[str, int]:
    session_factory = client.app.state.session_factory
    models = (Investigation, AuditEntry, Admission, Patient)
    with session_factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model)
            )
            for model in models
        }


# --------------------------------------------------------------------------- #
# Recording an Investigation
# --------------------------------------------------------------------------- #


def test_an_investigation_is_recorded_and_reads_back_as_requested(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = record_investigation(clinical_client, admission_id, "Full blood count")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == INVESTIGATION_KEYS
    assert body["admission_id"] == admission_id
    assert body["patient"]["id"] == patient_id
    assert body["test_name"] == "Full blood count"
    assert body["state"] == "requested"
    assert body["requested_at"] is not None
    assert body["requested_by"]["display_name"] == CLINICAL_ACTOR
    assert body["sample_taken_at"] is None
    assert body["result_available_at"] is None
    assert body["result_note"] is None
    assert body["reviewed_at"] is None
    assert body["reviewed_by"] is None

    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["id"] == body["id"]


def test_the_instructing_doctor_is_recorded_as_free_text_when_given(
    clinical_client: TestClient,
) -> None:
    """The doctor is not a user of this system, so who requested it is free text."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = record_investigation(
        clinical_client, admission_id, "Chest X-ray", instructed_by="Dr Okafor"
    )

    assert response.status_code == 201, response.text
    assert response.json()["instructed_by"] == "Dr Okafor"
    assert response.json()["requested_by"]["display_name"] == CLINICAL_ACTOR


def test_recording_an_investigation_against_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = record_investigation(clinical_client, 999_999, "Full blood count")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


def test_a_blank_test_name_is_refused(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = record_investigation(clinical_client, admission_id, "   ")

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# The four states move in order
# --------------------------------------------------------------------------- #


def test_the_four_states_move_in_order_and_read_back(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]

    taken = sample_taken(clinical_client, investigation_id)
    assert taken.status_code == 200, taken.text
    assert taken.json()["state"] == "sample_taken"
    assert taken.json()["sample_taken_at"] is not None
    assert taken.json()["result_available_at"] is None

    resulted = record_result(clinical_client, investigation_id, "Normal")
    assert resulted.status_code == 200, resulted.text
    assert resulted.json()["state"] == "result_available"
    assert resulted.json()["result_note"] == "Normal"
    assert resulted.json()["result_available_at"] is not None
    assert resulted.json()["reviewed_at"] is None

    reviewed = review(clinical_client, investigation_id)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["state"] == "reviewed"
    assert reviewed.json()["reviewed_at"] is not None
    assert reviewed.json()["reviewed_by"]["display_name"] == CLINICAL_ACTOR

    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "reviewed"
    assert stored["result_note"] == "Normal"


def test_a_result_is_never_described_as_overdue(
    clinical_client: TestClient,
) -> None:
    """No clinical alarm is attached to a result: there is no overdue mark.

    A result that has arrived and not been reviewed is described by its state
    (``result_available``) and the review fields alone; the vocabulary names no
    threshold, so the response carries no ``overdue`` field and nothing else
    that reads as an alarm.
    """
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]
    assert sample_taken(clinical_client, investigation_id).status_code == 200
    resulted = record_result(clinical_client, investigation_id, "Normal")

    assert resulted.status_code == 200, resulted.text
    body = resulted.json()
    assert body["state"] == "result_available"
    assert "overdue_review" not in body
    assert not any("overdue" in key for key in body)
    assert not hasattr(investigations, "review_is_overdue")


def test_a_second_move_is_refused_and_the_first_move_is_preserved(
    clinical_client: TestClient,
) -> None:
    """A repeat move changes nothing: the first recorded act stands."""
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]
    taken = sample_taken(clinical_client, investigation_id)
    assert taken.status_code == 200
    sample_taken_at = taken.json()["sample_taken_at"]

    resulted = record_result(clinical_client, investigation_id, "Normal")
    assert resulted.status_code == 200
    result_available_at = resulted.json()["result_available_at"]
    result_note = resulted.json()["result_note"]

    reviewed = review(clinical_client, investigation_id)
    assert reviewed.status_code == 200
    reviewed_at = reviewed.json()["reviewed_at"]
    reviewed_by = reviewed.json()["reviewed_by"]

    # Every repeat is refused, and none of the first moves is overwritten.
    assert sample_taken(clinical_client, investigation_id).status_code == 409
    assert record_result(clinical_client, investigation_id, "A later note").status_code == 409
    assert review(clinical_client, investigation_id).status_code == 409

    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "reviewed"
    assert stored["sample_taken_at"] == sample_taken_at
    assert stored["result_available_at"] == result_available_at
    assert stored["result_note"] == result_note == "Normal"
    assert stored["reviewed_at"] == reviewed_at
    assert stored["reviewed_by"] == reviewed_by


def test_the_conditional_update_refuses_a_move_that_races(
    clinical_client: TestClient,
) -> None:
    """The guard is the database row, not the caller's possibly-stale view.

    One session loads an Investigation while it is still ``requested``; another
    moves it and commits; the first then tries the same move. Its conditional
    update matches no row, so it is refused with the same ``409`` rather than
    overwriting the recorded instant -- which is the property that keeps two
    concurrent requests from both moving the same Investigation.
    """
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]
    session_factory = clinical_client.app.state.session_factory

    stale = session_factory()
    winner = session_factory()
    try:
        stale_investigation = stale.get(Investigation, investigation_id)
        assert (
            investigations.investigation_state(stale_investigation)
            is InvestigationState.requested
        )

        winner_investigation = winner.get(Investigation, investigation_id)
        investigations.mark_sample_taken(winner, winner_investigation)
        winner.commit()

        with pytest.raises(HTTPException) as excinfo:
            investigations.mark_sample_taken(stale, stale_investigation)
        assert excinfo.value.status_code == 409
        assert (
            excinfo.value.detail
            == investigations.INVESTIGATION_NOT_REQUESTED_DETAIL
        )
    finally:
        stale.close()
        winner.close()


def test_a_result_cannot_be_recorded_before_a_sample_is_taken(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]

    response = record_result(clinical_client, investigation_id, "Normal")

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A result can only be recorded once a sample has been taken"
    }
    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "requested"
    assert stored["result_note"] is None


def test_a_result_cannot_be_reviewed_before_it_is_available(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200

    response = review(clinical_client, investigation_id)

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A result can only be reviewed once it is available"
    }
    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "sample_taken"
    assert stored["reviewed_at"] is None


def test_a_sample_can_only_be_taken_for_a_requested_investigation(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200

    response = sample_taken(clinical_client, investigation_id)

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A sample can only be taken for a requested Investigation"
    }


def test_every_repeat_move_is_refused(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200
    assert record_result(clinical_client, investigation_id, "Normal").status_code == 200
    assert review(clinical_client, investigation_id).status_code == 200

    assert sample_taken(clinical_client, investigation_id).status_code == 409
    assert record_result(clinical_client, investigation_id, "Normal").status_code == 409
    assert review(clinical_client, investigation_id).status_code == 409

    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "reviewed"


def test_a_move_on_an_unknown_investigation_is_not_found(
    clinical_client: TestClient,
) -> None:
    taken = sample_taken(clinical_client, 999_999)
    resulted = record_result(clinical_client, 999_999, "Normal")
    reviewed = review(clinical_client, 999_999)

    assert taken.status_code == 404
    assert resulted.status_code == 404
    assert reviewed.status_code == 404
    assert taken.json() == {"detail": "Investigation not found"}


# --------------------------------------------------------------------------- #
# The review is attributable
# --------------------------------------------------------------------------- #


def test_the_review_records_the_actor_and_the_time(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(
        clinical_client, admission_id, "Full blood count"
    ).json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200
    assert record_result(clinical_client, investigation_id, "Normal").status_code == 200

    # A second Clinical user does the review, so the actor is not the recorder.
    reviewer_id = create_user(
        clinical_client, "reviewer@example.com", "Reviewing Nurse", Role.clinical
    )
    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        from app import investigations

        stored_investigation = session.get(Investigation, investigation_id)
        reviewer = session.get(User, reviewer_id)
        investigations.review_result(
            session, stored_investigation, reviewer=reviewer
        )
        session.commit()

    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["reviewed_by"]["id"] == reviewer_id
    assert stored["reviewed_by"]["display_name"] == "Reviewing Nurse"
    assert datetime.fromisoformat(stored["reviewed_at"]) is not None


# --------------------------------------------------------------------------- #
# The two worklists
# --------------------------------------------------------------------------- #


def test_the_worklists_cover_several_patients_and_exclude_wrong_states(
    clinical_client: TestClient,
) -> None:
    first = admit(clinical_client, register_patient(clinical_client, "P One"), "Ward A", "1")
    second = admit(clinical_client, register_patient(clinical_client, "P Two"), "Ward A", "2")

    # One awaiting review on each of two patients, one awaiting result, one done.
    reviewable_first = record_investigation(clinical_client, first, "FBC").json()["id"]
    reviewable_second = record_investigation(clinical_client, second, "U&E").json()["id"]
    for investigation_id in (reviewable_first, reviewable_second):
        assert sample_taken(clinical_client, investigation_id).status_code == 200
        assert (
            record_result(clinical_client, investigation_id, "Normal").status_code
            == 200
        )

    awaiting_first = record_investigation(clinical_client, first, "Clotting").json()["id"]
    assert sample_taken(clinical_client, awaiting_first).status_code == 200

    fully_done = record_investigation(clinical_client, second, "CRP").json()["id"]
    assert sample_taken(clinical_client, fully_done).status_code == 200
    assert record_result(clinical_client, fully_done, "Normal").status_code == 200
    assert review(clinical_client, fully_done).status_code == 200

    review_ids = {item["id"] for item in awaiting_review(clinical_client)}
    result_ids = {item["id"] for item in awaiting_result(clinical_client)}

    assert review_ids == {reviewable_first, reviewable_second}
    assert result_ids == {awaiting_first}
    # The reviewed one is on neither list, and the two lists do not overlap.
    assert fully_done not in review_ids | result_ids
    assert review_ids.isdisjoint(result_ids)


def test_the_awaiting_result_list_holds_both_requested_and_sample_taken(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    requested = record_investigation(clinical_client, admission_id, "FBC").json()["id"]
    sampled = record_investigation(clinical_client, admission_id, "U&E").json()["id"]
    assert sample_taken(clinical_client, sampled).status_code == 200

    ids = {item["id"] for item in awaiting_result(clinical_client)}

    assert ids == {requested, sampled}


def test_a_discharged_stays_investigations_leave_the_worklists(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()["id"]
    assert discharge(clinical_client, admission_id).status_code == 200

    assert awaiting_result(clinical_client) == []
    assert awaiting_review(clinical_client) == []
    # The record is kept and still reads back for the stay.
    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["id"] == investigation_id


def test_admission_investigations_read_newest_first(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    first = record_investigation(clinical_client, admission_id, "First").json()["id"]
    second = record_investigation(clinical_client, admission_id, "Second").json()["id"]

    ids = [item["id"] for item in admission_investigations(clinical_client, admission_id)]

    assert ids == [second, first]


# --------------------------------------------------------------------------- #
# The board's results-awaiting-review count
# --------------------------------------------------------------------------- #


def test_the_board_counts_the_real_unreviewed_results(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    available = record_investigation(clinical_client, admission_id, "FBC").json()["id"]
    assert sample_taken(clinical_client, available).status_code == 200
    assert record_result(clinical_client, available, "Normal").status_code == 200

    # A requested one and a reviewed one are not counted.
    record_investigation(clinical_client, admission_id, "U&E")
    reviewed = record_investigation(clinical_client, admission_id, "CRP").json()["id"]
    assert sample_taken(clinical_client, reviewed).status_code == 200
    assert record_result(clinical_client, reviewed, "Normal").status_code == 200
    assert review(clinical_client, reviewed).status_code == 200

    (row,) = board(clinical_client)

    assert row["unreviewed_result_count"] == 1


# --------------------------------------------------------------------------- #
# Free text is recorded as given, never read
# --------------------------------------------------------------------------- #


def test_a_free_text_result_note_is_stored_verbatim(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200

    response = record_result(clinical_client, investigation_id, VERBATIM_NOTE)

    assert response.status_code == 200, response.text
    assert response.json()["result_note"] == VERBATIM_NOTE
    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["result_note"] == VERBATIM_NOTE


def test_no_interpretation_of_a_result_is_produced(
    clinical_client: TestClient,
) -> None:
    """The value in the note is never parsed, flagged or interpreted anywhere."""
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()["id"]
    assert sample_taken(clinical_client, investigation_id).status_code == 200
    resulted = record_result(clinical_client, investigation_id, VERBATIM_NOTE).json()

    # The only keys served describe the test's progress and the note as written;
    # no key names a value, a reference range, an abnormality or a suggestion.
    forbidden = {
        "value",
        "reference_range",
        "reference_low",
        "reference_high",
        "abnormal_fields",
        "abnormal",
        "flag",
        "interpretation",
        "suggestion",
    }
    assert forbidden.isdisjoint(set(resulted))
    # The numeric value survives as characters in the note, not as a parsed field.
    assert resulted["result_note"] == VERBATIM_NOTE
    assert resulted["state"] == "result_available"


# --------------------------------------------------------------------------- #
# Closed admissions
# --------------------------------------------------------------------------- #


def test_a_discharged_admission_takes_no_new_investigation(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = record_investigation(clinical_client, admission_id, "FBC")

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A discharged Admission cannot take new Investigations"
    }


def test_a_move_on_an_investigation_of_a_discharged_stay_is_refused(
    clinical_client: TestClient,
) -> None:
    """A closed record is not rewritten: no move on a discharged stay's test."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]
    assert discharge(clinical_client, admission_id).status_code == 200

    taken = sample_taken(clinical_client, investigation_id)
    resulted = record_result(clinical_client, investigation_id, "Normal")
    reviewed = review(clinical_client, investigation_id)

    assert taken.status_code == 409, taken.text
    assert resulted.status_code == 409, resulted.text
    assert reviewed.status_code == 409, reviewed.text
    assert taken.json() == {
        "detail": "An Investigation on a discharged Admission cannot be changed"
    }
    (stored,) = admission_investigations(clinical_client, admission_id)
    assert stored["state"] == "requested"


# --------------------------------------------------------------------------- #
# Reads write nothing
# --------------------------------------------------------------------------- #


def test_reading_the_investigation_lists_adds_no_rows(
    clinical_client: TestClient,
) -> None:
    admission_id = admit(clinical_client, register_patient(clinical_client))
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]
    assert sample_taken(clinical_client, investigation_id).status_code == 200
    before = _row_counts(clinical_client)

    for _ in range(3):
        admission_investigations(clinical_client, admission_id)
        awaiting_review(clinical_client)
        awaiting_result(clinical_client)
        board(clinical_client)

    assert _row_counts(clinical_client) == before


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def test_recording_an_investigation_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    record_investigation(clinical_client, admission_id, "FBC")

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert investigation_actions(entries) == ["record_investigation"]
    (entry,) = [
        entry for entry in entries if entry["action"] == "record_investigation"
    ]
    assert entry["actor"]["display_name"] == CLINICAL_ACTOR
    assert entry["admission_id"] == admission_id


def test_each_state_move_appends_exactly_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]

    assert sample_taken(clinical_client, investigation_id).status_code == 200
    assert record_result(clinical_client, investigation_id, "Normal").status_code == 200
    assert review(clinical_client, investigation_id).status_code == 200

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert investigation_actions(entries) == [
        "record_investigation",
        "record_investigation_sample",
        "record_investigation_result",
        "review_investigation",
    ]


def test_a_refused_transition_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    investigation_id = record_investigation(clinical_client, admission_id, "FBC").json()[
        "id"
    ]

    # Recorded but no sample yet: a result and a review are both refused.
    assert record_result(clinical_client, investigation_id, "Normal").status_code == 409
    assert review(clinical_client, investigation_id).status_code == 409

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert investigation_actions(entries) == ["record_investigation"]
