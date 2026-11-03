"""Rules for correcting the intake captured on an Encounter.

Intake may be corrected only while no Triage Assessment exists for the
Encounter: once an assessment has run, its inputs are a record of what the
recommendation was made from and must not move underneath it.

Intake is complete as soon as the Encounter exists (ticket 02), so opening an
Encounter creates its first Assessment in the same transaction. In practice a
correction is therefore refused with ``409 Conflict`` for every Encounter
created by this build; the route keeps the guard so a failed assessment can
never silently leave the intake editable.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter, TriageAssessment

INTAKE_LOCKED_DETAIL = (
    "Intake cannot be corrected once a Triage Assessment exists for the Encounter"
)


def has_triage_assessment(session: Session, encounter: Encounter) -> bool:
    return (
        session.scalar(
            select(TriageAssessment.id)
            .where(TriageAssessment.encounter_id == encounter.id)
            .limit(1)
        )
        is not None
    )


def ensure_intake_editable(session: Session, encounter: Encounter) -> None:
    if has_triage_assessment(session, encounter):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=INTAKE_LOCKED_DETAIL,
        )
