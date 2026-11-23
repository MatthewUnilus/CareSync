from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import reports
from app.audit import read_audit_log
from app.audit_actions import label_for
from app.deps import DbSession, require_role
from app.models import Role, User
from app.schemas import (
    ActorResponse,
    AuditEntryResponse,
    AuditLogResponse,
    DailyVisitsReportResponse,
    PerformanceEntryResponse,
    PerformanceReportResponse,
    WardCensusReportResponse,
    LengthOfStayReportResponse,
    LengthOfStayDistributionItem,
    MedicationTimelinessReportResponse,
    InvestigationReviewReportResponse,
    TaskCompletionReportResponse,
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
    admission_id: Annotated[
        int | None,
        Query(
            gt=0,
            description="Narrow the log to one Admission's history",
        ),
    ] = None,
) -> AuditLogResponse:
    """The append-only log of clinical mutations, oldest first.

    Read-only, like the Reports beside it: oversight stays separate from care,
    so this route offers no action and is refusable to a Clinical user. One
    Encounter or one Admission may be named, which reconstructs a single visit
    or a single stay; entries that touch neither are excluded by that filter.
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
                admission_id=entry.admission_id,
            )
            for entry in read_audit_log(
                db, encounter_id=encounter_id, admission_id=admission_id
            )
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
    ended on it, and awaiting is the day's arrivals without an end instant. The
    caller may name the day; otherwise it is the server's UTC day at the moment
    of the request.
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
    """Time waiting over ended Encounters, arrival to end."""
    report = reports.performance(db)
    return PerformanceReportResponse(
        completed=report.completed,
        average_waiting_seconds=report.average_waiting_seconds,
        entries=[
            PerformanceEntryResponse(
                encounter_id=entry.encounter_id,
                arrived_at=entry.arrived_at,
                ended_at=entry.ended_at,
                waiting_seconds=entry.waiting_seconds,
            )
            for entry in report.entries
        ],
    )


@router.get(
    "/reports/ward-census",
    response_model=WardCensusReportResponse,
)
def get_ward_census(
    db: DbSession,
    user: AdministratorUser,
) -> WardCensusReportResponse:
    """Current patients on the ward, grouped by location."""
    report = reports.ward_census(db)
    return WardCensusReportResponse(**report.__dict__)


@router.get(
    "/reports/length-of-stay",
    response_model=LengthOfStayReportResponse,
)
def get_length_of_stay(
    db: DbSession,
    user: AdministratorUser,
) -> LengthOfStayReportResponse:
    """Length of stay for current inpatients."""
    report = reports.length_of_stay(db)
    return LengthOfStayReportResponse(
        average_seconds=report.average_seconds,
        distribution=[LengthOfStayDistributionItem(**item) for item in report.distribution],
    )


@router.get(
    "/reports/medication-timeliness",
    response_model=MedicationTimelinessReportResponse,
)
def get_medication_timeliness(
    db: DbSession,
    user: AdministratorUser,
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Period in days to report on"),
    ] = 7,
) -> MedicationTimelinessReportResponse:
    """Doses recorded on time, late, and not given over a period."""
    report = reports.medication_timeliness(db, days)
    return MedicationTimelinessReportResponse(**report.__dict__)


@router.get(
    "/reports/investigation-review",
    response_model=InvestigationReviewReportResponse,
)
def get_investigation_review(
    db: DbSession,
    user: AdministratorUser,
) -> InvestigationReviewReportResponse:
    """Results awaiting review and how long the oldest has waited."""
    report = reports.investigation_review(db)
    return InvestigationReviewReportResponse(**report.__dict__)


@router.get(
    "/reports/task-completion",
    response_model=TaskCompletionReportResponse,
)
def get_task_completion(
    db: DbSession,
    user: AdministratorUser,
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Period in days to report on"),
    ] = 7,
) -> TaskCompletionReportResponse:
    """Tasks completed vs raised over a period."""
    report = reports.task_completion(db, days)
    return TaskCompletionReportResponse(**report.__dict__)