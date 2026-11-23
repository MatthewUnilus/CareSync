"""Medication Orders, the round-time convention, and the derived due list.

A doctor's medication instruction is transcribed once as a Medication Order and
the ward can then see what is due and what is overdue across every patient from
one list. This module owns the two halves of that which are policy or derivation:

* the **round-time convention** — the times of day a frequency maps to, held here
  in one place as a documented default so the hospital's own set replaces it
  without touching the routes or the table. It is a convention, not clinical
  advice, and there is no single right set (ticket 34).
* the **due list** — computed at read time from the orders on open Admissions
  and the round times. It is never stored: a stored due list drifts from the
  orders that generate it, which is the reports discipline. Reading it writes
  nothing. A stopped order stops producing *further* doses; the doses already
  scheduled before it was stopped stay in the list, because they were due at a
  time the order was live and the record must not rewrite that.

The order is a transcription, not a prescription (ADR 0011). Nothing here
calculates a dose, checks a dose against a maximum, or checks interactions or
allergies: the system holds no allergy or interaction data and the ticket is not
the place to invent it. As-required (PRN) medication, continuous infusions and
variable-dose medication are deliberately **out of scope**: a due list that
quietly mishandled them would be worse than one that says it does not cover
them, so a frequency that names one is refused with a ``422`` that says so.

The functions that stage an order never commit: the route commits, so the order,
its stop and its single audit entry land in one transaction (ADR 0007).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Admission,
    MedicationAdministration,
    MedicationOrder,
    User,
)
from app.schemas import (
    DueDoseResponse,
    MedicationFrequencyResponse,
    MedicationOrderResponse,
    PatientResponse,
    RoundTimesResponse,
)
from app.timeutils import as_utc, utc_now

#: How far ahead of the server's clock a dose still counts as "due now" on the
#: board rather than "upcoming". A dose whose round time has passed is overdue;
#: one within this window after it is due now. The board's three counts share
#: this one rule, read against one clock at request time.
DUE_SOON_WINDOW = timedelta(hours=1)

#: One day and one microsecond as exact durations. The board's counts are worked
#: out by arithmetic over a frequency's fixed times rather than by walking every
#: day from the order's start, so a long-running order is counted in bounded
#: time. ``_DAY_MICROSECONDS`` is one day in whole microseconds, so the division
#: that turns a span into a number of doses stays in integers.
_DAY = timedelta(days=1)
_MICROSECOND = timedelta(microseconds=1)
_DAY_MICROSECONDS = 86_400_000_000

#: The largest window the due list will derive in one read. A derived list over
#: an unbounded range is a way to make the server work for no clinical reason, so
#: a wider request is refused rather than served.
MAX_DUE_RANGE = timedelta(days=7)

UNKNOWN_FREQUENCY_DETAIL = "Unknown medication frequency"
DUE_RANGE_INVALID_DETAIL = "The due-list window must end after it starts"
DUE_RANGE_EXCEEDED_DETAIL = "The due-list window may not exceed 7 days"
ORDER_NOT_FOUND_DETAIL = "Medication order not found"
ORDER_ALREADY_STOPPED_DETAIL = "A stopped Medication Order cannot be stopped again"
DISCHARGED_ORDER_DETAIL = (
    "A discharged Admission cannot take new Medication Orders"
)

#: Frequencies this ticket deliberately does not cover, and why. The message is
#: the ``422`` detail, so the refusal says which awkward case is out of scope
#: rather than reporting a generic unknown key.
UNSUPPORTED_FREQUENCIES: dict[str, str] = {
    "prn": "As-required (PRN) medication is out of scope for the due list",
    "as_required": "As-required (PRN) medication is out of scope for the due list",
    "continuous": "Continuous infusions are out of scope for the due list",
    "continuous_infusion": (
        "Continuous infusions are out of scope for the due list"
    ),
    "infusion": "Continuous infusions are out of scope for the due list",
    "variable": "Variable-dose medication is out of scope for the due list",
    "variable_dose": "Variable-dose medication is out of scope for the due list",
}


@dataclass(frozen=True)
class RoundFrequency:
    """One frequency and the clock times of day it maps to.

    ``times`` are ``HH:MM`` strings on the ward's clock. They are the provisional
    convention below; a frequency that has no entry here is refused rather than
    given an invented schedule.
    """

    key: str
    label: str
    times: tuple[str, ...]


#: The provisional ward round-time convention, in the order it is served. There
#: is no single right set: this is a documented default a hospital replaces with
#: its own. The times are read against the server's UTC clock, because this build
#: carries no ward timezone; a real deployment would hold the ward's zone here.
ROUND_FREQUENCIES: tuple[RoundFrequency, ...] = (
    RoundFrequency("once_daily", "Once daily", ("08:00",)),
    RoundFrequency("twice_daily", "Twice daily", ("08:00", "20:00")),
    RoundFrequency(
        "three_times_daily", "Three times daily", ("08:00", "14:00", "20:00")
    ),
    RoundFrequency(
        "four_times_daily",
        "Four times daily",
        ("06:00", "12:00", "18:00", "22:00"),
    ),
)

_FREQUENCY_BY_KEY: dict[str, RoundFrequency] = {
    frequency.key: frequency for frequency in ROUND_FREQUENCIES
}


@dataclass(frozen=True)
class DueDose:
    """One dose a schedule places in a window, with its order and lateness."""

    order: MedicationOrder
    due_at: datetime
    overdue: bool


@dataclass(frozen=True)
class MedicationCounts:
    """The board's three medication figures for one Admission, from the schedule."""

    overdue: int
    due: int
    outstanding: int


