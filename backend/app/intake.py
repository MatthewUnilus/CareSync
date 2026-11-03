"""Rules for correcting the intake captured on an Encounter.

Intake may be corrected only while no Triage Assessment exists for the
Encounter: once an assessment has run, its inputs are a record of what the
recommendation was made from and must not move underneath it.

No Triage Assessment can exist yet (ticket 03 introduces it), so
``has_triage_assessment`` currently answers ``False`` for every Encounter. The
correction route already calls ``ensure_intake_editable``, so ticket 03 only has
to replace the body of ``has_triage_assessment`` with a lookup; the API contract
(``409 Conflict``) is already in place and tested.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Encounter

INTAKE_LOCKED_DETAIL = (
    "Intake cannot be corrected once a Triage Assessment exists for the Encounter"
)


def has_triage_assessment(session: Session, encounter: Encounter) -> bool:
    return False


def ensure_intake_editable(session: Session, encounter: Encounter) -> None:
    if has_triage_assessment(session, encounter):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=INTAKE_LOCKED_DETAIL,
        )
