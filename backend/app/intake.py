"""The intake captured on an Encounter, and when it may be corrected.

Intake may be corrected only while no Triage Assessment exists for the
Encounter: once an assessment has run, its inputs are a record of what the
recommendation was made from and must not move underneath it.

Intake is complete as soon as the Encounter exists (ticket 02), so opening an
Encounter creates its first Assessment in the same transaction. In practice a
correction is therefore refused with ``409 Conflict`` for every Encounter
created by this build; the route keeps the guard so a failed assessment can
never silently leave the intake editable.

The one other way the intake moves is a Re-assessment (ticket 10), which
captures the Encounter's current condition as an explicit new act and freezes
it into a new Assessment. That path does not rewrite history: the earlier
Assessment's snapshot is untouched. See ``app.reassessments``.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter, TriageAssessment
from app.schemas import IntakePayload

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


def apply_intake(encounter: Encounter, intake: IntakePayload) -> None:
    """Write the supplied intake onto the Encounter, without committing.

    Used when the Encounter is opened and when a Re-assessment captures the
    current condition. The columns hold the assessment *about to be made*; each
    Assessment keeps its own frozen snapshot of what it ran on.
    """
    encounter.presenting_complaint = intake.presenting_complaint
    encounter.pain_level = intake.pain_level
    encounter.illness_duration_hours = intake.illness_duration_hours
    encounter.temperature_c = intake.temperature_c
    encounter.heart_rate_bpm = intake.heart_rate_bpm
    encounter.systolic_bp = intake.blood_pressure.systolic
    encounter.diastolic_bp = intake.blood_pressure.diastolic
    encounter.oxygen_saturation_percent = intake.oxygen_saturation_percent
    encounter.notes = intake.notes
