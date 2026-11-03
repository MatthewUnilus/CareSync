"""The Queue: a sort over awaiting Encounters, never a stored sequence.

Ordering is Urgency Level first (High, then Medium, then Low) and arrival time
second, so equally urgent Encounters are first-in-first-out. The governing
Urgency Level is the **latest** Triage Assessment's Final Decision: ticket 03
creates exactly one Assessment per Encounter, and ticket 10's Re-assessment
appends another whose Final Decision wins.

An Encounter is awaiting while ``departed_at`` is null, and departed once the
Departure action records the instant. Only awaiting Encounters are read here.
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

    @property
    def override_flag(self) -> bool:
        """True when a human set a Final Decision different from the machine's.

        Its own state name, deliberately not a generic "flagged": ticket 08
        adds the unclassified flag as a separate signal, and tickets 10 and 14
        consume Override records rather than this derived boolean.
        """
        return UrgencyLevel(
            self.assessment.final_decision
        ) != UrgencyLevel(self.assessment.machine_recommendation)

    @property
    def unclassified_flag(self) -> bool:
        """True when the fallback provider could not classify the complaint.

        Distinct from ``override_flag``: an Override is a human disagreement
        with a classified recommendation, while this says the recommendation
        itself came from the safety layer's default and needs review.
        """
        return bool(self.assessment.unclassified)


@dataclass(frozen=True)
class AdministratorQueueRow:
    """One row of the Administrator's dense Queue table.

    This is a read-only projection of the same awaiting Queue the Clinical
    board shows. It deliberately carries only the columns the table renders,
    so the Administrator surface has no intake or Assessment detail to act on.
    """

    encounter_id: int
    arrived_at: datetime
    waiting_seconds: int
    urgency_level: UrgencyLevel
    patient_name: str
    presenting_complaint: str
    machine_recommendation: UrgencyLevel
    final_decision: UrgencyLevel

    @property
    def final_decision_differs(self) -> bool:
        return self.final_decision != self.machine_recommendation


def awaiting_queue(session: Session, now: datetime) -> list[QueueEntry]:
    """Every awaiting Encounter that has an Assessment, in Queue order."""
    encounters = session.scalars(
        select(Encounter)
        .where(Encounter.departed_at.is_(None))
        .options(
            selectinload(Encounter.assessments).selectinload(
                TriageAssessment.overrides
            )
        )
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


def administrator_queue(
    session: Session, now: datetime
) -> list[AdministratorQueueRow]:
    """The same awaiting Queue, projected for the Administrator dashboard.

    Reading this does not change the Queue and exposes no clinical action.
    Because it is derived on every call, a later Override (which changes the
    governing Final Decision) or a Departure is visible on the next poll.
    """
    return [
        AdministratorQueueRow(
            encounter_id=entry.encounter.id,
            arrived_at=entry.encounter.arrived_at,
            waiting_seconds=entry.waiting_seconds,
            urgency_level=UrgencyLevel(entry.assessment.final_decision),
            patient_name=entry.encounter.patient.full_name,
            presenting_complaint=entry.encounter.presenting_complaint,
            machine_recommendation=UrgencyLevel(
                entry.assessment.machine_recommendation
            ),
            final_decision=UrgencyLevel(entry.assessment.final_decision),
        )
        for entry in awaiting_queue(session, now)
    ]


def _waiting_seconds(encounter: Encounter, now: datetime) -> int:
    elapsed = (as_utc(now) - as_utc(encounter.arrived_at)).total_seconds()
    return max(0, int(elapsed))
