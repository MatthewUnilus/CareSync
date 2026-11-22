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
