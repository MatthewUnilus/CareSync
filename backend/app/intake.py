"""The reason for a visit, and how it is written onto an Encounter.

A visit carries a reason for the visit. Opening a visit records it, and it may be
corrected afterwards: nothing freezes it any more, now that the engine whose
inputs were once held here has been removed.

Vital signs do not live on a visit; every set of vitals is its own Observation
(ADR 0008), which lands in a later ticket. A visit's payload is therefore the
reason alone (``VisitReasonPayload``), and the full ``IntakePayload`` the
Observation chart will validate against is kept for ticket 30.
"""

from app.models import Encounter
from app.schemas import VisitReasonPayload


def apply_visit_reason(encounter: Encounter, reason: VisitReasonPayload) -> None:
    """Write the supplied reason onto the Encounter, without committing.

    Used when a visit is opened and when its reason is corrected. Only the reason
    for the visit is kept on the Encounter; vitals have no home on a visit and are
    refused at the request boundary rather than dropped here.
    """
    encounter.reason_for_visit = reason.presenting_complaint
