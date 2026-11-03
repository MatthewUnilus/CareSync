"""Performing an Override: a Clinical user disagrees with the engine.

The rules live here rather than in the route so the API-level tests exercise
one place and ticket 10's Re-assessment can reuse the same guard later:

* only an awaiting Encounter may be overridden;
* only its governing Assessment — the most recent one — may be overridden;
* the new Final Decision must actually differ from the Machine Recommendation.

The Override itself is an append-only record of who and why. The Machine
Recommendation is never written by this path; only ``final_decision`` moves.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Encounter, Override, TriageAssessment, User
from app.override_reasons import OverrideReason
from app.prioritisation import UrgencyLevel
from app.timeutils import utc_now

ENCOUNTER_DEPARTED_DETAIL = "A departed Encounter cannot be overridden"
NOT_GOVERNING_DETAIL = (
    "Only the governing (most recent) Triage Assessment of the Encounter "
    "can be overridden"
)
DECISION_UNCHANGED_DETAIL = (
    "An Override must set a Final Decision different from the Machine "
    "Recommendation"
)


def perform_override(
    session: Session,
    encounter: Encounter,
    *,
    assessment_id: int,
    final_decision: UrgencyLevel,
    reason: OverrideReason,
    free_text: str | None,
    actor: User,
) -> TriageAssessment:
    """Apply an Override and append its record, without committing.

    The caller commits; this keeps the Assessment update and the Override row
    in one transaction.
    """
    if encounter.departed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ENCOUNTER_DEPARTED_DETAIL,
        )

    assessment = session.get(TriageAssessment, assessment_id)
    governing = encounter.assessments[-1] if encounter.assessments else None
    if (
        assessment is None
        or assessment.encounter_id != encounter.id
        or governing is None
        or governing.id != assessment.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=NOT_GOVERNING_DETAIL,
        )

    if final_decision.value == assessment.machine_recommendation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DECISION_UNCHANGED_DETAIL,
        )

    record = Override(
        assessment=assessment,
        actor=actor,
        reason=reason.value,
        free_text=free_text,
        performed_at=utc_now(),
    )
    session.add(record)
    assessment.final_decision = final_decision.value
    return assessment
