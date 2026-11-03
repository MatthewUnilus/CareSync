from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app import accuracy, reports
from app.deps import DbSession, require_role
from app.models import Role, User
from app.queue import administrator_queue
from app.schemas import (
    AccuracyConfusionCellResponse,
    AccuracyEvaluationReportResponse,
    AccuracyFallbackCoverageResponse,
    AccuracyGroundTruthSourceResponse,
    AccuracyLevelMetricsResponse,
    AccuracyOverrideMetricsResponse,
    AccuracyOverrideReasonCountResponse,
    AccuracyPriorityErrorRateResponse,
    AccuracyRunResponse,
    AccuracyRunSampleResponse,
    AdministratorQueueEntryResponse,
    AdministratorQueueResponse,
    DailyQueueReportResponse,
    PerformanceEntryResponse,
    PerformanceReportResponse,
    PriorityDistributionReportResponse,
    PriorityLevelCountResponse,
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
    "/reports/daily-queue",
    response_model=DailyQueueReportResponse,
)
def get_daily_queue_report(
    db: DbSession,
    user: AdministratorUser,
    day: Annotated[
        date | None,
        Query(description="UTC day to report on; defaults to the server's day"),
    ] = None,
) -> DailyQueueReportResponse:
    """The day's volume and throughput, derived on demand.

    Volume is Encounters that arrived on the day, throughput is Encounters that
    departed on it, and awaiting is the day's arrivals without a departure
    instant. The caller may name the day; otherwise it is the server's UTC day
    at the moment of the request.
    """
    report = reports.daily_queue(db, day or utc_now().date())
    return DailyQueueReportResponse(
        day=report.day,
        starts_at=report.starts_at,
        ends_at=report.ends_at,
        volume=report.volume,
        throughput=report.throughput,
        awaiting=report.awaiting,
    )


@router.get(
    "/reports/priority-distribution",
    response_model=PriorityDistributionReportResponse,
)
def get_priority_distribution_report(
    db: DbSession,
    user: AdministratorUser,
) -> PriorityDistributionReportResponse:
    """One count per Encounter at its governing Assessment's Final Decision."""
    report = reports.priority_distribution(db)
    return PriorityDistributionReportResponse(
        total=report.total,
        levels=[
            PriorityLevelCountResponse(
                urgency_level=level.urgency_level,
                encounters=level.encounters,
            )
            for level in report.levels
        ],
    )


@router.get(
    "/reports/performance",
    response_model=PerformanceReportResponse,
)
def get_performance_report(
    db: DbSession,
    user: AdministratorUser,
) -> PerformanceReportResponse:
    """Time waiting and processing time over departed Encounters."""
    report = reports.performance(db)
    return PerformanceReportResponse(
        completed=report.completed,
        average_waiting_seconds=report.average_waiting_seconds,
        average_processing_seconds=report.average_processing_seconds,
        entries=[
            PerformanceEntryResponse(
                encounter_id=entry.encounter_id,
                arrived_at=entry.arrived_at,
                assessed_at=entry.assessed_at,
                departed_at=entry.departed_at,
                waiting_seconds=entry.waiting_seconds,
                processing_seconds=entry.processing_seconds,
            )
            for entry in report.entries
        ],
    )


@router.get(
    "/reports/accuracy-evaluation",
    response_model=AccuracyEvaluationReportResponse,
)
def get_accuracy_evaluation_report(
    db: DbSession,
    user: AdministratorUser,
    request: Request,
) -> AccuracyEvaluationReportResponse:
    """Machine Recommendations against independent ground-truth labels.

    The labelled run is read from the offline harness's manifest, whose path is
    configuration. The Machine Recommendation itself always comes from the
    stored Triage Assessment row, so an Override can never move a matrix cell.
    No run, or no stored Assessment behind its cases, is an explicit empty
    state rather than a zero score.
    """
    bundle = accuracy.load_run_bundle(
        Path(request.app.state.settings.accuracy_run_path)
    )
    report = accuracy.build_report(db, bundle)
    return _accuracy_report_response(report)


def _accuracy_report_response(
    report: accuracy.AccuracyEvaluationReport,
) -> AccuracyEvaluationReportResponse:
    return AccuracyEvaluationReportResponse(
        available=report.available,
        empty_reason=report.empty_reason,
        runs=[
            AccuracyRunResponse(
                run_id=run.run_id,
                mode=run.mode,
                dataset=run.dataset,
                engine_artefact=run.engine_artefact,
                ground_truth=AccuracyGroundTruthSourceResponse(
                    name=run.ground_truth.name,
                    version=run.ground_truth.version,
                    citation=run.ground_truth.citation,
                    document=run.ground_truth.document,
                ),
                sample=AccuracyRunSampleResponse(
                    labelled_cases=run.sample.labelled_cases,
                    resolved_assessments=run.sample.resolved_assessments,
                    missing_assessments=list(run.sample.missing_assessments),
                    inconsistent_recommendations=list(
                        run.sample.inconsistent_recommendations
                    ),
                ),
                confusion_matrix=[
                    AccuracyConfusionCellResponse(
                        machine_recommendation=cell.machine_recommendation,
                        ground_truth=cell.ground_truth,
                        assessments=cell.assessments,
                    )
                    for cell in run.confusion_matrix
                ],
                levels=[
                    AccuracyLevelMetricsResponse(
                        urgency_level=level.urgency_level,
                        ground_truth_count=level.ground_truth_count,
                        predicted_count=level.predicted_count,
                        correct=level.correct,
                        precision=level.precision,
                        recall=level.recall,
                    )
                    for level in run.levels
                ],
                total=run.total,
                correct=run.correct,
                accuracy=run.accuracy,
                false_high_priority=AccuracyPriorityErrorRateResponse(
                    count=run.false_high_priority.count,
                    denominator=run.false_high_priority.denominator,
                    rate=run.false_high_priority.rate,
                ),
                false_low_priority=AccuracyPriorityErrorRateResponse(
                    count=run.false_low_priority.count,
                    denominator=run.false_low_priority.denominator,
                    rate=run.false_low_priority.rate,
                ),
                fallback=AccuracyFallbackCoverageResponse(
                    enabled=run.fallback.enabled,
                    fallback_used=run.fallback.fallback_used,
                    unclassified=run.fallback.unclassified,
                    coverage=run.fallback.coverage,
                    unclassified_rate=run.fallback.unclassified_rate,
                ),
            )
            for run in report.runs
        ],
        overrides=AccuracyOverrideMetricsResponse(
            assessments=report.overrides.assessments,
            overridden_assessments=report.overrides.overridden_assessments,
            overrides=report.overrides.overrides,
            rate=report.overrides.rate,
            reasons=[
                AccuracyOverrideReasonCountResponse(
                    reason=item.reason,
                    overrides=item.overrides,
                    share=item.share,
                )
                for item in report.overrides.reasons
            ],
        ),
    )
