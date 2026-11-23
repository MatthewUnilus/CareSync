"""Investigations: the tests a doctor requested, tracked to result and review.

An Investigation is recorded against an Admission by a Clinical user and followed
through four states -- requested, sample taken, result available, reviewed
(CONTEXT.md, "Investigation", ADR 0012). It tracks that a result arrived and that
somebody reviewed it; it is *not* a results viewer. The result note is free text,
recorded as the laboratory gave it: nothing here reads a value, flags an abnormal
result or suggests anything from one, so no reference range is held and the
Observation chart's range logic is deliberately not imported.

The state set lives once, in ``app.models`` beside the entity (``InvestigationState``)
and is derived from the row's instants rather than stored a second time. Moves go
in one order only -- requested to sample taken to result available to reviewed --
and any out-of-order or repeated move is refused with ``409`` and nothing written.
Marking a result reviewed is the accountable act and records who and when.

Two worklists are one read of the table, filtered two ways: results awaiting
review, and tests still awaiting a result (the chase list). Both read the ward's
open admissions only, because a discharged stay has left the working view while
its record is kept.

The functions that stage a change never commit: the route commits, so the change
and its single audit entry land in one transaction (ADR 0007).
"""

from __future__ import annotations

from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, CursorResult, select, update
from sqlalchemy.orm import Session

from app.models import (
    Admission,
    Investigation,
    User,
    investigation_state,
)
from app.schemas import (
    ActorResponse,
    InvestigationResponse,
    PatientResponse,
)
from app.timeutils import utc_now

#: Raised when an unknown Investigation is named. An id that resolves to nothing
#: is a missing resource rather than a bad request.
INVESTIGATION_NOT_FOUND_DETAIL = "Investigation not found"

#: Raised when a sample is taken for an Investigation that is not `requested`.
#: Covers an out-of-order move and a repeated one with the same refusal.
INVESTIGATION_NOT_REQUESTED_DETAIL = (
    "A sample can only be taken for a requested Investigation"
)

#: Raised when a result is recorded before a sample has been taken, or after one
#: has already been recorded.
INVESTIGATION_NO_SAMPLE_DETAIL = (
    "A result can only be recorded once a sample has been taken"
)

#: Raised when a result is reviewed before it is available, or reviewed twice.
#: A result cannot be reviewed before it is available.
INVESTIGATION_NO_RESULT_DETAIL = (
    "A result can only be reviewed once it is available"
)


def _refuse(detail: str) -> HTTPException:
    """A ``409`` for a move that does not fit the current state and writes nothing."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def stage_investigation(
    session: Session,
    *,
    admission: Admission,
    actor: User,
    test_name: str,
    instructed_by: str | None = None,
) -> Investigation:
    """Build one Investigation in the ``requested`` state and add it, without committing.

    ``actor`` is the Clinical user recording it; ``instructed_by`` is the doctor
    who requested the test as free text, because the doctor is not a user of this
    system. The caller commits, so the Investigation and its single audit entry
    land in one transaction.
    """
    investigation = Investigation(
        admission=admission,
        test_name=test_name,
        instructed_by=instructed_by,
        requested_by=actor,
        requested_at=utc_now(),
    )
    session.add(investigation)
    return investigation


def mark_sample_taken(session: Session, investigation: Investigation) -> Investigation:
    """Move an Investigation from ``requested`` to ``sample_taken``, without committing.

    The instant is the server's clock at the moment of the action. The move is a
    conditional update: ``sample_taken_at`` is set only where it is still null, and
    the number of rows changed decides the outcome. Two moves racing for the same
    Investigation therefore cannot both succeed -- the losing writer changes no
    row and is refused with ``409``, rather than overwriting the one recorded
    instant. The row is refreshed afterwards so the caller's object reflects the
    persisted state. The caller commits, so the move and its single audit entry
    land in one transaction.
    """
    result = cast(
        CursorResult,
        session.execute(
            update(Investigation)
            .where(
                Investigation.id == investigation.id,
                Investigation.sample_taken_at.is_(None),
            )
            .values(sample_taken_at=utc_now())
        ),
    )
    if result.rowcount == 0:
        raise _refuse(INVESTIGATION_NOT_REQUESTED_DETAIL)
    session.refresh(investigation)
    return investigation


def record_result(
    session: Session, investigation: Investigation, *, result_note: str
) -> Investigation:
    """Move an Investigation from ``sample_taken`` to ``result_available``.

    ``result_note`` is free text recorded verbatim as the laboratory gave it; it
    is never parsed or interpreted. The instant is the server's clock. The move is
    a conditional update: a result is set only where a sample has been taken and
    the result is still absent, so an out-of-order or repeated move changes no row
    and is refused with ``409``. Two moves racing for the same Investigation
    cannot both succeed. The row is refreshed afterwards, and the caller commits,
    so the move and its single audit entry land in one transaction.
    """
    result = cast(
        CursorResult,
        session.execute(
            update(Investigation)
            .where(
                Investigation.id == investigation.id,
                Investigation.sample_taken_at.is_not(None),
                Investigation.result_available_at.is_(None),
            )
            .values(result_note=result_note, result_available_at=utc_now())
        ),
    )
    if result.rowcount == 0:
        raise _refuse(INVESTIGATION_NO_SAMPLE_DETAIL)
    session.refresh(investigation)
    return investigation


def review_result(
    session: Session, investigation: Investigation, *, reviewer: User
) -> Investigation:
    """Move an Investigation from ``result_available`` to ``reviewed``, without committing.

    The review is the accountable act: it records the reviewer and the instant.
    The move is a conditional update: the review is recorded only where a result is
    available and no review exists, so a result cannot be reviewed before it is
    available and is reviewed once -- an out-of-order or repeated move changes no
    row and is refused with ``409``. Two reviewers racing cannot both succeed, and
    the loser's act is not recorded. The row is refreshed afterwards, and the
    caller commits, so the review and its single audit entry land in one
    transaction.
    """
    result = cast(
        CursorResult,
        session.execute(
            update(Investigation)
            .where(
                Investigation.id == investigation.id,
                Investigation.result_available_at.is_not(None),
                Investigation.reviewed_at.is_(None),
            )
            .values(reviewed_at=utc_now(), reviewed_by_user_id=reviewer.id)
        ),
    )
    if result.rowcount == 0:
        raise _refuse(INVESTIGATION_NO_RESULT_DETAIL)
    session.refresh(investigation)
    return investigation


def admission_investigations(
    session: Session, admission: Admission
) -> list[Investigation]:
    """One Admission's Investigations, newest first, in every state."""
    return list(
        session.scalars(
            select(Investigation)
            .where(Investigation.admission_id == admission.id)
            .order_by(Investigation.requested_at.desc(), Investigation.id.desc())
        ).all()
    )


