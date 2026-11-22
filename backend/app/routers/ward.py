"""The ward's HTTP surface: admission, move, discharge, the board and notes.

Admission is separate from Encounter (ADR 0008): a visit has a reason and an
end, a stay has a location and a discharge. Every mutation here is a Clinical
action that writes exactly one audit entry in the same transaction as the change
(ADR 0007). The board is a read: it recalculates from the record on every
request and writes nothing. Nursing Notes and the Note Template vocabulary live
here too (ticket 32): the templates are a fixed code vocabulary (ADR 0013) and a
note is written from one, its fields one row each, prefilled from the patient's
latest Observation.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notes, ward
from app.admissions import (
    admission_status,
    admit,
    discharge,
    move,
)
from app.audit import record_audit_entry
from app.audit_actions import AuditAction
from app.deps import DbSession, require_role
from app.models import Admission, Encounter, NursingNote, Patient, Role, User
from app.observations import observation_response
from app.schemas import (
    ActorResponse,
    AdmissionCreateRequest,
    AdmissionListResponse,
    AdmissionMoveRequest,
    AdmissionResponse,
    NotePrefillResponse,
    NotePrefillSourceResponse,
    NoteTemplatesResponse,
    NursingNoteCreateRequest,
    NursingNoteListResponse,
    NursingNoteResponse,
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
DISCHARGED_STAY_NOTE_DETAIL = (
    "A discharged Admission cannot take new Notes, except a Discharge Summary"
)


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


@router.get("/note-templates", response_model=NoteTemplatesResponse)
def get_note_templates(user: ClinicalUser) -> NoteTemplatesResponse:
    """The fixed Note Template vocabulary, so a note starts from a shape.

    The definitions live in code (``app.notes``); this is a plain read of them.
    Adding a field to a template is a code change with no schema change and no
    client change, because the client reads the fields from here (ADR 0013).
    """
    return NoteTemplatesResponse(templates=notes.template_responses())


@router.get(
    "/admissions/{admission_id}/note-prefill",
    response_model=NotePrefillResponse,
)
def get_note_prefill(
    admission_id: int,
    db: DbSession,
    user: ClinicalUser,
    template_key: Annotated[
        str,
        Query(
            min_length=1,
            max_length=64,
            description="The template the note will be written from",
        ),
    ],
) -> NotePrefillResponse:
    """The values to start a note with, drawn from the patient's latest vitals.

    The prefill is visible, not silent: the ``vital_signs`` free text names where
    each number came from, and ``source_observation`` names the Observation it was
    read from, so a nurse who sees the source amends rather than retypes. An
    unknown Admission is a 404; an unknown template is a 422.
    """
    admission = _get_admission(db, admission_id)
    template = notes.resolve_template(template_key)
    values, source = notes.prefill(db, admission, template)
    return NotePrefillResponse(
        fields=values,
        source_observation=(
            None
            if source is None
            else NotePrefillSourceResponse(
                taken_at=source.taken_at,
                actor=ActorResponse(
                    id=source.actor.id,
                    display_name=source.actor.display_name,
                ),
            )
        ),
    )


@router.get(
    "/admissions/{admission_id}/notes",
    response_model=NursingNoteListResponse,
)
def list_nursing_notes(
    admission_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> NursingNoteListResponse:
    """One Admission's notes in time order, oldest first.

    A discharged stay is closed, not deleted, so its notes are still returned in
    full. An unknown Admission is a 404.
    """
    admission = _get_admission(db, admission_id)
    return NursingNoteListResponse(notes=notes.notes_response(db, admission))


@router.post(
    "/admissions/{admission_id}/notes",
    response_model=NursingNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_nursing_note(
    admission_id: int,
    payload: NursingNoteCreateRequest,
    db: DbSession,
    user: ClinicalUser,
) -> NursingNoteResponse:
    """Write a Nursing Note from a template, or append a correction to one.

    The note and its single audit entry commit together, with the Admission as
    the entry's subject (ADR 0007). A correction names the note it corrects, which
    must be on the same Admission and use the same template; the corrected note is
    never edited and still reads back, showing the note that corrects it. An
    unknown Admission or correction note is a 404; an unknown template, an
    incomplete field set or an unknown field key is a 422.

    A stay that has already been discharged takes no new note, because it is no
    longer on the ward, except a Discharge Summary: that records the stay and the
    state at leaving, so it follows the discharge rather than being refused by it.
    """
    admission = _get_admission(db, admission_id)
    template = notes.resolve_template(payload.template_key)
    if (
        admission.discharged_at is not None
        and template.key != notes.DISCHARGE_SUMMARY_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DISCHARGED_STAY_NOTE_DETAIL,
        )
    notes.validate_fields(template, payload.fields)

    corrects: NursingNote | None = None
    if payload.corrects_note_id is not None:
        corrects = db.get(NursingNote, payload.corrects_note_id)
        if corrects is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=notes.NOTE_NOT_FOUND_DETAIL,
            )
        if corrects.admission_id != admission.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=notes.CORRECTION_OTHER_ADMISSION_DETAIL,
            )
        if corrects.template_key != template.key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=notes.CORRECTION_TEMPLATE_MISMATCH_DETAIL,
            )
        if notes.corrected_by(db, corrects) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=notes.ALREADY_CORRECTED_DETAIL,
            )

    note = notes.stage_note(
        db,
        admission=admission,
        actor=user,
        template=template,
        fields=payload.fields,
        corrects=corrects,
    )
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=(
            AuditAction.correct_nursing_note
            if corrects is not None
            else AuditAction.write_nursing_note
        ),
        patient=admission.patient,
        admission=admission,
        detail=(
            f"template {template.key}"
            if corrects is None
            else f"template {template.key} corrects note {corrects.id}"
        ),
    )
    db.commit()
    return notes.note_response(db, note)


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