def resolve_frequency(value: str) -> RoundFrequency:
    """The frequency the key names, or a ``422`` saying why it is refused.

    A key that names an out-of-scope case (PRN, an infusion, a variable dose)
    gets a message that says so; anything else is a plain unknown key. Nothing is
    guessed into a schedule.
    """
    key = value.strip().lower()
    frequency = _FREQUENCY_BY_KEY.get(key)
    if frequency is not None:
        return frequency
    unsupported = UNSUPPORTED_FREQUENCIES.get(key)
    if unsupported is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=unsupported,
        )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=UNKNOWN_FREQUENCY_DETAIL,
    )


def round_times_response() -> RoundTimesResponse:
    """The frequency-to-round-times convention as the API serves it."""
    return RoundTimesResponse(
        frequencies=[
            MedicationFrequencyResponse(
                key=frequency.key,
                label=frequency.label,
                times=list(frequency.times),
            )
            for frequency in ROUND_FREQUENCIES
        ]
    )


def stage_order(
    session: Session,
    *,
    admission: Admission,
    actor: User,
    drug: str,
    dose: str,
    route: str,
    frequency: RoundFrequency,
    start_at: datetime,
    instructed_by: str,
) -> MedicationOrder:
    """Build one Medication Order and add it, without committing.

    ``frequency`` is the resolved convention, stored by key. The caller commits,
    so the order and its single audit entry land in one transaction.
    """
    order = MedicationOrder(
        admission=admission,
        actor=actor,
        drug=drug,
        dose=dose,
        route=route,
        frequency=frequency.key,
        start_at=start_at,
        instructed_by=instructed_by,
    )
    session.add(order)
    return order


def stop_order(session: Session, order: MedicationOrder) -> MedicationOrder:
    """Stop an active order, recording the instant *now*, without committing.

    The instant is the server's clock at the moment of the action, never a value
    the caller supplies: stopping is a deliberate act, and the clock is the
    system's. A stopped order produces no *further* due doses: the doses already
    scheduled before this instant stay in the due list, so the record shows what
    was due while the order was live and does not rewrite the past. An order that
    has already been stopped is refused with ``409`` rather than moved, so the one
    recorded stop instant is not overwritten.
    """
    if order.stopped_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ORDER_ALREADY_STOPPED_DETAIL,
        )
    order.stopped_at = utc_now()
    return order


