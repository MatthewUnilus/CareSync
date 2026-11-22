from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import reports
from app.audit import read_audit_log
from app.audit_actions import label_for
from app.deps import DbSession, require_role
from app.models import Role, User
from app.queue import administrator_queue
from app.schemas import (
    AdministratorQueueEntryResponse,
    AdministratorQueueResponse,
    AuditEntryResponse,
    AuditLogResponse,
    DailyVisitsReportResponse,
    ActorResponse,
    PerformanceEntryResponse,
    PerformanceReportResponse,
)
from app.timeutils import utc_now

router = APIRouter(prefix="/api/administrator", tags=["administrator"])

AdministratorUser = Annotated[User, Depends(require_role(Role.administrator))]


@router.get("/access")
def administrator_access(user: AdministratorUser) -> dict[str, str]:
    return {
        "role": Role.administrator.value,
        "message": "Administrator access granted",
    }


@router.get("/queue", response_model=AdministratorQueueResponse)
def get_administrator_queue(
    db: DbSession,
    user: AdministratorUser,
) -> AdministratorQueueResponse:
    """The awaiting Queue as a dense, read-only table.

    Neither this route nor the Reports below offers any clinical action.
    """
    now = utc_now()
    return AdministratorQueueResponse(
        as_of=now,
        entries=[
            AdministratorQueueEntryResponse(
                encounter_id=row.encounter_id,
                arrived_at=row.arrived_at,
                waiting_seconds=row.waiting_seconds,
                urgency_level=row.urgency_level,
                patient_name=row.patient_name,
                presenting_complaint=row.presenting_complaint,
                machine_recommendation=row.machine_recommendation,
                final_decision=row.final_decision,
                final_decision_differs=row.final_decision_differs,
            )
            for row in administrator_queue(db, now)
        ],
    )


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
)
def get_audit_log(
    db: DbSession,
    user: AdministratorUser,
    encounter_id: Annotated[
        int | None,
        Query(
            gt=0,
            description="Narrow the log to one Encounter's history",
        ),
    ] = None,
) -> AuditLogResponse:
    """The append-only log of clinical mutations, oldest first.

    Read-only, like the Reports beside it: oversight stays separate from care,
    so this route offers no action and is refusable to a Clinical user. One
    Encounter may be named, which reconstructs a single visit; entries that
    touch no Encounter (registration) are excluded by that filter.
    """
    return AuditLogResponse(
        entries=[
            AuditEntryResponse(
                id=entry.id,
                action=entry.action,
                action_label=label_for(entry.action),
                detail=entry.detail,
                recorded_at=entry.recorded_at,
                actor=ActorResponse(
                    id=entry.actor.id,
                    display_name=entry.actor.display_name,
                ),
                patient_id=entry.patient_id,
                encounter_id=entry.encounter_id,
                assessment_id=entry.assessment_id,
            )
            for entry in read_audit_log(db, encounter_id=encounter_id)
        ]
    )


@router.get(
    "/reports/daily-visits",
    response_model=DailyVisitsReportResponse,
)
def get_daily_visits_report(
    db: DbSession,
    user: AdministratorUser,
    day: Annotated[
        date | None,
        Query(description="UTC day to report on; defaults to the server's day"),
    ] = None,
) -> DailyVisitsReportResponse:
    """The day's visits, derived on demand.

    Volume is Encounters that arrived on the day, throughput is Encounters that
    departed on it, and awaiting is the day's arrivals without a departure
    instant. The caller may name the day; otherwise it is the server's UTC day
    at the moment of the request.
    """
    report = reports.daily_visits(db, day or utc_now().date())
    return DailyVisitsReportResponse(
        day=report.day,
        starts_at=report.starts_at,
        ends_at=report.ends_at,
        volume=report.volume,
        throughput=report.throughput,
        awaiting=report.awaiting,
    )


@router.get(
    "/reports/performance",
    response_model=PerformanceReportResponse,
)
def get_performance_report(
    db: DbSession,
    user: AdministratorUser,
) -> PerformanceReportResponse:
    """Time waiting over departed Encounters, arrival to departure."""
    report = reports.performance(db)
    return PerformanceReportResponse(
        completed=report.completed,
        average_waiting_seconds=report.average_waiting_seconds,
        entries=[
            PerformanceEntryResponse(
                encounter_id=entry.encounter_id,
                arrived_at=entry.arrived_at,
                departed_at=entry.departed_at,
                waiting_seconds=entry.waiting_seconds,
            )
            for entry in report.entries
        ],
    )
