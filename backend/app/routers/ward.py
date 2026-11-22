"""The ward's HTTP surface: admission, location move, discharge and the board.

Admission is separate from Encounter (ADR 0008): a visit has a reason and an
end, a stay has a location and a discharge. Every mutation here is a Clinical
action that writes exactly one audit entry in the same transaction as the change
(ADR 0007). The board is a read: it recalculates from the record on every
request and writes nothing.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ward
from app.admissions import (
    admission_status,
    admit,
    discharge,
    move,
)
from app.audit import record_audit_entry
from app.audit_actions import AuditAction
from app.deps import DbSession, require_role
from app.models import Admission, Encounter, Patient, Role, User
from app.observations import observation_response
from app.schemas import (
    AdmissionCreateRequest,
    AdmissionListResponse,
    AdmissionMoveRequest,
    AdmissionResponse,
    PatientResponse,
    WardBoardEntryResponse,
    WardBoardResponse,
)

router = APIRouter(prefix="/api/ward", tags=["ward"])

ClinicalUser = Annotated[User, Depends(require_role(Role.clinical))]

PATIENT_NOT_FOUND_DETAIL = "Patient not found"
ENCOUNTER_NOT_FOUND_DETAIL = "Encounter not found"
ENCOUNTER_OWNER_MISMATCH_DETAIL = "Encounter belongs to another patient"
ADMISSION_NOT_FOUND_DETAIL = "Admission not found"


@router.post(
    "/admissions",
    response_model=AdmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def admit_patient(
    payload: AdmissionCreateRequest,
    db: DbSession,
    user: ClinicalUser,
) -> AdmissionResponse:
    """Admit a Patient to a ward and bed, optionally linking the visit they came in on.

    A direct admission works with no prior visit. When an ``encounter_id`` is
    supplied it must name the same Patient's Encounter, so the visit and the
    stay read as one history and one Patient's stay can never be pinned to
    another Patient's visit. The Admission and its single audit entry commit
    together.
    """
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PATIENT_NOT_FOUND_DETAIL,
        )

    encounter = None
    if payload.encounter_id is not None:
        encounter = db.get(Encounter, payload.encounter_id)
        if encounter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ENCOUNTER_NOT_FOUND_DETAIL,
            )
        if encounter.patient_id != patient.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ENCOUNTER_OWNER_MISMATCH_DETAIL,
            )

    admission = admit(
        db,
        patient=patient,
        ward=payload.ward,
        bed=payload.bed,
        encounter=encounter,
    )
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.admit_patient,
        patient=patient,
        encounter=encounter,
        admission=admission,
    )
    db.commit()
    return AdmissionResponse(**_admission_fields(admission))


@router.post(
    "/admissions/{admission_id}/move",
    response_model=AdmissionResponse,
)
def move_admission(
    admission_id: int,
    payload: AdmissionMoveRequest,
    db: DbSession,
    user: ClinicalUser,
) -> AdmissionResponse:
    """Move an open stay to another ward and bed.

    The move is recorded on the Admission and in its audit entry, so the board
    always says where a Patient is. A discharged stay cannot be moved (``409``);
    an unknown Admission is a ``404``. The move and its audit entry commit
    together.
    """
    admission = _get_admission(db, admission_id)
    from_location = f"{admission.ward} / {admission.bed}"
    move(db, admission, ward=payload.ward, bed=payload.bed)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.move_admission,
        patient=admission.patient,
        encounter=admission.encounter,
        admission=admission,
        detail=f"{from_location} -> {payload.ward} / {payload.bed}",
    )
    db.commit()
    return AdmissionResponse(**_admission_fields(admission))


@router.post(
    "/admissions/{admission_id}/discharge",
    response_model=AdmissionResponse,
)
def discharge_admission(
    admission_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> AdmissionResponse:
    """Discharge a Patient, recording the instant now.

    Manual only: the instant is the server's clock at the moment of the request,
    never a value the caller supplies. A stay that has already been discharged is
    refused with ``409``; an unknown Admission is a ``404``. The discharge and
    its single audit entry land in one transaction, and the stay leaves the board
    while keeping its full history.
    """
    admission = _get_admission(db, admission_id)
    discharge(db, admission)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.discharge_patient,
        patient=admission.patient,
        encounter=admission.encounter,
        admission=admission,
    )
    db.commit()
    return AdmissionResponse(**_admission_fields(admission))


@router.get("/board", response_model=WardBoardResponse)
def get_board(db: DbSession, user: ClinicalUser) -> WardBoardResponse:
    """The ward's open admissions, ordered by outstanding work.

    Recalculated on every read and storing nothing: each entry carries the
    Patient's latest Observation and the counts of what the record shows is
    outstanding, ordered overdue medication, then due medication, then results
    awaiting review, then open Tasks, with bed order breaking ties.
    """
    return WardBoardResponse(
        admissions=[
            _board_entry_response(db, entry) for entry in ward.board(db)
        ]
    )


@router.get("/admissions", response_model=AdmissionListResponse)
def list_admissions(
    db: DbSession,
    user: ClinicalUser,
    patient_id: Annotated[
        int,
        Query(gt=0, description="The Patient whose admissions to read"),
    ],
) -> AdmissionListResponse:
    """One Patient's Admissions over time, oldest first, including discharged ones.

    A discharged stay is closed, not deleted (ADR 0008), so this history keeps
    it while the board drops it. An unknown Patient is a ``404``.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=PATIENT_NOT_FOUND_DETAIL,
        )

    admissions = db.scalars(
        select(Admission)
        .where(Admission.patient_id == patient.id)
        .order_by(Admission.admitted_at, Admission.id)
    ).all()
    return AdmissionListResponse(
        admissions=[
            AdmissionResponse(**_admission_fields(admission))
            for admission in admissions
        ]
    )


def _get_admission(db: Session, admission_id: int) -> Admission:
    admission = db.get(Admission, admission_id)
    if admission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ADMISSION_NOT_FOUND_DETAIL,
        )
    return admission


def _admission_fields(admission: Admission) -> dict:
    """The Admission fields shared by ``AdmissionResponse`` and a board row."""
    return {
        "id": admission.id,
        "patient": PatientResponse.model_validate(admission.patient),
        "ward": admission.ward,
        "bed": admission.bed,
        "admitted_at": admission.admitted_at,
        "discharged_at": admission.discharged_at,
        "encounter_id": admission.encounter_id,
        "status": admission_status(admission),
    }


def _board_entry_response(
    db: Session, entry: ward.WardBoardEntry
) -> WardBoardEntryResponse:
    return WardBoardEntryResponse(
        **_admission_fields(entry.admission),
        latest_observation=(
            None
            if entry.latest_observation is None
            else observation_response(db, entry.latest_observation)
        ),
        outstanding_medication_count=entry.outstanding_medication_count,
        overdue_medication_count=entry.overdue_medication_count,
        due_medication_count=entry.due_medication_count,
        open_task_count=entry.open_task_count,
        unreviewed_result_count=entry.unreviewed_result_count,
    )