def orders_for_admission(
    session: Session, admission: Admission
) -> list[MedicationOrder]:
    """One Admission's orders, oldest first, including stopped ones.

    A stopped order is part of the record, not deleted, so the history shows both
    the order that was stopped and the order that replaced it.
    """
    return list(
        session.scalars(
            select(MedicationOrder)
            .where(MedicationOrder.admission_id == admission.id)
            .order_by(MedicationOrder.id)
        ).all()
    )


def order_response(order: MedicationOrder) -> MedicationOrderResponse:
    """Render one order, with its condition derived from its stopped instant.

    The condition comes from the model's own ``status`` property, so there is one
    definition of active-versus-stopped rather than a copy here.
    """
    return MedicationOrderResponse(
        id=order.id,
        admission_id=order.admission_id,
        drug=order.drug,
        dose=order.dose,
        route=order.route,
        frequency=order.frequency,
        start_at=order.start_at,
        instructed_by=order.instructed_by,
        status=order.status,
        stopped_at=order.stopped_at,
    )


def validate_due_window(start: datetime, end: datetime) -> None:
    """Refuse a window that does not advance, or one wider than the cap.

    The due list is inclusive of ``start`` and exclusive of ``end``; a window
    that does not advance is refused, and a range wider than ``MAX_DUE_RANGE`` is
    refused rather than derived.
    """
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=DUE_RANGE_INVALID_DETAIL,
        )
    if end - start > MAX_DUE_RANGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=DUE_RANGE_EXCEEDED_DETAIL,
        )


def order_slots(
    order: MedicationOrder, start: datetime, end: datetime
) -> list[datetime]:
    """One order's round-time slots within ``[start, end)``, sorted.

    The public read of the derivation the grid and the admission history need:
    the same instants the due list would produce for one order, in the order they
    fall.
    """
    return sorted(_order_slots(order, as_utc(start), as_utc(end)))


def is_order_slot(order: MedicationOrder, due_at: datetime) -> bool:
    """Whether ``due_at`` is one of the order's round-time slots.

    A slot's identity is a round time of the order's frequency on or after the
    order's start, and before its stop when it is stopped. A value that is not
    such an instant is a made-up slot: an administration must answer a dose the
    schedule actually placed, so a made-up one is refused (``422``) rather than
    recorded.
    """
    due_at = as_utc(due_at)
    if due_at.second or due_at.microsecond:
        return False
    order_start = as_utc(order.start_at)
    if due_at < order_start:
        return False
    if order.stopped_at is not None and due_at >= as_utc(order.stopped_at):
        return False
    for hour, minute in _parsed_times(order.frequency):
        first = _first_slot_at_or_after(order_start, hour, minute)
        if due_at < first:
            continue
        if (due_at - first) % _DAY == timedelta(0):
            return True
    return False


def due_doses(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    now: datetime | None = None,
) -> list[DueDose]:
    """Every dose due in ``[start, end)`` across the ward, derived at read time.

    A dose is produced by an order that was live when the dose fell: an active
    order produces doses through the window, and a stopped order still produces
    the doses scheduled *before* it was stopped, so the record shows what was due
    at the time rather than rewriting it. A discharged Admission has left the
    ward and produces nothing. A dose slot that has been recorded is no longer
    *due* — it has been dealt with — so a recorded slot leaves this list and the
    record stays readable through the administration read instead. The window is
    inclusive of ``start`` and exclusive of ``end``, so two adjacent windows share
    no boundary dose, and a stopped order's slots are additionally exclusive of
    its stop instant. ``overdue`` is measured against the server's clock (``now``,
    defaulting to ``utc_now``). The result is sorted by due time, breaking ties on
    the order id, so the list reads in the order the doses fall.
    """
    now = now or utc_now()
    start = as_utc(start)
    end = as_utc(end)
    orders = session.scalars(
        select(MedicationOrder)
        .join(Admission, MedicationOrder.admission_id == Admission.id)
        .where(Admission.discharged_at.is_(None))
        .order_by(MedicationOrder.id)
    ).all()
    recorded = _recorded_slot_keys(session, start=start, end=end)
    doses = [
        DueDose(order=order, due_at=due_at, overdue=due_at < now)
        for order in orders
        for due_at in _order_slots(order, start, end)
        if (order.id, due_at) not in recorded
    ]
    doses.sort(key=lambda dose: (dose.due_at, dose.order.id))
    return doses


