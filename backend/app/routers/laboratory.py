from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import CursorResult, Update, asc, desc, select, update

from app.audit import record_audit_entry
from app.audit_actions import AuditAction
from app.deps import DbSession, require_role
from app.investigations import investigation_actor
from app.models import Investigation, Role, User
from app.schemas import (
    InvestigationResultRequest,
    LaboratoryInvestigationResponse,
    LaboratoryPatientResponse,
    LaboratoryWorklistResponse,
)
from app.timeutils import utc_now

router = APIRouter(prefix="/api/laboratory", tags=["laboratory"])
LaboratoryUser = Annotated[User, Depends(require_role(Role.laboratory))]


def project(item: Investigation) -> LaboratoryInvestigationResponse:
    sender = investigation_actor(item.lab_sent_by)
    assert item.lab_sent_at and sender and item.sample_taken_at and item.lab_origin_ward
    patient = item.admission.patient
    return LaboratoryInvestigationResponse(
        id=item.id,
        admission_id=item.admission_id,
        patient=LaboratoryPatientResponse(
            full_name=patient.full_name, hospital_number=patient.hospital_number,
        ),
        ward=item.lab_origin_ward,
        test_name=item.test_name,
        sample_taken_at=item.sample_taken_at,
        lab_sent_at=item.lab_sent_at,
        lab_sent_by=sender,
        lab_received_at=item.lab_received_at,
        lab_received_by=investigation_actor(item.lab_received_by),
        result_available_at=item.result_available_at,
        result_published_by=investigation_actor(item.result_published_by),
        result_note=item.result_note,
    )


@router.get("/investigations", response_model=LaboratoryWorklistResponse)
def worklist(db: DbSession, user: LaboratoryUser) -> LaboratoryWorklistResponse:
    sent = select(Investigation).where(Investigation.lab_sent_at.is_not(None))
    # Group one read, so a concurrent publication cannot appear in two lists.
    rows = db.scalars(sent.order_by(
        desc(Investigation.result_available_at).nulls_last(),
        asc(Investigation.lab_received_at).nulls_last(),
        Investigation.lab_sent_at, Investigation.id,
    ))
    result = LaboratoryWorklistResponse(incoming=[], acknowledged=[], published=[])
    for item in rows:
        if item.result_available_at is not None:
            result.published.append(project(item))
        elif item.lab_received_at is not None:
            result.acknowledged.append(project(item))
        else:
            result.incoming.append(project(item))
    return result


def complete_action(
    db: DbSession, user: User, investigation_id: int, action: AuditAction, change: Update,
) -> LaboratoryInvestigationResponse:
    item = db.scalar(select(Investigation).where(
        Investigation.id == investigation_id, Investigation.lab_sent_at.is_not(None),
    ))
    if item is None:
        raise HTTPException(404, "Investigation not found")
    result = cast(CursorResult, db.execute(change.where(Investigation.id == item.id)))
    if result.rowcount != 1:
        raise HTTPException(409, "Request state changed. Refresh the laboratory worklist.")
    record_audit_entry(
        db, actor=user, action=action, patient=item.admission.patient,
        admission=item.admission, detail=f"investigation {item.id}",
    )
    db.commit()
    db.refresh(item)
    return project(item)


@router.post("/investigations/{id}/receive", response_model=LaboratoryInvestigationResponse)
def receive(id: int, db: DbSession, user: LaboratoryUser) -> LaboratoryInvestigationResponse:
    change = update(Investigation).where(Investigation.lab_received_at.is_(None)).values(
        lab_received_at=utc_now(), lab_received_by_user_id=user.id,
    )
    return complete_action(db, user, id, AuditAction.acknowledge_lab_investigation, change)


@router.post("/investigations/{id}/result", response_model=LaboratoryInvestigationResponse)
def publish(
    id: int, payload: InvestigationResultRequest, db: DbSession, user: LaboratoryUser,
) -> LaboratoryInvestigationResponse:
    change = update(Investigation).where(
        Investigation.lab_received_at.is_not(None),
        Investigation.result_available_at.is_(None),
    ).values(
        result_note=payload.result_note, result_available_at=utc_now(),
        result_published_by_user_id=user.id,
    )
    return complete_action(db, user, id, AuditAction.publish_lab_result, change)
