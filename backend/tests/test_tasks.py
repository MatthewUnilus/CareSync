"""Ticket 33: Tasks and the ward round, at the HTTP API seam.

These tests drive the API a nurse uses. A Task is raised by hand or from a saved
Ward Round Entry, one round entry raising several Tasks at once. A Task carries an
optional due time and an optional assignee, is marked done by a Clinical user, and
the ward's cross-patient list shows the open work across every patient rather than
one list per patient. Every Task raised, completed and assigned appends exactly one
audit entry in the same transaction as the change, and reading the list writes
nothing. Overdue is a display mark and nothing acts on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    Admission,
    AuditEntry,
    NursingNote,
    Patient,
    Role,
    Task,
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

#: The fields a Ward Round Entry's note carries, one per template field.
WARD_ROUND_FIELDS = [
    {"key": "vital_signs", "value": "Temperature 37.0 C"},
    {"key": "current_issue", "value": "Breathless on exertion"},
    {"key": "findings", "value": "Chest clear"},
    {"key": "plan", "value": "Start antibiotics"},
    {"key": "review_due", "value": "Tomorrow morning"},
]

#: A due time in the past, so a Task with it is overdue; and one in the future,
#: so a Task with it is not.
PAST_DUE = "2020-01-01T08:00:00+00:00"
FUTURE_DUE = "2999-01-01T08:00:00+00:00"


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


def write_ward_round_note(client: TestClient, admission_id: int) -> int:
    response = client.post(
        f"/api/ward/admissions/{admission_id}/notes",
        json={
            "template_key": "ward_round_entry",
            "fields": WARD_ROUND_FIELDS,
            "corrects_note_id": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def write_note(
    client: TestClient, admission_id: int, template_key: str, fields: list[dict[str, str]]
) -> int:
    response = client.post(
        f"/api/ward/admissions/{admission_id}/notes",
        json={"template_key": template_key, "fields": fields, "corrects_note_id": None},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def raise_task(
    client: TestClient,
    admission_id: int,
    description: str,
    due_at: str | None = None,
    assignee_user_id: int | None = None,
):
    return client.post(
        f"/api/ward/admissions/{admission_id}/tasks",
        json={
            "description": description,
            "due_at": due_at,
            "assignee_user_id": assignee_user_id,
        },
    )


def raise_round_tasks(
    client: TestClient,
    admission_id: int,
    note_id: int,
    tasks: list[dict[str, Any]],
):
    return client.post(
        f"/api/ward/admissions/{admission_id}/ward-round-tasks",
        json={"note_id": note_id, "tasks": tasks},
    )


def admission_tasks(client: TestClient, admission_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/ward/admissions/{admission_id}/tasks")
    assert response.status_code == 200, response.text
    return response.json()["tasks"]


def ward_tasks(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/ward/tasks", params=params)
    assert response.status_code == 200, response.text
    return response.json()["tasks"]


def complete(client: TestClient, task_id: int):
    return client.post(f"/api/ward/tasks/{task_id}/complete")


def assign(client: TestClient, task_id: int, assignee_user_id: int | None):
    return client.post(
        f"/api/ward/tasks/{task_id}/assign",
        json={"assignee_user_id": assignee_user_id},
    )


def staff(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/staff")
    assert response.status_code == 200, response.text
    return response.json()["users"]


def acting_user_id(client: TestClient) -> int:
    """The id of the signed-in Clinical demo user, read from the staff list."""
    return next(user["id"] for user in staff(client) if user["display_name"] == CLINICAL_ACTOR)


def create_user(
    client: TestClient, email: str, display_name: str, role: Role
) -> int:
    """Insert a user directly, since there is no user-creation route.

    A second Clinical user is what proves the assignee list and the "mine" filter
    distinguish one person from another; an Administrator is what proves a
    non-clinical user cannot be an assignee.
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


TASK_ACTIONS = {"raise_task", "complete_task", "assign_task"}


def task_actions(entries: list[dict[str, Any]]) -> list[str]:
    """Just the Task mutations, so an Admission's own audit entry is ignored."""
    return [entry["action"] for entry in entries if entry["action"] in TASK_ACTIONS]


def _row_counts(client: TestClient) -> dict[str, int]:
    session_factory = client.app.state.session_factory
    models = (Task, AuditEntry, NursingNote, Admission, Patient)
    with session_factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model)
            )
            for model in models
        }


