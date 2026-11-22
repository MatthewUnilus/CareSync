"""The reason for a visit, and how it is written onto an Encounter.

A visit carries a reason for the visit. Opening a visit records it, and it may be
corrected afterwards: nothing freezes it any more, now that the engine whose
inputs were once held here has been removed.

Vital signs do not live on a visit; every set of vitals is its own Observation
(ADR 0008). A visit's payload is therefore the reason alone
(``VisitReasonPayload``), or the full ``IntakePayload`` when the first set of
vitals is captured as the visit is opened — in which case the reason is written
here and the readings become the visit's first Observation, in the same
transaction. Either way the Encounter keeps only the reason; a posted set of
vitals is never dropped on the floor.
"""

from app.models import Encounter
from app.schemas import IntakePayload, VisitReasonPayload


def apply_visit_reason(
    encounter: Encounter,
    reason: VisitReasonPayload | IntakePayload,
) -> None:
    """Write the supplied reason onto the Encounter, without committing.

    Used when a visit is opened and when its reason is corrected. Only the reason
    for the visit is kept on the Encounter; vitals have no home on a visit, so a
    full ``IntakePayload`` contributes its reason here and its readings become an
    Observation at the route, never a column on the Encounter.
    """
    encounter.reason_for_visit = reason.presenting_complaint
