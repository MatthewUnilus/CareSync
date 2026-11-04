"""Reports: read-only views derived on demand from stored records.

A Report is never a stored snapshot and never a projection of the live Queue. It
is recomputed from the rows that record what happened: an Encounter's arrival
and departure instants, and its Triage Assessment rows. Nothing is cached, so a
change to a record shows in the very next request, and reverting the record
reverts the figure.

Each Encounter's **governing Assessment** is its highest-id one, matching the
Queue: a Re-assessment appends a row and its Final Decision wins. The Priority
Distribution and Performance Reports share the ``governing_assessments`` read
model. Ticket 14's Accuracy Evaluation is measured per Assessment rather than
per Encounter, so it reads Triage Assessment rows (and Overrides) directly.

A "day" is one UTC calendar day, half-open: ``[00:00, next 00:00)``.

Definitions, in the terms of ``CONTEXT.md``:

* **Volume** — Encounters that arrived on the day.
* **Throughput** — Encounters that departed on the day. An Encounter can
  contribute to one day's volume and another day's throughput.
* **Awaiting** — Encounters that arrived on the day and have no departure
  instant yet.
* **Priority Distribution** — one count per Encounter, at the Urgency Level of
  its governing Assessment's Final Decision.
* **Waiting time** — arrival to departure, the whole Encounter. The departure
  instant is what makes this figure complete, exactly as the Queue's
  ``waiting_seconds`` is arrival to now while the Encounter awaits.
* **Processing time** — the governing Assessment to departure: the part of the
  stay after the urgency decision existed.

Waiting and processing time are computed only for departed Encounters, because
only they have a departure instant.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Encounter, TriageAssessment
from app.prioritisation import URGENCY_RANK, UrgencyLevel
from app.timeutils import as_utc


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """The half-open UTC window a Report's day covers."""
    starts_at = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return starts_at, starts_at + timedelta(days=1)


@dataclass(frozen=True)
class AssessedEncounter:
    """An Encounter paired with the Assessment that governs it."""

    encounter: Encounter
    assessment: TriageAssessment

    @property
    def urgency_level(self) -> UrgencyLevel:
        return UrgencyLevel(self.assessment.final_decision)


def governing_assessments(session: Session) -> list[AssessedEncounter]:
    """Every assessed Encounter, with its highest-id Assessment.

    Shared read model for the Reports: the Priority Distribution and the
    Performance Report both need "one Urgency Level per Encounter". An
    Encounter without an Assessment has no Urgency Level and is not a row.
    """
    encounters = session.scalars(
        select(Encounter)
        # Evaluation-run rows are excluded: the activity and performance
        # Reports describe what happened in this facility, not the labelled
        # corpus that evidences the engine.
        .where(Encounter.evaluation_run_id.is_(None))
        .options(selectinload(Encounter.assessments))
        .order_by(Encounter.id)
    ).all()
    return [
        AssessedEncounter(encounter, encounter.assessments[-1])
        for encounter in encounters
        if encounter.assessments
    ]


@dataclass(frozen=True)
class DailyQueueReport:
    day: date
    starts_at: datetime
    ends_at: datetime
    volume: int
    throughput: int
    awaiting: int


def daily_queue(session: Session, day: date) -> DailyQueueReport:
    """The day's arrival volume, departure throughput, and backlog."""
    starts_at, ends_at = utc_day_bounds(day)
    volume = 0
    throughput = 0
    awaiting = 0
    for encounter in session.scalars(
        select(Encounter).where(Encounter.evaluation_run_id.is_(None))
    ).all():
        if starts_at <= as_utc(encounter.arrived_at) < ends_at:
            volume += 1
            if encounter.departed_at is None:
                awaiting += 1
        if encounter.departed_at is not None:
            if starts_at <= as_utc(encounter.departed_at) < ends_at:
                throughput += 1
    return DailyQueueReport(
        day=day,
        starts_at=starts_at,
        ends_at=ends_at,
        volume=volume,
        throughput=throughput,
        awaiting=awaiting,
    )


@dataclass(frozen=True)
class UrgencyLevelCount:
    urgency_level: UrgencyLevel
    encounters: int


@dataclass(frozen=True)
class UrgencyDistributionReport:
    total: int
    levels: list[UrgencyLevelCount]


def priority_distribution(session: Session) -> UrgencyDistributionReport:
    """How many Encounters sit at each Urgency Level, one per Encounter."""
    counts = {level: 0 for level in UrgencyLevel}
    for row in governing_assessments(session):
        counts[row.urgency_level] += 1
    ordered = sorted(UrgencyLevel, key=lambda level: URGENCY_RANK[level])
    return UrgencyDistributionReport(
        total=sum(counts.values()),
        levels=[
            UrgencyLevelCount(level, counts[level]) for level in ordered
        ],
    )


@dataclass(frozen=True)
class PerformanceEntry:
    encounter_id: int
    arrived_at: datetime
    assessed_at: datetime
    departed_at: datetime
    waiting_seconds: int
    processing_seconds: int


@dataclass(frozen=True)
class PerformanceReport:
    completed: int
    average_waiting_seconds: float
    average_processing_seconds: float
    entries: list[PerformanceEntry]


def performance(session: Session) -> PerformanceReport:
    """Time waiting and processing time over departed Encounters."""
    entries: list[PerformanceEntry] = []
    for row in governing_assessments(session):
        encounter = row.encounter
        if encounter.departed_at is None:
            continue
        arrived_at = as_utc(encounter.arrived_at)
        assessed_at = as_utc(row.assessment.assessed_at)
        departed_at = as_utc(encounter.departed_at)
        entries.append(
            PerformanceEntry(
                encounter_id=encounter.id,
                arrived_at=arrived_at,
                assessed_at=assessed_at,
                departed_at=departed_at,
                waiting_seconds=_seconds_between(arrived_at, departed_at),
                processing_seconds=_seconds_between(assessed_at, departed_at),
            )
        )

    entries.sort(key=lambda entry: (entry.departed_at, entry.encounter_id))
    completed = len(entries)
    if completed == 0:
        return PerformanceReport(0, 0.0, 0.0, [])
    return PerformanceReport(
        completed=completed,
        average_waiting_seconds=round(
            sum(entry.waiting_seconds for entry in entries) / completed, 1
        ),
        average_processing_seconds=round(
            sum(entry.processing_seconds for entry in entries) / completed, 1
        ),
        entries=entries,
    )


def _seconds_between(start: datetime, end: datetime) -> int:
    """Whole seconds, never negative even if a stored pair is out of order."""
    return max(0, int((end - start).total_seconds()))
