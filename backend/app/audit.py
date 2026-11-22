"""Recording clinical mutations in the audit log.

Every clinical mutation appends exactly one entry here, and the entry shares the
transaction with the change it describes. This module **adds** the entry to the
session and never commits. The route commits, so the mutation and its record
land or fail together — a rolled-back change cannot leave an audit entry
behind, and a state change cannot be committed without its record.

The one caller that could not follow that shape unchanged is registration:
``patients.find_or_create_patient`` used to commit internally, which would have
closed the transaction before the entry was staged. That commit boundary was
lifted to the route (see ``app.routers.clinical.register_patient``), which is
why this module's contract — add, never commit — holds. The route is the single
committer in every case.

An entry names the actor by foreign key and the subjects it touched. Not every
action reaches every subject, so the subject arguments are optional and default
to absent; registration, for instance, touches a Patient but no Encounter.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_actions import AuditAction
from app.models import AuditEntry, Encounter, Patient, User
from app.timeutils import utc_now


def record_audit_entry(
    session: Session,
    *,
    actor: User,
    action: AuditAction,
    patient: Patient | None = None,
    encounter: Encounter | None = None,
    detail: str | None = None,
) -> AuditEntry:
    """Stage one audit entry for a clinical mutation, without committing.

    The caller commits. The subjects are passed as objects, not ids, because an
    action may reference a subject that is still pending in the same flush —
    registration's Patient and open-encounter's Encounter both are — and the
    relationship lets SQLAlchemy resolve the key when that happens.
    """
    entry = AuditEntry(
        actor=actor,
        action=action.value,
        detail=detail,
        recorded_at=utc_now(),
        patient=patient,
        encounter=encounter,
    )
    session.add(entry)
    return entry


def read_audit_log(
    session: Session,
    *,
    encounter_id: int | None = None,
) -> list[AuditEntry]:
    """Return the log oldest-first, optionally narrowed to one Encounter.

    Oldest-first is the order the acts happened, which is the order a reader
    reconstructs a visit in. ``encounter_id`` filters to a single Encounter so
    one visit's history can be read on its own; entries with no Encounter
    (registration) are naturally excluded by that filter.
    """
    statement = select(AuditEntry).order_by(AuditEntry.id)
    if encounter_id is not None:
        statement = statement.where(AuditEntry.encounter_id == encounter_id)
    return list(session.scalars(statement).all())
