"""Re-assessment: a Clinical user asks for a fresh Triage Assessment.

Re-assessment is an explicit act. Nothing here schedules, polls, times out or
reacts to a Queue read: the only caller is
``POST /api/clinical/encounters/{id}/reassessment``, so no Assessment is ever
appended except when a person asks for one.

The action captures the Encounter's **current** intake — the condition may have
changed since the last Assessment — and runs the engine again, so the new
Assessment has a Machine Recommendation of its own. It then records on the new
row which Assessment it superseded: the one that was governing. That single
link is enough to reconstruct the sequence, and no earlier row is touched, so
every previous snapshot and Override stays exactly as it was.

The Queue's governing Assessment is the most recent one (highest id); after this
call it is the row appended here. An Encounter's position therefore moves only
when a person explicitly re-assesses or overrides it.
"""

from sqlalchemy.orm import Session

from app.assessments import create_triage_assessment
from app.departures import REASSESSMENT_DEPARTED_DETAIL, ensure_awaiting
from app.intake import apply_intake
from app.models import Encounter, TriageAssessment
from app.schemas import IntakePayload


def perform_reassessment(
    session: Session,
    encounter: Encounter,
    *,
    intake: IntakePayload,
) -> TriageAssessment:
    """Append a new Assessment for the intake supplied, without committing.

    The caller commits, so the Encounter's current intake, the new Assessment
    and its supersession link land in one transaction.
    """
    ensure_awaiting(encounter, REASSESSMENT_DEPARTED_DETAIL)
    apply_intake(encounter, intake)

    superseded = encounter.assessments[-1] if encounter.assessments else None
    return create_triage_assessment(session, encounter, supersedes=superseded)