def _recorded_slot_keys(
    session: Session, *, start: datetime, end: datetime
) -> set[tuple[int, datetime]]:
    """The ``(order_id, due_at)`` slots already recorded within ``[start, end)``.

    Read once per due-list derivation so a recorded slot is subtracted without a
    query per slot. ``due_at`` is normalised to UTC, matching the instants the
    derivation produces, because SQLite round-trips aware timestamps as naive.
    """
    rows = session.scalars(
        select(MedicationAdministration).where(
            MedicationAdministration.due_at >= start,
            MedicationAdministration.due_at < end,
        )
    ).all()
    return {(row.order_id, as_utc(row.due_at)) for row in rows}


def dose_response(dose: DueDose) -> DueDoseResponse:
    """Render one derived dose, with the Admission's Patient inline."""
    order = dose.order
    return DueDoseResponse(
        order_id=order.id,
        admission_id=order.admission_id,
        patient=PatientResponse.model_validate(order.admission.patient),
        drug=order.drug,
        dose=order.dose,
        route=order.route,
        due_at=dose.due_at,
        overdue=dose.overdue,
    )


def medication_counts(
    session: Session,
    admission: Admission,
    *,
    now: datetime | None = None,
) -> MedicationCounts:
    """The board's three medication figures for one Admission, from the schedule.

    ``overdue`` counts doses whose round time has passed and nothing recorded
    them; ``due`` counts doses in the window just after their round time; and
    ``outstanding`` is the two together, the doses not yet given that the record
    shows. A recorded dose slot is no longer outstanding, so the recorded slots in
    each window are subtracted; the record stays readable through the
    administration read instead of the count. All three are read against one
    clock. A discharged Admission has nothing outstanding. A stopped order still
    contributes the doses scheduled before it was stopped, so a dose that went
    unrecorded while the order was live stays counted rather than quietly
    disappearing.

    The count is worked out per fixed round time by arithmetic over the span from
    the order's start to the clock, not by walking every day in between, so a long
    running order costs the same to count as a new one; the recorded slots are
    read per order and subtracted from that arithmetic, so the count stays bounded
    by the record rather than by the days since the order started.
    """
    now = now or utc_now()
    if admission.discharged_at is not None:
        return MedicationCounts(overdue=0, due=0, outstanding=0)
    orders = orders_for_admission(session, admission)
    if not orders:
        return MedicationCounts(overdue=0, due=0, outstanding=0)
    end = now + DUE_SOON_WINDOW
    overdue = 0
    due = 0
    for order in orders:
        order_overdue, order_due = _order_slot_counts(order, now=now, end=end)
        recorded_overdue, recorded_due = _recorded_slot_counts(
            session, order, now=now, end=end
        )
        overdue += max(order_overdue - recorded_overdue, 0)
        due += max(order_due - recorded_due, 0)
    return MedicationCounts(
        overdue=overdue, due=due, outstanding=overdue + due
    )


def _order_slot_counts(
    order: MedicationOrder, *, now: datetime, end: datetime
) -> tuple[int, int]:
    """``(overdue, due)`` for one order, counting each fixed round time exactly.

    For each clock time the frequency maps to, the doses are one per day from the
    first one at or after the order's start. The number before an instant is the
    number of whole days from that first dose to the instant, so the span is
    turned into a count directly rather than iterated. A stopped order's doses are
    bounded by its stop instant, exclusive.
    """
    order_start = as_utc(order.start_at)
    upper = _order_end(order, end)
    if upper <= order_start:
        return 0, 0
    ceiling = min(now, upper)
    overdue = 0
    due = 0
    for hour, minute in _parsed_times(order.frequency):
        first = _first_slot_at_or_after(order_start, hour, minute)
        overdue += _slot_count_before(first, ceiling)
        due += _slot_count_before(first, upper) - _slot_count_before(
            first, ceiling
        )
    return overdue, due


