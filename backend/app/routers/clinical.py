from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments import create_triage_assessment
from app.deps import DbSession, require_role
from app.intake import ensure_intake_editable
from app.models import Encounter, Override, Patient, Role, TriageAssessment, User
from app.override_reasons import OVERRIDE_REASONS
from app.overrides import perform_override
from app.patients import find_or_create_patient
from app.queue import awaiting_queue
from app.schemas import (
    AssessmentResponse,
    AssessmentSnapshot,
    EncounterCreateRequest,
    EncounterListResponse,
    EncounterResponse,
    IntakePayload,
    OverrideActorResponse,
    OverrideRecordResponse,
    OverrideReasonsResponse,
    OverrideRequest,
    PatientRegistrationRequest,
    PatientResponse,
    QueueEntryResponse,
    QueueResponse,
)
from app.timeutils import utc_now

router = APIRouter(prefix="/api/clinical", tags=["clinical"])

ClinicalUser = Annotated[User, Depends(require_role(Role.clinical))]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@router.get("/access")
def clinical_access(user: ClinicalUser) -> dict[str, str]:
    return {
        "role": Role.clinical.value,
        "message": "Clinical access granted",
    }


@router.post(
    "/patients",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_patient(
    payload: PatientRegistrationRequest,
    response: Response,
    db: DbSession,
    user: ClinicalUser,
) -> Patient:
    """Register a Patient, or reuse the existing record for the same person.

    ``201 Created`` when a new Patient is registered, ``200 OK`` when an
    existing record is reused.
    """
    patient, created = find_or_create_patient(
        db,
        full_name=payload.full_name,
        age=payload.age,
        sex=payload.sex,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return patient


@router.post(
    "/encounters",
    response_model=EncounterResponse,
    status_code=status.HTTP_201_CREATED,
)
def open_encounter(
    payload: EncounterCreateRequest,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    encounter = Encounter(patient_id=patient.id)
    _apply_intake(encounter, payload.intake)
    db.add(encounter)
    db.flush()
    assessment = create_triage_assessment(db, encounter)
    db.commit()
    return _encounter_response(encounter, assessment)


@router.get("/encounters", response_model=EncounterListResponse)
def list_recent_encounters(
    db: DbSession,
    user: ClinicalUser,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> EncounterListResponse:
    """Encounters most recently opened first, for reviewing a saved intake.

    This is a recency list, not the Queue: it is not ordered by Urgency Level
    and does not filter on awaiting versus departed.
    """
    encounters = db.scalars(
        select(Encounter)
        .order_by(Encounter.arrived_at.desc(), Encounter.id.desc())
        .limit(limit)
    ).all()
    return EncounterListResponse(
        encounters=[_encounter_response(encounter) for encounter in encounters]
    )


@router.get("/queue", response_model=QueueResponse)
def get_queue(db: DbSession, user: ClinicalUser) -> QueueResponse:
    """The Queue: awaiting Encounters by Urgency Level, then arrival time.

    Time waiting is computed from ``arrived_at`` at the instant of the read, so
    the same stored row reports a different wait on the next poll.
    """
    now = utc_now()
    entries = awaiting_queue(db, now)
    return QueueResponse(
        as_of=now,
        entries=[
            QueueEntryResponse(
                encounter_id=entry.encounter.id,
                arrived_at=entry.encounter.arrived_at,
                waiting_seconds=entry.waiting_seconds,
                urgency_level=entry.assessment.final_decision,
                patient=PatientResponse.model_validate(entry.encounter.patient),
                intake=_intake_payload(entry.encounter),
                assessment=_assessment_response(entry.assessment),
                override_flag=entry.override_flag,
            )
            for entry in entries
        ],
    )


@router.get("/override-reasons", response_model=OverrideReasonsResponse)
def get_override_reasons(user: ClinicalUser) -> OverrideReasonsResponse:
    """The fixed Override Reason set, for the card's Override form."""
    return OverrideReasonsResponse(reasons=list(OVERRIDE_REASONS))


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
def get_encounter(
    encounter_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    return _encounter_response(_get_encounter(db, encounter_id))


@router.post(
    "/encounters/{encounter_id}/override",
    response_model=EncounterResponse,
)
def override_final_decision(
    encounter_id: int,
    payload: OverrideRequest,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """Set a different Final Decision on the governing Triage Assessment.

    The Machine Recommendation is not writable through this route; the
    Override records the actor and reason, and the Queue reorders on the next
    read because it sorts on Final Decision.
    """
    encounter = _get_encounter(db, encounter_id)
    perform_override(
        db,
        encounter,
        assessment_id=payload.assessment_id,
        final_decision=payload.final_decision,
        reason=payload.reason,
        free_text=payload.free_text,
        actor=user,
    )
    db.commit()
    return _encounter_response(encounter)


@router.put("/encounters/{encounter_id}/intake", response_model=EncounterResponse)
def correct_intake(
    encounter_id: int,
    payload: IntakePayload,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """Replace the intake on an Encounter, while no Triage Assessment exists."""
    encounter = _get_encounter(db, encounter_id)
    ensure_intake_editable(db, encounter)
    _apply_intake(encounter, payload)
    db.commit()
    return _encounter_response(encounter)


def _get_encounter(db: Session, encounter_id: int) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encounter not found",
        )
    return encounter


def _apply_intake(encounter: Encounter, intake: IntakePayload) -> None:
    encounter.presenting_complaint = intake.presenting_complaint
    encounter.pain_level = intake.pain_level
    encounter.illness_duration_hours = intake.illness_duration_hours
    encounter.temperature_c = intake.temperature_c
    encounter.heart_rate_bpm = intake.heart_rate_bpm
    encounter.systolic_bp = intake.blood_pressure.systolic
    encounter.diastolic_bp = intake.blood_pressure.diastolic
    encounter.oxygen_saturation_percent = intake.oxygen_saturation_percent
    encounter.notes = intake.notes


def _encounter_response(
    encounter: Encounter,
    assessment: TriageAssessment | None = None,
) -> EncounterResponse:
    if assessment is None:
        assessment = (
            encounter.assessments[-1] if encounter.assessments else None
        )
    return EncounterResponse(
        id=encounter.id,
        arrived_at=encounter.arrived_at,
        patient=PatientResponse.model_validate(encounter.patient),
        intake=_intake_payload(encounter),
        assessment=(
            _assessment_response(assessment) if assessment is not None else None
        ),
    )


def _intake_payload(encounter: Encounter) -> IntakePayload:
    return IntakePayload(
        presenting_complaint=encounter.presenting_complaint,
        pain_level=encounter.pain_level,
        illness_duration_hours=encounter.illness_duration_hours,
        temperature_c=encounter.temperature_c,
        heart_rate_bpm=encounter.heart_rate_bpm,
        blood_pressure={
            "systolic": encounter.systolic_bp,
            "diastolic": encounter.diastolic_bp,
        },
        oxygen_saturation_percent=encounter.oxygen_saturation_percent,
        notes=encounter.notes,
    )


def _assessment_response(assessment: TriageAssessment) -> AssessmentResponse:
    groups = [
        group
        for group in assessment.recognised_symptom_groups.split(",")
        if group
    ]
    return AssessmentResponse(
        id=assessment.id,
        assessed_at=assessment.assessed_at,
        machine_recommendation=assessment.machine_recommendation,
        final_decision=assessment.final_decision,
        recognised_symptom_groups=groups,
        override=_override_response(
            assessment.overrides[-1] if assessment.overrides else None
        ),
        snapshot=AssessmentSnapshot(
            presenting_complaint=assessment.presenting_complaint,
            age=assessment.patient_age,
            pain_level=assessment.pain_level,
            illness_duration_hours=assessment.illness_duration_hours,
            temperature_c=assessment.temperature_c,
            heart_rate_bpm=assessment.heart_rate_bpm,
            blood_pressure={
                "systolic": assessment.systolic_bp,
                "diastolic": assessment.diastolic_bp,
            },
            oxygen_saturation_percent=assessment.oxygen_saturation_percent,
            notes=assessment.notes,
        ),
    )


def _override_response(override: Override | None) -> OverrideRecordResponse | None:
    if override is None:
        return None
    return OverrideRecordResponse(
        reason=override.reason,
        free_text=override.free_text,
        performed_at=override.performed_at,
        performed_by=OverrideActorResponse(
            id=override.actor.id,
            display_name=override.actor.display_name,
        ),
    )
