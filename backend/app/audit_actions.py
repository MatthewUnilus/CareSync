"""The fixed Audit Action set.

One source of truth for what an audit entry can record: the data layer
constrains the stored column to exactly these values, so an action that is not
listed here cannot reach the table. The set is closed on purpose — it names the
clinical mutations the log covers, and nothing else (ADR 0001: validated strings
in the application layer, no database enums, no triggers).

Adding an action is a deliberate, reviewable change: a new clinical mutation
must appear here in the same commit that writes it, or its audit entry is
refused at the data layer.
"""

from enum import Enum


class AuditAction(str, Enum):
    """One state-changing clinical act, named in the glossarist's terms.

    Values are snake_case identifiers rather than prose, because an action is a
    machine-readable key used for filtering and counting, unlike an Override
    Reason which is a reportable clinical dimension rendered to a human.
    """

    register_patient = "register_patient"
    open_encounter = "open_encounter"
    correct_intake = "correct_intake"
    override = "override"
    reassessment = "reassessment"
    departure = "departure"


AUDIT_ACTIONS: tuple[AuditAction, ...] = tuple(AuditAction)
