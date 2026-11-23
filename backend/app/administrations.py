"""Medication Administrations: the record of what happened to each due dose.

A dose is recorded once per ``(order, due time)`` as given, withheld, refused or
unavailable; where it was not given a reason explains the omission, so not giving
a dose is as recordable as giving it. The record says what a nurse attests to:
there is no barcode or wristband verification and none is added here, no dose is
calculated and no value is interpreted (ticket 35).

Three properties this module owns:

* **The reason vocabulary** — a fixed set held once here, served to the client,
  validated against the request, with the free text permitted only for ``other``
  (the pattern the deleted Override Reason used). It keeps the reason set
  reportable rather than becoming free commentary.
* **The slot rules** — a due time must be an actual round time of the order, not
  in the future, and a slot can be recorded only once (a unique constraint backs
  the last rule). A dose not yet due is refused: recording it would remove a dose
  from the due list and the board before it fell. A dose with a past due time can
  still be recorded and — where it was given — is marked ``late``, a display mark
  that records a dose given after its round time rather than refusing the entry;
  a dose that was not given is never late.
* **The grid and the history** — one order's doses over a window, and one
  Admission's doses across its orders: what was due, what happened, when and by
  whom. They are derived at read time and store nothing.

Nothing here escalates, cancels or changes an order for an overdue dose: an
overdue slot stays visible as overdue until it is recorded and the system does
nothing about it (ADR 0010's rule, restated for the ward). The functions that
record never commit: the route commits, so the administration and its single
Audit Entry land in one transaction (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import medications
from app.admissions import ensure_open
from app.models import (
    AdministrationOutcome,
    Admission,
    MedicationAdministration,
    MedicationOrder,
    User,
)
from app.schemas import (
    ActorResponse,
    AdministrationGridOrderResponse,
    AdministrationGridSlotResponse,
    AdministrationReasonResponse,
    AdmissionAdministrationHistoryResponse,
    AdmissionAdministrationSlotResponse,
    MedicationAdministrationGridResponse,
    MedicationAdministrationReasonResponse,
    MedicationAdministrationReasonsResponse,
    MedicationAdministrationResponse,
)
from app.timeutils import as_utc, utc_now

#: The largest window a grid or a history will derive in one read. A derived list
#: over an unbounded range is a way to make the server work for no clinical
#: reason, so a wider request is refused rather than served. The seven-day due
#: list and the one-week chart a nurse reads both fit inside it.
MAX_ADMIN_RANGE = timedelta(days=31)

UNKNOWN_OUTCOME_DETAIL = "Unknown medication administration outcome"
UNKNOWN_REASON_DETAIL = "Unknown medication administration reason"
REASON_REQUIRED_DETAIL = "A reason is required when the outcome is not given"
REASON_NOT_ALLOWED_DETAIL = (
    "A reason is recorded only when the outcome is not given"
)
REASON_TEXT_ONLY_FOR_OTHER_DETAIL = (
    "Free text is permitted only for the 'other' reason"
)
REASON_TEXT_REQUIRED_DETAIL = "Free text is required for the 'other' reason"
DUPLICATE_SLOT_DETAIL = "This dose slot has already been recorded"
INVALID_SLOT_DETAIL = (
    "The due time is not a round time of this Medication Order"
)
FUTURE_SLOT_DETAIL = "This dose is not yet due and cannot be recorded"
DISCHARGED_ADMISSION_DETAIL = (
    "A discharged Admission cannot take new Medication Administrations"
)
ADMIN_RANGE_INVALID_DETAIL = "The administration window must end after it starts"
ADMIN_RANGE_EXCEEDED_DETAIL = (
    "The administration window may not exceed 31 days"
)

#: The outcome the reason rules turn on: a reason explains a dose that was *not*
#: given, and is absent on the one that was.
_GIVEN = AdministrationOutcome.given


@dataclass(frozen=True)
class AdministrationReason:
    """One key of the fixed administration-reason vocabulary.

    ``requires_text`` is true for ``other`` alone; the free text is permitted only
    for that key, so a reason set of short codes stays reportable.
    """

    key: str
    label: str
    requires_text: bool


#: The fixed reason set, in the order it is served. A reason is required whenever
#: a dose was not given, so the omission is explained. The wording follows the
#: nurse's own description of the work and is expected to be checked against the
#: hospital's chart, because the words for refusal and unavailability differ
#: between wards (ticket 35).
ADMINISTRATION_REASONS: tuple[AdministrationReason, ...] = (
    AdministrationReason(key="not_available", label="Not available", requires_text=False),
    AdministrationReason(
        key="patient_refused", label="Patient refused", requires_text=False
    ),
    AdministrationReason(key="withheld", label="Withheld", requires_text=False),
    AdministrationReason(
        key="patient_nil_by_mouth",
        label="Patient nil by mouth",
        requires_text=False,
    ),
    AdministrationReason(key="other", label="Other", requires_text=True),
)

_REASON_BY_KEY: dict[str, AdministrationReason] = {
    reason.key: reason for reason in ADMINISTRATION_REASONS
}

#: The state a slot shows when nothing is recorded against it: measured against
#: the clock at read time, so a dose past its round time reads overdue and a dose
#: ahead reads pending. The ``due`` band reuses the board's one window so a slot
#: reads "due" in exactly the places the board counts it as due.
_STATE_OVERDUE = "overdue"
_STATE_DUE = "due"
_STATE_PENDING = "pending"


def reasons_response() -> MedicationAdministrationReasonsResponse:
    """The reason vocabulary as the API serves it."""
    return MedicationAdministrationReasonsResponse(
        reasons=[
            MedicationAdministrationReasonResponse(
                key=reason.key,
                label=reason.label,
                requires_text=reason.requires_text,
            )
            for reason in ADMINISTRATION_REASONS
        ]
    )


def resolve_outcome(value: str) -> AdministrationOutcome:
    """The outcome the key names, or a ``422`` for an unknown one."""
    try:
        return AdministrationOutcome(value.strip().lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=UNKNOWN_OUTCOME_DETAIL,
        ) from None


def resolve_reason(value: str) -> AdministrationReason:
    """The reason the key names, or a ``422`` for an unknown one."""
    reason = _REASON_BY_KEY.get(value.strip().lower())
    if reason is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=UNKNOWN_REASON_DETAIL,
        )
    return reason


def validate_reason(
    outcome: AdministrationOutcome,
    reason_key: str | None,
    reason_text: str | None,
) -> AdministrationReason | None:
    """Enforce the reason rules at the request boundary, returning the reason.

    A reason is required when the outcome is not given and absent when it is. The
    free text is permitted only for ``other``: supplying it with any other key is
    refused, and omitting it for ``other`` is refused, so the reason set stays
    reportable. A blank text is treated as absent.
    """
    text = (reason_text or "").strip() or None
    if outcome is _GIVEN:
        if reason_key is not None or text is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=REASON_NOT_ALLOWED_DETAIL,
            )
        return None
    if reason_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=REASON_REQUIRED_DETAIL,
        )
    reason = resolve_reason(reason_key)
    if reason.requires_text:
        if text is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=REASON_TEXT_REQUIRED_DETAIL,
            )
    elif text is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=REASON_TEXT_ONLY_FOR_OTHER_DETAIL,
        )
    return reason


def record_administration(
    session: Session,
    *,
    order: MedicationOrder,
    actor: User,
    due_at: datetime,
    outcome: str,
    reason_key: str | None,
    reason_text: str | None,
) -> MedicationAdministration:
    """Validate and stage one administration, without committing.

    The outcome and the reason are checked against the fixed vocabularies, the due
    time against the order's round times, and the slot against the record so it
    cannot be recorded twice. A dose that is not yet due is refused too: a slot
    whose due time is ahead of the server's clock has not happened, and recording
    it would remove a dose from the due list and the board before it fell. A
    discharged Admission takes no new record of this kind, matching the read rule
    that excludes it from the due list and the board. A made-up due time, a dose
    not yet due and a bad reason are ``422``; a discharged Admission and a slot
    already recorded are ``409``, refused rather than merged. The caller commits,
    so the administration and its single audit entry land together.
    """
    resolved_outcome = resolve_outcome(outcome)
    reason = validate_reason(resolved_outcome, reason_key, reason_text)
    due_at = as_utc(due_at)
    ensure_open(order.admission, DISCHARGED_ADMISSION_DETAIL)
    if not medications.is_order_slot(order, due_at):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=INVALID_SLOT_DETAIL,
        )
    if due_at > utc_now():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=FUTURE_SLOT_DETAIL,
        )
    if _slot_is_recorded(session, order_id=order.id, due_at=due_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DUPLICATE_SLOT_DETAIL,
        )
    stored_text = (
        (reason_text or "").strip() or None
        if reason is not None and reason.requires_text
        else None
    )
    administration = MedicationAdministration(
        order=order,
        actor=actor,
        due_at=due_at,
        outcome=resolved_outcome.value,
        reason_key=reason.key if reason is not None else None,
        reason_text=stored_text,
    )
    session.add(administration)
    return administration


def _slot_is_recorded(
    session: Session, *, order_id: int, due_at: datetime
) -> bool:
    """Whether ``(order_id, due_at)`` already has an administration.

    The application-layer pre-check that gives the second attempt its ``409``; the
    unique constraint over the two columns backs it against a race at commit time.
    """
    rows = session.scalars(
        select(MedicationAdministration.due_at).where(
            MedicationAdministration.order_id == order_id
        )
    ).all()
    return any(as_utc(raw) == due_at for raw in rows)


def administration_response(
    administration: MedicationAdministration,
) -> MedicationAdministrationResponse:
    """Render one recorded administration, with the drug and its reason inline."""
    order = administration.order
    recorded_at = as_utc(administration.recorded_at)
    return MedicationAdministrationResponse(
        id=administration.id,
        order_id=order.id,
        admission_id=order.admission_id,
        drug=order.drug,
        dose=order.dose,
        route=order.route,
        due_at=administration.due_at,
        outcome=AdministrationOutcome(administration.outcome),
        reason=_reason_response(administration),
        recorded_at=administration.recorded_at,
        actor=ActorResponse(
            id=administration.actor.id,
            display_name=administration.actor.display_name,
        ),
        late=(
            administration.outcome == AdministrationOutcome.given.value
            and recorded_at > as_utc(administration.due_at)
        ),
    )


def _reason_response(
    administration: MedicationAdministration,
) -> AdministrationReasonResponse | None:
    """The reason on a record, or None when the dose was given.

    The label comes from the one vocabulary beside the keys, so a client holds no
    copy of the mapping; an unrecognised stored key falls back to the key itself
    rather than leaking a raw value.
    """
    if administration.reason_key is None:
        return None
    known = _REASON_BY_KEY.get(administration.reason_key)
    return AdministrationReasonResponse(
        key=administration.reason_key,
        label=known.label if known is not None else administration.reason_key,
        text=administration.reason_text,
    )


def validate_admin_window(start: datetime, end: datetime) -> None:
    """Refuse a window that does not advance, or one wider than the cap.

    The grid and the history are inclusive of ``start`` and exclusive of ``end``.
    """
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ADMIN_RANGE_INVALID_DETAIL,
        )
    if end - start > MAX_ADMIN_RANGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ADMIN_RANGE_EXCEEDED_DETAIL,
        )


def administration_grid(
    session: Session,
    order: MedicationOrder,
    *,
    start: datetime,
    end: datetime,
    now: datetime | None = None,
) -> MedicationAdministrationGridResponse:
    """One order's doses over ``[start, end)``, as a chart reads.

    Each slot the order's schedule places in the window is shown with its recorded
    outcome where a dose was recorded, or its relation to the clock where it was
    not. The slots are sorted by due time. The window is capped by the caller, so
    the derivation is bounded.
    """
    now = now or utc_now()
    start = as_utc(start)
    end = as_utc(end)
    recorded = _administrations_in_window(
        session, order_ids=[order.id], start=start, end=end
    )
    return MedicationAdministrationGridResponse(
        order=_grid_order_response(order),
        slots=[
            AdministrationGridSlotResponse(
                due_at=due_at,
                state=_slot_state(
                    recorded.get((order.id, due_at)), due_at, now=now
                ),
                administration=_render_optional(recorded.get((order.id, due_at))),
            )
            for due_at in medications.order_slots(order, start, end)
        ],
    )


def admission_administration_history(
    session: Session,
    admission: Admission,
    *,
    start: datetime,
    end: datetime,
    now: datetime | None = None,
) -> AdmissionAdministrationHistoryResponse:
    """One Admission's doses over ``[start, end)``, across its orders.

    The history reads what was due, what happened, when and by whom: every slot
    the Admission's orders place in the window, each with its recorded outcome
    where a dose was recorded or its relation to the clock where it was not, all
    sorted by due time. A stopped order still contributes the doses it placed
    before it was stopped, so the history does not rewrite the past.
    """
    now = now or utc_now()
    start = as_utc(start)
    end = as_utc(end)
    orders = medications.orders_for_admission(session, admission)
    recorded = _administrations_in_window(
        session, order_ids=[order.id for order in orders], start=start, end=end
    )
    slots = [
        AdmissionAdministrationSlotResponse(
            order_id=order.id,
            drug=order.drug,
            dose=order.dose,
            route=order.route,
            due_at=due_at,
            state=_slot_state(
                recorded.get((order.id, due_at)), due_at, now=now
            ),
            administration=_render_optional(recorded.get((order.id, due_at))),
        )
        for order in orders
        for due_at in medications.order_slots(order, start, end)
    ]
    slots.sort(key=lambda slot: (slot.due_at, slot.order_id))
    return AdmissionAdministrationHistoryResponse(slots=slots)


def _administrations_in_window(
    session: Session,
    *,
    order_ids: list[int],
    start: datetime,
    end: datetime,
) -> dict[tuple[int, datetime], MedicationAdministration]:
    """The recorded slots for ``order_ids`` within ``[start, end)``, keyed.

    Read once for a whole grid or history so a slot's record is a lookup rather
    than a query per slot. ``due_at`` is normalised to UTC, matching the instants
    the derivation produces.
    """
    if not order_ids:
        return {}
    rows = session.scalars(
        select(MedicationAdministration).where(
            MedicationAdministration.order_id.in_(order_ids),
            MedicationAdministration.due_at >= start,
            MedicationAdministration.due_at < end,
        )
    ).all()
    return {(row.order_id, as_utc(row.due_at)): row for row in rows}


def _render_optional(
    administration: MedicationAdministration | None,
) -> MedicationAdministrationResponse | None:
    if administration is None:
        return None
    return administration_response(administration)


def _slot_state(
    administration: MedicationAdministration | None,
    due_at: datetime,
    *,
    now: datetime,
) -> str:
    """A slot's state: the recorded outcome, or its relation to the clock.

    A recorded slot shows what happened (given, withheld, refused or unavailable);
    an unrecorded one shows overdue, due or pending against one clock at read time.
    """
    if administration is not None:
        return administration.outcome
    due_at = as_utc(due_at)
    if due_at < now:
        return _STATE_OVERDUE
    if due_at < now + medications.DUE_SOON_WINDOW:
        return _STATE_DUE
    return _STATE_PENDING


def _grid_order_response(order: MedicationOrder) -> AdministrationGridOrderResponse:
    """The order a grid is charted for, with its condition derived."""
    return AdministrationGridOrderResponse(
        id=order.id,
        admission_id=order.admission_id,
        drug=order.drug,
        dose=order.dose,
        route=order.route,
        frequency=order.frequency,
        start_at=order.start_at,
        status=order.status,
        stopped_at=order.stopped_at,
    )
