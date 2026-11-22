"""The Ward Board: the ward's open Admissions, ordered by outstanding work.

The board is a read model, recalculated on every read and storing nothing. It is
derived from the rows that record what happened, so a change to the record shows
in the very next request. It is a count of what the record shows is outstanding,
not a score and not a clinical judgement, and it does not decide who is treated
first (CONTEXT.md, "Ward Board").

Every count is a function here, and each returns zero while the feature it counts
does not exist yet. The later ward tickets each replace one function rather than
rewriting the board — medicine (ticket 34), tasks (ticket 33) and investigations
(ticket 36) — so this ticket lands before them and still works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Admission, Observation


@dataclass(frozen=True)
class WardBoardEntry:
    """One open Admission and the outstanding work the record shows against it."""

    admission: Admission
    latest_observation: Observation | None
    outstanding_medication_count: int
    overdue_medication_count: int
    due_medication_count: int
    open_task_count: int
    unreviewed_result_count: int


def overdue_medication_count(session: Session, admission: Admission) -> int:
    """Doses past their due time. Medicine fills this in; zero until then."""
    return 0


def due_medication_count(session: Session, admission: Admission) -> int:
    """Doses due now. Medicine fills this in; zero until then."""
    return 0


def outstanding_medication_count(session: Session, admission: Admission) -> int:
    """Doses not yet given. Medicine fills this in; zero until then."""
    return 0


def unreviewed_result_count(session: Session, admission: Admission) -> int:
    """Results awaiting review. Investigations fill this in; zero until then."""
    return 0


def open_task_count(session: Session, admission: Admission) -> int:
    """Tasks not yet done. Tasks fill this in; zero until then."""
    return 0


def latest_observation(
    session: Session, admission: Admission
) -> Observation | None:
    """The Patient's most recent Observation, or None when none is charted.

    A Patient's Observations are one time series across every visit and stay
    (ADR 0008), so the board shows the latest reading for the Patient, not one
    narrowed to this stay.
    """
    return session.scalar(
        select(Observation)
        .where(Observation.patient_id == admission.patient_id)
        .order_by(Observation.taken_at.desc(), Observation.id.desc())
        .limit(1)
    )


def open_admissions(session: Session) -> list[Admission]:
    """Every stay that has not been discharged, the board's set."""
    return list(
        session.scalars(
            select(Admission).where(Admission.discharged_at.is_(None))
        ).all()
    )


def entry_for(session: Session, admission: Admission) -> WardBoardEntry:
    """Build one board entry for an admission, reading each count from the record."""
    return WardBoardEntry(
        admission=admission,
        latest_observation=latest_observation(session, admission),
        outstanding_medication_count=outstanding_medication_count(
            session, admission
        ),
        overdue_medication_count=overdue_medication_count(session, admission),
        due_medication_count=due_medication_count(session, admission),
        open_task_count=open_task_count(session, admission),
        unreviewed_result_count=unreviewed_result_count(session, admission),
    )


def board(session: Session) -> list[WardBoardEntry]:
    """The ward's open admissions, ordered by outstanding work.

    The order follows CONTEXT.md: overdue medication doses first, then doses due
    now, then results awaiting review, then open Tasks, with bed order breaking
    ties. Each category is compared on its count, so the patient with more
    overdue doses sits above one with fewer before the next category is reached.
    """
    entries = [entry_for(session, admission) for admission in open_admissions(session)]
    entries.sort(key=_board_order)
    return entries


def _board_order(entry: WardBoardEntry) -> tuple[int, int, int, int, tuple, int]:
    """The sort key: descending work in category order, then bed, then row id."""
    admission = entry.admission
    return (
        -entry.overdue_medication_count,
        -entry.due_medication_count,
        -entry.unreviewed_result_count,
        -entry.open_task_count,
        _bed_order(admission.bed),
        admission.id,
    )


def _bed_order(bed: str) -> tuple[int, int, str]:
    """A stable bed order: numeric beds first, in number, then the rest by name.

    A plain string sort would place bed "12" before bed "3"; splitting off a
    leading number keeps a bay of numbered beds in the order a reader expects.
    """
    stripped = bed.strip()
    match = re.match(r"^(\d+)", stripped)
    if match is not None:
        return (0, int(match.group(1)), stripped.casefold())
    return (1, 0, stripped.casefold())
