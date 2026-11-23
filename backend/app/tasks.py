"""Tasks: the work a ward round raises, and the ward's cross-patient list.

A Task is how an instruction becomes something to work (CONTEXT.md, "Task"). It
is raised against an Admission either by hand or from a Ward Round Entry, carries
an optional due time and an optional assignee, and a Clinical user marks it done.
One round entry may raise several Tasks in one go, because a round gives several
instructions in one conversation.

The cross-patient list shows the ward's open Tasks across every patient rather
than a list per patient, filterable to the ones assigned to the signed-in user.
Assignment is optional on purpose, so both an assigned caseload and a shared ward
work; the assignee filter works in both worlds.

Nothing acts on a Task on its own. ``overdue`` is a comparison against the clock
at read time and nothing more (ADR 0010's rule for a second case): a Task is
never escalated, reassigned or closed by the system.

The functions that stage a change never commit: the route commits, so the Task
and its single audit entry land in one transaction (ADR 0007). A round entry that
raises several Tasks stages them and their audit entries together, so the whole
batch lands or fails as one.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.models import Admission, NursingNote, Role, Task, User
from app.schemas import (
    ActorResponse,
    PatientResponse,
    StaffMemberResponse,
    StaffResponse,
    TaskResponse,
    WardRoundTaskPayload,
)
from app.timeutils import as_utc, utc_now

#: Raised when an unknown Task is named. A Task id that resolves to nothing is a
#: missing resource rather than a bad request.
TASK_NOT_FOUND_DETAIL = "Task not found"

#: Raised when a Task that is already done is marked done again. One completion
#: instant is recorded, so the second act is refused rather than overwriting it.
TASK_ALREADY_DONE_DETAIL = "This Task is already done"

#: Raised when an assignee is named that is not a Clinical user. Administration is
#: read-only oversight and does not do clinical work, so it cannot be an assignee.
ASSIGNEE_NOT_CLINICAL_DETAIL = "The assignee must be a Clinical user"

#: Raised when a round entry named by a task-raising request is not a Ward Round
#: Entry. Only a round entry raises Tasks; the note is otherwise the wrong kind.
WARD_ROUND_NOTE_WRONG_TEMPLATE_DETAIL = (
    "Tasks can only be raised from a Ward Round Entry"
)

#: Raised when a round entry named by a task-raising request belongs to another
#: Admission. A Task belongs to the patient on the note, so the note and the
#: Admission must be the same stay.
WARD_ROUND_NOTE_OTHER_ADMISSION_DETAIL = (
    "A Ward Round Entry must be on the same Admission as the Tasks it raises"
)


def resolve_assignee(session: Session, assignee_user_id: int | None) -> User | None:
    """The Clinical user an assignee id names, or None for an unassigned Task.

    A named assignee must be a Clinical user: Administration is read-only oversight
    and cannot be assigned clinical work. An unknown id and a non-clinical user are
    both refused with ``422``, because the id names a member of a fixed set of
    people the route validates against.
    """
    if assignee_user_id is None:
        return None
    user = session.get(User, assignee_user_id)
    if user is None or user.role != Role.clinical.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ASSIGNEE_NOT_CLINICAL_DETAIL,
        )
    return user


def stage_task(
    session: Session,
    *,
    admission: Admission,
    author: User,
    description: str,
    due_at: datetime | None,
    assignee: User | None = None,
    note: NursingNote | None = None,
) -> Task:
    """Build one Task and add it, without committing.

    ``note`` is the Ward Round Entry the Task came from, or None when it was raised
    by hand. The caller commits, so the Task and its single audit entry land in one
    transaction.
    """
    task = Task(
        admission=admission,
        author=author,
        description=description,
        due_at=due_at,
        assignee=assignee,
        note=note,
        raised_at=utc_now(),
    )
    session.add(task)
    return task


def raise_tasks(
    session: Session,
    *,
    admission: Admission,
    author: User,
    items: list[WardRoundTaskPayload],
    note: NursingNote,
) -> list[Task]:
    """Build the Tasks a Ward Round Entry raised, and add them, without committing.

    Every assignee is resolved before anything is staged, so a bad assignee
    refuses the whole batch rather than leaving it half-staged. The caller commits
    once, so all the Tasks and their audit entries land or fail as one.
    """
    created: list[Task] = []
    assignees = [
        resolve_assignee(session, item.assignee_user_id) for item in items
    ]
    for item, assignee in zip(items, assignees):
        created.append(
            stage_task(
                session,
                admission=admission,
                author=author,
                description=item.description,
                due_at=as_utc(item.due_at) if item.due_at is not None else None,
                assignee=assignee,
                note=note,
            )
        )
    return created


def admission_tasks(session: Session, admission: Admission) -> list[Task]:
    """One Admission's Tasks in the order they were raised, including done ones.

    A done Task is part of the record, not deleted, so it stays here while it
    leaves the open list.
    """
    return list(
        session.scalars(
            select(Task)
            .where(Task.admission_id == admission.id)
            .order_by(Task.raised_at, Task.id)
        ).all()
    )


def ward_tasks(
    session: Session,
    *,
    assignee_user_id: int | None = None,
    include_done: bool = False,
) -> list[Task]:
    """Open Tasks across every open Admission, oldest due first.

    Only open Admissions are read: a discharged stay has left the working view, and
    its Tasks leave with it while its record is kept. ``include_done`` adds the done
    Tasks for the history; ``assignee_user_id`` narrows the list to one assignee,
    which is the "mine" filter and works whether the ward assigns patients or works
    a shared list. Ordered so work with the earliest deadline is first, with
    undated work last.
    """
    statement = (
        select(Task)
        .where(Task.admission.has(Admission.discharged_at.is_(None)))
        .order_by(Task.due_at.is_(None), Task.due_at, Task.id)
    )
    if not include_done:
        statement = statement.where(Task.completed_at.is_(None))
    if assignee_user_id is not None:
        statement = statement.where(Task.assignee_user_id == assignee_user_id)
    return list(session.scalars(statement).all())


def complete_task(session: Session, task: Task, *, actor: User) -> Task:
    """Mark a Task done, recording who and when, without committing.

    The instant is the server's clock at the moment of the action, never a value
    the caller supplies.

    Completion is a conditional update: ``completed_at`` is set only where it is
    still null, and the number of rows changed decides the outcome. Two completes
    racing for the same Task therefore cannot both succeed — the losing writer
    changes no row and is refused with ``409``, rather than overwriting the one
    recorded completion. The row is refreshed afterwards so the caller's object
    reflects the persisted state. The caller commits, so the update and its single
    audit entry land in one transaction.
    """
    result = cast(
        CursorResult,
        session.execute(
            update(Task)
            .where(Task.id == task.id, Task.completed_at.is_(None))
            .values(completed_at=utc_now(), completed_by_user_id=actor.id)
        ),
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=TASK_ALREADY_DONE_DETAIL,
        )
    session.refresh(task)
    return task


def assign_task(session: Session, task: Task, *, assignee: User | None) -> Task:
    """Set a Task's assignee, or clear it when ``assignee`` is None, without committing.

    Assignment is the one field a Task may change after it is raised, so reassigning
    or returning a Task to the shared list is the same act.
    """
    task.assignee = assignee
    return task


def clinical_staff(session: Session) -> list[User]:
    """The Clinical users a Task may be assigned to, in name order.

    Administrators are not clinical, so they are not offered as an assignee.
    """
    return list(
        session.scalars(
            select(User)
            .where(User.role == Role.clinical.value)
            .order_by(User.display_name, User.id)
        ).all()
    )


def staff_response(session: Session) -> StaffResponse:
    """The Clinical staff for the optional-assignee list."""
    return StaffResponse(
        users=[
            StaffMemberResponse(id=user.id, display_name=user.display_name)
            for user in clinical_staff(session)
        ]
    )


def is_overdue(task: Task, *, now: datetime) -> bool:
    """Whether an open Task is past its due time, measured against ``now``.

    A done Task is never shown as overdue: the work was done, so there is nothing
    outstanding to mark. An undated Task cannot be overdue. This is a comparison
    only; nothing acts on it.
    """
    if task.completed_at is not None or task.due_at is None:
        return False
    return as_utc(task.due_at) < now


def task_response(task: Task, *, now: datetime | None = None) -> TaskResponse:
    """Render one Task, with its condition and lateness derived at read time."""
    now = now or utc_now()
    return TaskResponse(
        id=task.id,
        admission_id=task.admission_id,
        patient=PatientResponse.model_validate(task.admission.patient),
        description=task.description,
        due_at=task.due_at,
        assignee=_actor(task.assignee),
        author=ActorResponse(
            id=task.author.id, display_name=task.author.display_name
        ),
        status=task.status,
        completed_by=_actor(task.completed_by),
        completed_at=task.completed_at,
        overdue=is_overdue(task, now=now),
        note_id=task.note_id,
    )


def admission_task_responses(
    session: Session, admission: Admission
) -> list[TaskResponse]:
    """One Admission's Tasks as the API serves them, oldest first, done included."""
    now = utc_now()
    return [
        task_response(task, now=now)
        for task in admission_tasks(session, admission)
    ]


def ward_task_responses(
    session: Session,
    *,
    assignee_user_id: int | None,
    include_done: bool,
) -> list[TaskResponse]:
    """The ward's cross-patient Task list, read against one clock."""
    now = utc_now()
    return [
        task_response(task, now=now)
        for task in ward_tasks(
            session,
            assignee_user_id=assignee_user_id,
            include_done=include_done,
        )
    ]


def _actor(user: User | None) -> ActorResponse | None:
    """A User as a shared actor shape, or None when there is no such user."""
    if user is None:
        return None
    return ActorResponse(id=user.id, display_name=user.display_name)
