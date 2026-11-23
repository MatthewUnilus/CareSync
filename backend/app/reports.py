"""Reports: read-only views derived on demand from stored records.

A Report is never a stored snapshot and never a projection of the live record.
It is recomputed from the rows that record what happened, on every read, so a
change to a record shows in the very next request and reverting the record
reverts the figure. Nothing is cached.

A "day" is one UTC calendar day, half-open: ``[00:00, next 00:00)``.

Definitions, in the terms of ``CONTEXT.md``:

* **Volume** — Encounters that arrived on the day.
* **Throughput** — Encounters that ended on the day. An Encounter can
  contribute to one day's volume and another day's throughput.
* **Awaiting** — Encounters that arrived on the day and have no end instant
  yet.
* **Waiting time** — arrival to end, the whole Encounter.

Waiting time is computed only for ended Encounters, because only they have an
end instant.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter
from app.timeutils import as_utc


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """The half-open UTC window a Report's day covers."""
    starts_at = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return starts_at, starts_at + timedelta(days=1)


@dataclass(frozen=True)
class DailyVisitsReport:
    day: date
    starts_at: datetime
    ends_at: datetime
    volume: int
    throughput: int
    awaiting: int


def daily_visits(session: Session, day: date) -> DailyVisitsReport:
    """The day's arrival volume, end throughput, and backlog."""
    starts_at, ends_at = utc_day_bounds(day)
    volume = 0
    throughput = 0
    awaiting = 0
    for encounter in session.scalars(select(Encounter)).all():
        if starts_at <= as_utc(encounter.arrived_at) < ends_at:
            volume += 1
            if encounter.ended_at is None:
                awaiting += 1
        if encounter.ended_at is not None:
            if starts_at <= as_utc(encounter.ended_at) < ends_at:
                throughput += 1
    return DailyVisitsReport(
        day=day,
        starts_at=starts_at,
        ends_at=ends_at,
        volume=volume,
        throughput=throughput,
        awaiting=awaiting,
    )


@dataclass(frozen=True)
class PerformanceEntry:
    encounter_id: int
    arrived_at: datetime
    ended_at: datetime
    waiting_seconds: int


@dataclass(frozen=True)
class PerformanceReport:
    completed: int
    average_waiting_seconds: float
    entries: list[PerformanceEntry]


def performance(session: Session) -> PerformanceReport:
    """Time waiting over ended Encounters, arrival to end."""
    entries: list[PerformanceEntry] = []
    for encounter in session.scalars(select(Encounter)).all():
        if encounter.ended_at is None:
            continue
        arrived_at = as_utc(encounter.arrived_at)
        ended_at = as_utc(encounter.ended_at)
        entries.append(
            PerformanceEntry(
                encounter_id=encounter.id,
                arrived_at=arrived_at,
                ended_at=ended_at,
                waiting_seconds=_seconds_between(arrived_at, ended_at),
            )
        )

    entries.sort(key=lambda entry: (entry.ended_at, entry.encounter_id))
    completed = len(entries)
    if completed == 0:
        return PerformanceReport(0, 0.0, [])
    return PerformanceReport(
        completed=completed,
        average_waiting_seconds=round(
            sum(entry.waiting_seconds for entry in entries) / completed, 1
        ),
        entries=entries,
    )


def _seconds_between(start: datetime, end: datetime) -> int:
    """Whole seconds, never negative even if a stored pair is out of order."""
    return max(0, int((end - start).total_seconds()))


# ============================================================================
# Ward Operations Dashboard Reports
# ============================================================================


@dataclass(frozen=True)
class WardCensusReport:
    """Current ward census by location."""
    total_patients: int
    by_ward: dict[str, int]
    by_bed: dict[str, int]


def ward_census(session: Session) -> WardCensusReport:
    """Current patients on the ward, grouped by location."""
    from app.models import Admission

    total = 0
    by_ward: dict[str, int] = {}
    by_bed: dict[str, int] = {}
    for admission in session.scalars(select(Admission).where(Admission.discharged_at.is_(None))).all():
        total += 1
        by_ward[admission.ward] = by_ward.get(admission.ward, 0) + 1
        by_bed[f"{admission.ward} · {admission.bed}"] = by_bed.get(f"{admission.ward} · {admission.bed}", 0) + 1
    return WardCensusReport(
        total_patients=total,
        by_ward=by_ward,
        by_bed=by_bed,
    )


