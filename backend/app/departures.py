"""The end of a visit: a Clinical user ends an Encounter.

Ending a visit is manual only. Nothing here schedules, polls, times out or
cascades: the end-of-visit instant is written when the action is performed and
at no other moment. An Encounter therefore carries exactly two conditions, both
derived from the one nullable column ``Encounter.ended_at``:

* **open** while ``ended_at`` is null — the visit is under way;
* **ended** once it is set — the visit is over, still readable.

Keeping the condition derived means there is no second status column that could
contradict the instant. There are no queue semantics here any more: the visit is
simply open or ended.
"""

from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Encounter
from app.timeutils import utc_now

ALREADY_ENDED_DETAIL = (
    "An Encounter that has already ended cannot be ended again"
)


class EncounterStatus(str, Enum):
    """The only two conditions an Encounter can hold in this scope."""

    open = "open"
    ended = "ended"


def encounter_status(encounter: Encounter) -> EncounterStatus:
    return (
        EncounterStatus.open
        if encounter.ended_at is None
        else EncounterStatus.ended
    )


def ensure_open(encounter: Encounter, detail: str) -> None:
    """Refuse a clinical action on an Encounter that has already ended.

    Each caller states what could not be done, so the ``409`` explains the
    refusal in the action's own terms.
    """
    if encounter.ended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


def end_encounter(session: Session, encounter: Encounter) -> Encounter:
    """Record the end-of-visit instant *now*, without committing.

    The caller commits, so the instant and nothing else lands in one
    transaction. The instant is the server's clock at the moment of the action;
    it is never accepted from the caller.
    """
    ensure_open(encounter, ALREADY_ENDED_DETAIL)
    encounter.ended_at = utc_now()
    return encounter
