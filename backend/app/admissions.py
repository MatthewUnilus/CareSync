"""Ward admissions: inpatient stays, location moves, and the discharge that ends them.

An Admission is a period of inpatient care with a location (ADR 0008): it is
*not* an Encounter. Like an Encounter, a stay carries exactly two conditions,
both derived from the one nullable column ``Admission.discharged_at``:

* **open** while ``discharged_at`` is null — the Patient is on the ward;
* **discharged** once it is set — the stay is over and leaves the Ward Board,
  still readable.

Keeping the condition derived means there is no second status column that could
contradict the instant. This is the reduced shape ``app.departures`` follows for
the end of a visit, kept for exactly this reason (ticket 26).

The functions here stage a change and never commit: the route commits, so the
Admission and its single audit entry land in one transaction (ADR 0007).
"""

from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Admission, Encounter, Patient
from app.timeutils import utc_now

#: Refused when a move is asked of a stay that has already ended. Each caller
#: states what could not be done, so the ``409`` reads in the action's own terms.
MOVE_DISCHARGED_DETAIL = "A discharged Admission cannot be moved"
ALREADY_DISCHARGED_DETAIL = (
    "An Admission that has already been discharged cannot be discharged again"
)


class AdmissionStatus(str, Enum):
    """The only two conditions an Admission can hold in this scope."""

    open = "open"
    discharged = "discharged"


def admission_status(admission: Admission) -> AdmissionStatus:
    return (
        AdmissionStatus.open
        if admission.discharged_at is None
        else AdmissionStatus.discharged
    )


def ensure_open(admission: Admission, detail: str) -> None:
    """Refuse a clinical action on a stay that has already been discharged."""
    if admission.discharged_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


def admit(
    session: Session,
    *,
    patient: Patient,
    ward: str,
    bed: str,
    encounter: Encounter | None = None,
) -> Admission:
    """Stage a new Admission, without committing.

    A direct admission has no prior visit (``encounter`` is None); one that came
    from a visit links the Encounter so the visit and the stay read as one
    history. The caller commits.
    """
    admission = Admission(
        patient=patient,
        ward=ward,
        bed=bed,
        encounter=encounter,
    )
    session.add(admission)
    return admission


def move(
    session: Session,
    admission: Admission,
    *,
    ward: str,
    bed: str,
) -> Admission:
    """Record a location move on an open stay, without committing.

    A discharged stay cannot be moved: it has left the working view and its
    location is part of what it was, not something to change after the fact.
    """
    ensure_open(admission, MOVE_DISCHARGED_DETAIL)
    admission.ward = ward
    admission.bed = bed
    return admission


def discharge(session: Session, admission: Admission) -> Admission:
    """Record the discharge instant *now*, without committing.

    The instant is the server's clock at the moment of the action; it is never
    accepted from the caller. Discharge is manual only — nothing schedules it —
    and a stay that has already ended cannot be discharged again.
    """
    ensure_open(admission, ALREADY_DISCHARGED_DETAIL)
    admission.discharged_at = utc_now()
    return admission