def _open_admissions() -> ColumnElement[bool]:
    """Investigations whose Admission is still open: the working views' set."""
    return Investigation.admission.has(Admission.discharged_at.is_(None))


def awaiting_review(session: Session) -> list[Investigation]:
    """Every result awaiting review across the ward's open stays, longest waiting first.

    A result that has arrived and not been reviewed, so nothing goes unread. One
    of the two filters over the same read; a discharged stay has left the working
    view. Ordered oldest result first, so the ward can clear them in the order
    they arrived.
    """
    return list(
        session.scalars(
            select(Investigation)
            .where(
                _open_admissions(),
                Investigation.result_available_at.is_not(None),
                Investigation.reviewed_at.is_(None),
            )
            .order_by(Investigation.result_available_at, Investigation.id)
        ).all()
    )


def awaiting_result(session: Session) -> list[Investigation]:
    """Every test still awaiting a result across the open ward: the chase list.

    The requested and sample-taken Investigations, so the nurse knows what to
    chase. The other filter over the same read; a discharged stay has left the
    working view. Ordered oldest request first, so the longest-outstanding test
    is at the top.
    """
    return list(
        session.scalars(
            select(Investigation)
            .where(
                _open_admissions(),
                Investigation.result_available_at.is_(None),
                Investigation.reviewed_at.is_(None),
            )
            .order_by(Investigation.requested_at, Investigation.id)
        ).all()
    )


def investigation_response(investigation: Investigation) -> InvestigationResponse:
    """Render one Investigation, with its state derived at read time."""
    return InvestigationResponse(
        id=investigation.id,
        admission_id=investigation.admission_id,
        patient=PatientResponse.model_validate(investigation.admission.patient),
        test_name=investigation.test_name,
        instructed_by=investigation.instructed_by,
        requested_at=investigation.requested_at,
        requested_by=ActorResponse(
            id=investigation.requested_by.id,
            display_name=investigation.requested_by.display_name,
        ),
        state=investigation_state(investigation),
        sample_taken_at=investigation.sample_taken_at,
        result_available_at=investigation.result_available_at,
        result_note=investigation.result_note,
        reviewed_at=investigation.reviewed_at,
        reviewed_by=_actor(investigation.reviewed_by),
    )


def investigation_responses(
    investigations: list[Investigation],
) -> list[InvestigationResponse]:
    """The Investigations as the API serves them, in the order given."""
    return [investigation_response(item) for item in investigations]


def _actor(user: User | None) -> ActorResponse | None:
    """A User as the shared actor shape, or None when there is no such user."""
    if user is None:
        return None
    return ActorResponse(id=user.id, display_name=user.display_name)