def _recorded_slot_counts(
    session: Session,
    order: MedicationOrder,
    *,
    now: datetime,
    end: datetime,
) -> tuple[int, int]:
    """``(overdue, due)`` recorded slots for one order, to subtract from the count.

    A recorded slot has been dealt with, so it is no longer outstanding. The
    slots are classified against the same boundaries the arithmetic count uses:
    before ``ceiling`` (the clock, capped by the order's end) is overdue, and from
    ``ceiling`` up to the window end is due. A slot past the order's end is not
    counted, matching the schedule. The rows are read per order, so the count
    stays bounded by the record rather than the days since the order started.
    """
    order_start = as_utc(order.start_at)
    upper = _order_end(order, end)
    if upper <= order_start:
        return 0, 0
    ceiling = min(now, upper)
    overdue = 0
    due = 0
    rows = session.scalars(
        select(MedicationAdministration.due_at).where(
            MedicationAdministration.order_id == order.id
        )
    ).all()
    for raw in rows:
        due_at = as_utc(raw)
        if due_at < order_start:
            continue
        if due_at < ceiling:
            overdue += 1
        elif due_at < upper:
            due += 1
    return overdue, due


def _order_end(order: MedicationOrder, end: datetime) -> datetime:
    """The instant an order stops producing doses: its stop, or the window end.

    Exclusive: a dose exactly at the stop instant is not produced, because the
    order is no longer live from that instant. An active order ends at ``end``.
    """
    if order.stopped_at is None:
        return end
    return min(end, as_utc(order.stopped_at))


def _first_slot_at_or_after(
    moment: datetime, hour: int, minute: int
) -> datetime:
    """The first dose at ``hour:minute`` on or after ``moment``.

    The order's start is a time of day, and a dose falls at the frequency's clock
    times; the first dose is the first such time at or after the start, so a start
    of 09:00 on a once-daily 08:00 order first doses at 08:00 the next day.
    """
    candidate = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate < moment:
        candidate += _DAY
    return candidate


def _slot_count_before(first: datetime, moment: datetime) -> int:
    """How many daily doses from ``first`` fall strictly before ``moment``.

    The doses are ``first + k days`` for ``k`` from zero, so the count is the
    number of whole days that fit below the span, with a dose exactly at
    ``moment`` excluded (the span is strict). ``timedelta`` floors toward negative
    infinity, so the span is measured in whole microseconds to keep the arithmetic
    in integers.
    """
    span = moment - first
    if span <= timedelta(0):
        return 0
    micros = span // _MICROSECOND
    return (micros - 1) // _DAY_MICROSECONDS + 1


def _order_slots(
    order: MedicationOrder, start: datetime, end: datetime
) -> Iterator[datetime]:
    """The round-time instants one order falls on within ``[start, end)``.

    A dose falls at each of the frequency's clock times on each day, from the
    order's ``start_at`` onward; a slot before the order started is not a dose. A
    stopped order's slots stop at its stop instant, exclusive, so the window is
    bounded by ``min(end, stopped_at)`` for a stopped order. The window is
    inclusive of ``start`` and exclusive of ``end``. The window is capped by the
    caller, so the day walk here is bounded.
    """
    order_start = as_utc(order.start_at)
    end = _order_end(order, end)
    times = _parsed_times(order.frequency)
    if not times:
        return
    day: date = (start - _DAY).date()
    last = end.date()
    while day <= last:
        for hour, minute in times:
            due_at = datetime(
                day.year,
                day.month,
                day.day,
                hour,
                minute,
                tzinfo=UTC,
            )
            if due_at < order_start or due_at < start or due_at >= end:
                continue
            yield due_at
        day += _DAY


def _parsed_times(frequency_key: str) -> tuple[tuple[int, int], ...]:
    """The ``(hour, minute)`` pairs of a stored frequency key, or none for an
    unknown key (which the boundary refuses, so it is never stored)."""
    frequency = _FREQUENCY_BY_KEY.get(frequency_key)
    if frequency is None:
        return ()
    return tuple(_parse_hhmm(value) for value in frequency.times)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)
