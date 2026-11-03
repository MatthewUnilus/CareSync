"""The Queue: a sort over awaiting Encounters, never a stored sequence.

Ordering is Urgency Level first (High, then Medium, then Low) and arrival time
second, so equally urgent Encounters are first-in-first-out. The governing
Urgency Level is the **latest** Triage Assessment's Final Decision: ticket 03
creates exactly one Assessment per Encounter, and ticket 10's Re-assessment
appends another whose Final Decision wins.

An Encounter is awaiting while ``departed_at`` is null. Ticket 11 records
departures; until then every Encounter is awaiting.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Encounter, TriageAssessment
from app.prioritisation import URGENCY_RANK, UrgencyLevel
from app.timeutils import as_utc


@dataclass(frozen=True)
class QueueEntry:
    encounter: Encounter
    assessment: TriageAssessment
    waiting_seconds: int


def awaiting_queue(session: Session, now: datetime) -> list[QueueEntry]:
    """Every awaiting Encounter that has an Assessment, in Queue order."""
    encounters = session.scalars(
        select(Encounter)
        .where(Encounter.departed_at.is_(None))
        .options(selectinload(Encounter.assessments))
    ).all()

    entries: list[QueueEntry] = []
    for encounter in encounters:
        if not encounter.assessments:
            # Not yet assessed, so it has no Urgency Level and no place in the
            # Queue. In this ticket intake always creates one when opened.
            continue
        assessment = encounter.assessments[-1]
        entries.append(
            QueueEntry(
                encounter=encounter,
                assessment=assessment,
                waiting_seconds=_waiting_seconds(encounter, now),
            )
        )

    entries.sort(
        key=lambda entry: (
            URGENCY_RANK[UrgencyLevel(entry.assessment.final_decision)],
            as_utc(entry.encounter.arrived_at),
            entry.encounter.id,
        )
    )
    return entries


def _waiting_seconds(encounter: Encounter, now: datetime) -> int:
    elapsed = (as_utc(now) - as_utc(encounter.arrived_at)).total_seconds()
    return max(0, int(elapsed))
