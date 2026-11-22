from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_entry
from app.audit_actions import AuditAction
from app.departures import encounter_status, end_encounter
from app.deps import DbSession, require_role
from app.intake import apply_visit_reason
from app.models import Encounter, Patient, Role, User
from app.patients import find_or_create_patient, search_patients as patient_search
from app.schemas import (
    EncounterCreateRequest,
    EncounterListResponse,
    EncounterResponse,
    PatientHistoryResponse,
    PatientRegistrationRequest,
    PatientResponse,
    PatientSearchResponse,
    VisitReasonPayload,
)

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

    The route commits, so the Patient row and its audit entry land in one
    transaction. ``find_or_create_patient`` no longer commits internally for
    exactly this reason: a re-registration reuses a record, so it is not a
    mutation and writes no audit entry.
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
    else:
        record_audit_entry(
            db,
            actor=user,
            action=AuditAction.register_patient,
            patient=patient,
        )
    db.commit()
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
    apply_visit_reason(encounter, payload.intake)
    db.add(encounter)
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.open_encounter,
        patient=patient,
        encounter=encounter,
    )
    db.commit()
    return _encounter_response(encounter)


@router.get("/patients", response_model=PatientSearchResponse)
def search_patients(
    db: DbSession,
    user: ClinicalUser,
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PatientSearchResponse:
    """Find Patients by a fragment of their name or contact number.

    This is not identity resolution. ``app.patients`` matches an identity only
    when the whole name and the whole phone are both equal; a search matches
    part of either and returns candidates for a human to choose between. A
    blank query returns nothing, so the route is never a bulk export.
    """
    patients = patient_search(db, query=q, limit=limit)
    return PatientSearchResponse(
        patients=[PatientResponse.model_validate(patient) for patient in patients]
    )


@router.get(
    "/patients/{patient_id}/encounters",
    response_model=PatientHistoryResponse,
)
def get_patient_history(
    patient_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> PatientHistoryResponse:
    """One Patient's Encounters over time, oldest first.

    Every visit is rendered through the same helper the rest of the API uses. An
    unknown Patient is a 404, consistent with the encounter lookup.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    encounters = db.scalars(
        select(Encounter)
        .where(Encounter.patient_id == patient.id)
        .order_by(Encounter.arrived_at, Encounter.id)
    ).all()
    return PatientHistoryResponse(
        patient=PatientResponse.model_validate(patient),
        encounters=[_encounter_response(encounter) for encounter in encounters],
    )


@router.get("/encounters", response_model=EncounterListResponse)
def list_recent_encounters(
    db: DbSession,
    user: ClinicalUser,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> EncounterListResponse:
    """Encounters most recently opened first, for reviewing a saved intake."""
    encounters = db.scalars(
        select(Encounter)
        .order_by(Encounter.arrived_at.desc(), Encounter.id.desc())
        .limit(limit)
    ).all()
    return EncounterListResponse(
        encounters=[_encounter_response(encounter) for encounter in encounters]
    )


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
def get_encounter(
    encounter_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    return _encounter_response(_get_encounter(db, encounter_id))


@router.put("/encounters/{encounter_id}/intake", response_model=EncounterResponse)
def correct_visit_reason(
    encounter_id: int,
    payload: VisitReasonPayload,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """Replace the reason for the visit on an Encounter.

    The reason is not frozen by anything, so this route always succeeds for a
    known Encounter. Vitals in the body are refused (``422``), not dropped.
    """
    encounter = _get_encounter(db, encounter_id)
    apply_visit_reason(encounter, payload)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.correct_visit_reason,
        patient=encounter.patient,
        encounter=encounter,
    )
    db.commit()
    return _encounter_response(encounter)


@router.post("/encounters/{encounter_id}/end", response_model=EncounterResponse)
def end_visit(
    encounter_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """End a visit, recording the end instant now.

    Manual only: the instant is the server's clock at the moment of the request,
    never a value the caller supplies. A visit that has already ended is refused
    with ``409``; an unknown Encounter is a ``404``. The end and its single audit
    entry land in one transaction.
    """
    encounter = _get_encounter(db, encounter_id)
    end_encounter(db, encounter)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.end_encounter,
        patient=encounter.patient,
        encounter=encounter,
    )
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


def _encounter_response(encounter: Encounter) -> EncounterResponse:
    return EncounterResponse(
        id=encounter.id,
        arrived_at=encounter.arrived_at,
        ended_at=encounter.ended_at,
        status=encounter_status(encounter),
        patient=PatientResponse.model_validate(encounter.patient),
        reason_for_visit=encounter.reason_for_visit,
    )