@dataclass(frozen=True)
class LengthOfStayReport:
    """Length of stay for current inpatients."""
    average_seconds: float
    distribution: list[dict]


def length_of_stay(session: Session) -> LengthOfStayReport:
    """Length of stay for current inpatients."""
    from app.models import Admission
    from app.timeutils import utc_now

    now = utc_now()
    stays: list[dict] = []
    total_seconds = 0.0
    count = 0
    for admission in session.scalars(select(Admission).where(Admission.discharged_at.is_(None))).all():
        admitted_at = as_utc(admission.admitted_at)
        seconds = max(0, (now - admitted_at).total_seconds())
        total_seconds += seconds
        count += 1
        stays.append({
            "admission_id": admission.id,
            "patient": admission.patient.full_name,
            "ward": admission.ward,
            "bed": admission.bed,
            "seconds": seconds,
            "days": round(seconds / 86400, 1),
        })
    stays.sort(key=lambda s: s["seconds"], reverse=True)
    return LengthOfStayReport(
        average_seconds=round(total_seconds / count, 1) if count > 0 else 0.0,
        distribution=stays,
    )


@dataclass(frozen=True)
class MedicationTimelinessReport:
    """Doses recorded on time, late, and not given."""
    on_time: int
    late: int
    not_given: int
    total: int
    on_time_pct: float


def medication_timeliness(session: Session, days: int = 7) -> MedicationTimelinessReport:
    """Doses recorded on time vs late vs not given over a period."""
    from app.models import MedicationAdministration
    from app.timeutils import utc_now

    now = utc_now()
    cutoff = now - timedelta(days=days)

    # Get all administrations in the window
    admins = session.scalars(
        select(MedicationAdministration)
        .where(MedicationAdministration.recorded_at >= cutoff)
    ).all()

    on_time = 0
    late = 0
    not_given = 0

    for admin in admins:
        if admin.outcome == "given":
            due_at = as_utc(admin.due_at)
            recorded_at = as_utc(admin.recorded_at)
            if recorded_at <= due_at:
                on_time += 1
            else:
                late += 1
        else:
            not_given += 1

    total = on_time + late + not_given
    return MedicationTimelinessReport(
        on_time=on_time,
        late=late,
        not_given=not_given,
        total=total,
        on_time_pct=round((on_time / total * 100), 1) if total > 0 else 0.0,
    )


@dataclass(frozen=True)
class InvestigationReviewReport:
    """Results awaiting review and oldest wait."""
    awaiting_review_count: int
    oldest_wait_seconds: int | None


def investigation_review(session: Session) -> InvestigationReviewReport:
    """Results awaiting review and how long the oldest has waited."""
    from app.models import Investigation
    from app.timeutils import utc_now

    now = utc_now()
    awaiting = session.scalars(
        select(Investigation).where(Investigation.result_available_at.is_not(None))
        .where(Investigation.reviewed_at.is_(None))
    ).all()

    count = len(awaiting)
    oldest_wait = None
    for inv in awaiting:
        available_at = as_utc(inv.result_available_at)
        wait = int((now - available_at).total_seconds())
        if oldest_wait is None or wait > oldest_wait:
            oldest_wait = wait

    return InvestigationReviewReport(
        awaiting_review_count=count,
        oldest_wait_seconds=oldest_wait,
    )


@dataclass(frozen=True)
class TaskCompletionReport:
    """Tasks completed vs raised over a period."""
    raised: int
    completed: int
    completion_pct: float


def task_completion(session: Session, days: int = 7) -> TaskCompletionReport:
    """Tasks completed vs raised over a period."""
    from app.models import Task
    from app.timeutils import utc_now

    now = utc_now()
    cutoff = now - timedelta(days=days)

    tasks = session.scalars(
        select(Task).where(Task.raised_at >= cutoff)
    ).all()

    raised = len(tasks)
    completed = sum(1 for t in tasks if t.completed_at is not None)

    return TaskCompletionReport(
        raised=raised,
        completed=completed,
        completion_pct=round((completed / raised * 100), 1) if raised > 0 else 0.0,
    )
