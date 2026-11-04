"""Departure: a Clinical user discharges an Encounter from the Queue.

Departure is manual only. Nothing here schedules, polls, times out or cascades:
the departure instant is written when the action is performed and at no other
moment. An Encounter therefore carries exactly two conditions, both derived
from the one nullable column ``Encounter.departed_at``:

* **awaiting** while ``departed_at`` is null — on the Queue;
* **departed** once it is set — off the Queue, still readable.

Keeping the condition derived means there is no second status column that could
contradict the instant. The same guard is shared with every other clinical
action that needs an awaiting Encounter, so a departed Encounter is refused at
the API boundary consistently (ticket 09's Override, and ticket 10's
Re-assessment when it lands).
"""

from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Encounter
from app.timeutils import utc_now

ALREADY_DEPARTED_DETAIL = (
    "An Encounter that has already departed cannot be departed again"
)
# Ticket 10's Re-assessment route refuses through ``ensure_awaiting`` with this
# message, so both clinical actions that need an awaiting Encounter speak in
# the same terms.
REASSESSMENT_DEPARTED_DETAIL = (
    "A departed Encounter cannot be re-assessed"
)


class EncounterStatus(str, Enum):
    """The only two conditions an Encounter can hold in this scope."""

    awaiting = "awaiting"
    departed = "departed"


def encounter_status(encounter: Encounter) -> EncounterStatus:
    return (
        EncounterStatus.awaiting
        if encounter.departed_at is None
        else EncounterStatus.departed
    )


def ensure_awaiting(encounter: Encounter, detail: str) -> None:
    """Refuse a clinical action on an Encounter that has already departed.

    Each caller states what could not be done, so the ``409`` explains the
    refusal in the action's own terms.
    """
    if encounter.departed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


def perform_departure(session: Session, encounter: Encounter) -> Encounter:
    """Record the departure instant *now*, without committing.

    The caller commits, so the instant and nothing else lands in one
    transaction. The instant is the server's clock at the moment of the
    action; it is never accepted from the caller.
    """
    ensure_awaiting(encounter, ALREADY_DEPARTED_DETAIL)
    encounter.departed_at = utc_now()
    return encounter
