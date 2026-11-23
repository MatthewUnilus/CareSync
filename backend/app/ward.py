"""The Ward Board: the ward's open Admissions, ordered by outstanding work.

The board is a read model, recalculated on every read and storing nothing. It is
derived from the rows that record what happened, so a change to the record shows
in the very next request. It is a count of what the record shows is outstanding,
not a score and not a clinical judgement, and it does not decide who is treated
first (CONTEXT.md, "Ward Board").

One read captures one clock (``utc_now``) and passes it down, so every count on a
board is measured against the same instant. The medication figures for an
admission are read through one seam, ``medication_counts``, which derives all
three from a single pass of that admission's schedule rather than scanning once
per count. The open Task count (ticket 33) is read the same way; investigations
(ticket 36) fill in their own count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import medications
from app.models import Admission, Observation, Task
from app.timeutils import utc_now


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


def medication_counts(
    session: Session,
    admission: Admission,
    *,
    now: datetime | None = None,
) -> medications.MedicationCounts:
    """The three medication figures for one admission, from one schedule read.

    The single seam the board reads its medication counts through: one clock for
    the read and one pass of the admission's schedule, rather than a scan per
    count. ``app.medications`` owns the round-time convention and the derivation;
    nothing is stored for a dose.
    """
    return medications.medication_counts(session, admission, now=now)


def unreviewed_result_count(session: Session, admission: Admission) -> int:
    """Results awaiting review. Investigations fill this in; zero until then."""
    return 0


def open_task_count(session: Session, admission: Admission) -> int:
    """Tasks on this Admission not yet done, counted from the record.

    The figure the Ward Board shows in the open Tasks column: a Task leaves this
    count when it is marked done, not when it is raised. A discharged Admission
    has left the board, so its Tasks are never asked for here.
    """
    return session.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.admission_id == admission.id,
            Task.completed_at.is_(None),
        )
    )


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


def entry_for(
    session: Session, admission: Admission, *, now: datetime | None = None
) -> WardBoardEntry:
    """Build one board entry, reading each count from the record against one clock.

    The medication figures come from a single call to ``medication_counts``, so a
    board read scans each admission's schedule once rather than once per count.
    """
    now = now or utc_now()
    counts = medication_counts(session, admission, now=now)
    return WardBoardEntry(
        admission=admission,
        latest_observation=latest_observation(session, admission),
        outstanding_medication_count=counts.outstanding,
        overdue_medication_count=counts.overdue,
        due_medication_count=counts.due,
        open_task_count=open_task_count(session, admission),
        unreviewed_result_count=unreviewed_result_count(session, admission),
    )


def board(session: Session) -> list[WardBoardEntry]:
    """The ward's open admissions, ordered by outstanding work.

    The order follows CONTEXT.md: overdue medication doses first, then doses due
    now, then results awaiting review, then open Tasks, with bed order breaking
    ties. Each category is compared on its count, so the patient with more
    overdue doses sits above one with fewer before the next category is reached.
    One clock is captured here and used for every entry, so the whole board is
    measured at a single instant.
    """
    now = utc_now()
    entries = [
        entry_for(session, admission, now=now)
        for admission in open_admissions(session)
    ]
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