# --------------------------------------------------------------------------- #
# Raising a Task by hand
# --------------------------------------------------------------------------- #


def test_a_task_is_raised_by_hand_and_reads_back(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = raise_task(clinical_client, admission_id, "Check blood pressure")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["admission_id"] == admission_id
    assert body["patient"]["id"] == patient_id
    assert body["description"] == "Check blood pressure"
    assert body["due_at"] is None
    assert body["assignee"] is None
    assert body["author"]["display_name"] == CLINICAL_ACTOR
    assert body["status"] == "open"
    assert body["completed_by"] is None
    assert body["completed_at"] is None
    assert body["overdue"] is False
    assert body["note_id"] is None

    (stored,) = admission_tasks(clinical_client, admission_id)
    assert stored["id"] == body["id"]


def test_a_task_is_raised_with_a_due_time_and_an_assignee(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    current = acting_user_id(clinical_client)

    response = raise_task(
        clinical_client,
        admission_id,
        "Give fluids",
        due_at=FUTURE_DUE,
        assignee_user_id=current,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert datetime.fromisoformat(body["due_at"]) == datetime.fromisoformat(FUTURE_DUE)
    assert body["assignee"]["id"] == current
    assert body["assignee"]["display_name"] == CLINICAL_ACTOR


def test_raising_a_task_against_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = raise_task(clinical_client, 999_999, "Check blood pressure")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


def test_a_discharged_admission_takes_no_new_task(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = raise_task(clinical_client, admission_id, "Check blood pressure")

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A discharged Admission cannot take new Tasks"
    }


def test_a_blank_description_is_refused(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = raise_task(clinical_client, admission_id, "   ")

    assert response.status_code == 422, response.text


def test_an_assignee_that_is_not_clinical_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    administrator_id = create_user(
        clinical_client, "admin2@example.com", "Second Administrator", Role.administrator
    )

    response = raise_task(
        clinical_client, admission_id, "Give fluids", assignee_user_id=administrator_id
    )

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": "The assignee must be a Clinical user"}


def test_an_unknown_assignee_is_refused(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = raise_task(
        clinical_client, admission_id, "Give fluids", assignee_user_id=999_999
    )

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- #
# The staff list
# --------------------------------------------------------------------------- #


def test_the_staff_list_offers_clinical_users_only(
    clinical_client: TestClient,
) -> None:
    create_user(
        clinical_client, "nurse@example.com", "Night Nurse", Role.clinical
    )

    served = staff(clinical_client)

    names = [user["display_name"] for user in served]
    assert CLINICAL_ACTOR in names
    assert "Night Nurse" in names
    assert "Administrator Demo User" not in names
    for user in served:
        assert set(user) == {"id", "display_name"}


# --------------------------------------------------------------------------- #
# Tasks raised from a Ward Round Entry
# --------------------------------------------------------------------------- #


def test_a_round_entry_raises_several_tasks_on_the_right_patient(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_admission = admit(clinical_client, first)
    second_admission = admit(clinical_client, second, bed="4")
    note_id = write_ward_round_note(clinical_client, first_admission)

    response = raise_round_tasks(
        clinical_client,
        first_admission,
        note_id,
        [
            {"description": "Start antibiotics", "due_at": None, "assignee_user_id": None},
            {"description": "Repeat bloods", "due_at": FUTURE_DUE, "assignee_user_id": None},
        ],
    )

    assert response.status_code == 201, response.text
    tasks = response.json()["tasks"]
    assert [task["description"] for task in tasks] == [
        "Start antibiotics",
        "Repeat bloods",
    ]
    for task in tasks:
        assert task["admission_id"] == first_admission
        assert task["patient"]["id"] == first
        assert task["note_id"] == note_id
        assert task["status"] == "open"

    # The Tasks belong to the round entry's patient, and to that patient alone.
    on_first = admission_tasks(clinical_client, first_admission)
    assert {task["id"] for task in on_first} == {task["id"] for task in tasks}
    assert admission_tasks(clinical_client, second_admission) == []


def test_a_round_entry_raising_no_tasks_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    note_id = write_ward_round_note(clinical_client, admission_id)

    response = raise_round_tasks(clinical_client, admission_id, note_id, [])

    assert response.status_code == 422, response.text


def test_a_note_from_another_admission_cannot_raise_tasks(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_admission = admit(clinical_client, first)
    second_admission = admit(clinical_client, second, bed="4")
    note_on_first = write_ward_round_note(clinical_client, first_admission)

    response = raise_round_tasks(
        clinical_client,
        second_admission,
        note_on_first,
        [{"description": "Start antibiotics", "due_at": None, "assignee_user_id": None}],
    )

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": (
            "A Ward Round Entry must be on the same Admission as the Tasks it raises"
        )
    }


def test_only_a_ward_round_entry_can_raise_tasks(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    note_id = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        [
            {"key": "vital_signs", "value": "Temperature 37.0 C"},
            {"key": "general_condition", "value": "Comfortable"},
            {"key": "mobility", "value": "Independent"},
            {"key": "skin", "value": "Intact"},
            {"key": "pain", "value": "None"},
            {"key": "intake_output", "value": "Balanced"},
        ],
    )

    response = raise_round_tasks(
        clinical_client,
        admission_id,
        note_id,
        [{"description": "Start antibiotics", "due_at": None, "assignee_user_id": None}],
    )

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "Tasks can only be raised from a Ward Round Entry"
    }


def test_an_unknown_note_cannot_raise_tasks(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = raise_round_tasks(
        clinical_client,
        admission_id,
        999_999,
        [{"description": "Start antibiotics", "due_at": None, "assignee_user_id": None}],
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Note not found"}


def test_a_bad_assignee_anywhere_in_the_round_leaves_no_task_behind(
    clinical_client: TestClient,
) -> None:
    """The batch is atomic: a refused assignee stages nothing, not a prefix."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    note_id = write_ward_round_note(clinical_client, admission_id)
    before = _row_counts(clinical_client)

    response = raise_round_tasks(
        clinical_client,
        admission_id,
        note_id,
        [
            {"description": "Start antibiotics", "due_at": None, "assignee_user_id": None},
            {
                "description": "Repeat bloods",
                "due_at": None,
                "assignee_user_id": 999_999,
            },
        ],
    )

    assert response.status_code == 422, response.text
    assert admission_tasks(clinical_client, admission_id) == []
    assert _row_counts(clinical_client) == before


# --------------------------------------------------------------------------- #
# Marking done, assignment and the record
# --------------------------------------------------------------------------- #


def test_marking_done_removes_it_from_the_open_list_and_keeps_it_in_the_record(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]

    response = complete(clinical_client, task_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "done"
    assert body["completed_by"]["display_name"] == CLINICAL_ACTOR
    assert body["completed_at"] is not None

    # Gone from the open list...
    assert ward_tasks(clinical_client) == []
    # ...but kept in the admission's record.
    (kept,) = admission_tasks(clinical_client, admission_id)
    assert kept["id"] == task_id
    assert kept["status"] == "done"


def test_completing_a_task_twice_is_refused(clinical_client: TestClient) -> None:
    """Two completes cannot both win: the second is refused and the first stands.

    The write is conditional on the Task still being open, so the second act
    changes no row and is refused with ``409``; the one recorded completion — its
    completer and its instant — is left exactly as the first act recorded it.
    """
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]
    first = complete(clinical_client, task_id)
    assert first.status_code == 200, first.text
    first_instant = first.json()["completed_at"]
    first_by = first.json()["completed_by"]

    second = complete(clinical_client, task_id)

    assert second.status_code == 409, second.text
    assert second.json() == {"detail": "This Task is already done"}
    # The one recorded completion is not overwritten.
    (kept,) = admission_tasks(clinical_client, admission_id)
    assert kept["completed_at"] == first_instant
    assert kept["completed_by"] == first_by


def test_a_later_completer_does_not_overwrite_the_first(
    clinical_client: TestClient,
) -> None:
    """A different signed-in user completing again still loses to the first.

    The conflict is decided by the row, not by who is asking, so a second user's
    attempt records nothing and leaves the first user's completion intact.
    """
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]
    create_user(clinical_client, "nurse@example.com", "Night Nurse", Role.clinical)
    first = complete(clinical_client, task_id)
    assert first.status_code == 200, first.text
    first_instant = first.json()["completed_at"]

    # A different signed-in user (still Clinical) tries to complete it too.
    login = clinical_client.post(
        "/api/auth/login",
        json={"email": "nurse@example.com", "password": "second-password"},
    )
    assert login.status_code == 200, login.text
    second = complete(clinical_client, task_id)

    assert second.status_code == 409, second.text
    (kept,) = admission_tasks(clinical_client, admission_id)
    assert kept["completed_at"] == first_instant
    assert kept["completed_by"]["display_name"] == CLINICAL_ACTOR


def test_a_task_on_a_discharged_admission_can_still_be_completed_and_assigned(
    clinical_client: TestClient,
) -> None:
    """A discharge takes the stay off the board, not its work out of the record.

    An open Task a discharge leaves behind can still be completed and assigned, so
    the stay's outstanding work is closable rather than frozen; the stay itself is
    no longer listed on the board.
    """
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]
    nurse_id = create_user(clinical_client, "nurse@example.com", "Night Nurse", Role.clinical)
    assert discharge(clinical_client, admission_id).status_code == 200
    assert board(clinical_client) == []

    assigned = assign(clinical_client, task_id, nurse_id)
    completed = complete(clinical_client, task_id)

    assert assigned.status_code == 200, assigned.text
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "done"
    (kept,) = admission_tasks(clinical_client, admission_id)
    assert kept["status"] == "done"
    assert kept["assignee"]["display_name"] == "Night Nurse"


def test_completing_an_unknown_task_is_not_found(clinical_client: TestClient) -> None:
    response = complete(clinical_client, 999_999)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Task not found"}


def test_a_task_can_be_assigned_reassigned_and_unassigned(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]
    nurse_id = create_user(clinical_client, "nurse@example.com", "Night Nurse", Role.clinical)

    assigned = assign(clinical_client, task_id, nurse_id)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assignee"]["display_name"] == "Night Nurse"

    unassigned = assign(clinical_client, task_id, None)
    assert unassigned.status_code == 200, unassigned.text
    assert unassigned.json()["assignee"] is None


def test_assigning_an_unknown_task_is_not_found(clinical_client: TestClient) -> None:
    response = assign(clinical_client, 999_999, None)

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Task not found"}


# --------------------------------------------------------------------------- #
# The cross-patient list
# --------------------------------------------------------------------------- #


def test_the_cross_patient_list_covers_several_patients(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_admission = admit(clinical_client, first, bed="1")
    second_admission = admit(clinical_client, second, bed="2")
    raise_task(clinical_client, first_admission, "For Ada")
    raise_task(clinical_client, second_admission, "For Alan")

    served = ward_tasks(clinical_client)

    assert {task["description"] for task in served} == {"For Ada", "For Alan"}
    assert {task["patient"]["id"] for task in served} == {first, second}


def test_the_cross_patient_list_filters_to_one_assignee(
    clinical_client: TestClient,
) -> None:
    current = acting_user_id(clinical_client)
    nurse_id = create_user(clinical_client, "nurse@example.com", "Night Nurse", Role.clinical)
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_admission = admit(clinical_client, first, bed="1")
    second_admission = admit(clinical_client, second, bed="2")
    mine = raise_task(
        clinical_client, first_admission, "Mine", assignee_user_id=current
    ).json()["id"]
    raise_task(clinical_client, second_admission, "Unassigned")
    raise_task(
        clinical_client, second_admission, "Someone else's", assignee_user_id=nurse_id
    )

    served = ward_tasks(clinical_client, mine="true")

    assert [task["id"] for task in served] == [mine]
    # Without the filter the whole ward's work is shown.
    assert len(ward_tasks(clinical_client)) == 3


def test_the_cross_patient_list_excludes_discharged_admissions(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client, "Ada Lovelace", 36)
    second = register_patient(clinical_client, "Alan Turing", 40)
    first_admission = admit(clinical_client, first, bed="1")
    second_admission = admit(clinical_client, second, bed="2")
    raise_task(clinical_client, first_admission, "Stays")
    raise_task(clinical_client, second_admission, "Leaves")
    assert discharge(clinical_client, second_admission).status_code == 200

    served = ward_tasks(clinical_client)

    assert [task["description"] for task in served] == ["Stays"]


def test_include_done_adds_the_done_tasks_for_the_history(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    open_id = raise_task(clinical_client, admission_id, "Still open").json()["id"]
    done_id = raise_task(clinical_client, admission_id, "Done").json()["id"]
    assert complete(clinical_client, done_id).status_code == 200

    open_only = ward_tasks(clinical_client)
    with_done = ward_tasks(clinical_client, include_done="true")

    assert [task["id"] for task in open_only] == [open_id]
    assert {task["id"] for task in with_done} == {open_id, done_id}


def test_the_cross_patient_list_orders_by_due_time_with_undated_last(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    undated = raise_task(clinical_client, admission_id, "No deadline").json()["id"]
    later = raise_task(
        clinical_client, admission_id, "Later", due_at=FUTURE_DUE
    ).json()["id"]
    sooner = raise_task(
        clinical_client, admission_id, "Sooner", due_at=PAST_DUE
    ).json()["id"]

    served = ward_tasks(clinical_client)

    assert [task["id"] for task in served] == [sooner, later, undated]


# --------------------------------------------------------------------------- #
# Overdue
# --------------------------------------------------------------------------- #


def test_an_overdue_task_is_marked_and_a_future_or_undated_one_is_not(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    overdue = raise_task(
        clinical_client, admission_id, "Late", due_at=PAST_DUE
    ).json()
    future = raise_task(
        clinical_client, admission_id, "Early", due_at=FUTURE_DUE
    ).json()
    undated = raise_task(clinical_client, admission_id, "No deadline").json()

    assert overdue["overdue"] is True
    assert future["overdue"] is False
    assert undated["overdue"] is False


def test_a_done_task_is_not_shown_as_overdue(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(
        clinical_client, admission_id, "Late but done", due_at=PAST_DUE
    ).json()["id"]

    response = complete(clinical_client, task_id)

    assert response.status_code == 200, response.text
    assert response.json()["overdue"] is False
    assert response.json()["status"] == "done"


# --------------------------------------------------------------------------- #
# The board's open Task count
# --------------------------------------------------------------------------- #


def test_the_board_counts_the_real_open_tasks(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    first = raise_task(clinical_client, admission_id, "First").json()["id"]
    raise_task(clinical_client, admission_id, "Second")
    assert complete(clinical_client, first).status_code == 200

    (row,) = board(clinical_client)

    assert row["open_task_count"] == 1


# --------------------------------------------------------------------------- #
# The list writes nothing
# --------------------------------------------------------------------------- #


def test_reading_the_task_lists_adds_no_rows(clinical_client: TestClient) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    raise_task(
        clinical_client, admission_id, "Late", due_at=PAST_DUE
    )
    note_id = write_ward_round_note(clinical_client, admission_id)
    raise_round_tasks(
        clinical_client,
        admission_id,
        note_id,
        [{"description": "From the round", "due_at": None, "assignee_user_id": None}],
    )
    before = _row_counts(clinical_client)

    for _ in range(3):
        admission_tasks(clinical_client, admission_id)
        ward_tasks(clinical_client)
        ward_tasks(clinical_client, include_done="true")
        staff(clinical_client)

    assert _row_counts(clinical_client) == before


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def test_raising_a_task_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    raise_task(clinical_client, admission_id, "Check blood pressure")

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert task_actions(entries) == ["raise_task"]
    (entry,) = [e for e in entries if e["action"] == "raise_task"]
    assert entry["actor"]["display_name"] == CLINICAL_ACTOR
    assert entry["admission_id"] == admission_id


def test_a_round_entry_appends_one_audit_entry_per_task(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    note_id = write_ward_round_note(clinical_client, admission_id)

    response = raise_round_tasks(
        clinical_client,
        admission_id,
        note_id,
        [
            {"description": "Start antibiotics", "due_at": None, "assignee_user_id": None},
            {"description": "Repeat bloods", "due_at": None, "assignee_user_id": None},
            {"description": "Review in the morning", "due_at": None, "assignee_user_id": None},
        ],
    )
    assert response.status_code == 201, response.text

    entries = audit_log(clinical_client, admission_id=admission_id)
    raised = [entry for entry in entries if entry["action"] == "raise_task"]
    assert len(raised) == 3
    for entry in raised:
        assert entry["admission_id"] == admission_id


def test_completing_a_task_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]

    assert complete(clinical_client, task_id).status_code == 200

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert task_actions(entries) == ["raise_task", "complete_task"]


def test_assigning_a_task_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    task_id = raise_task(clinical_client, admission_id, "Check blood pressure").json()[
        "id"
    ]
    nurse_id = create_user(clinical_client, "nurse@example.com", "Night Nurse", Role.clinical)

    assert assign(clinical_client, task_id, nurse_id).status_code == 200

    entries = audit_log(clinical_client, admission_id=admission_id)
    assert task_actions(entries) == ["raise_task", "assign_task"]


def test_a_refused_task_action_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = raise_task(
        clinical_client, admission_id, "Give fluids", assignee_user_id=999_999
    )
    assert response.status_code == 422

    assert task_actions(audit_log(clinical_client, admission_id=admission_id)) == []
