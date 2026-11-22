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


# The human read of every action, in the same module as the enum so the two
# cannot drift. The key stays the machine identifier (tests and filters match on
# it, and changing it would rewrite the log's stored values); the label is what
# an Administrator reads. A label is the reportable dimension the enum docstring
# contrasts the key with, so it belongs here as a second table rather than
# replacing the values. Served with every entry by
# ``GET /api/administrator/audit-log`` (ADR 0007, amended by ticket 24).
#
# Every member of the enum must appear here: ``test_audit_log`` asserts the
# table covers the set exactly, so an action added without a label fails the
# suite rather than reaching the UI as a raw snake_case key.
AUDIT_ACTION_LABELS: dict[AuditAction, str] = {
    AuditAction.register_patient: "Patient registered",
    AuditAction.open_encounter: "Encounter opened",
    AuditAction.correct_intake: "Intake corrected",
    AuditAction.override: "Final decision overridden",
    AuditAction.reassessment: "Re-assessment recorded",
    AuditAction.departure: "Patient departed",
}

# What to show for a value the table does not name. Deliberate and readable: the
# log is read by an Administrator, so an unrecognised value says so rather than
# leaking the raw machine key. Reached only if a stored action predates a
# removed label, which the coverage test above is meant to prevent.
UNKNOWN_ACTION_LABEL = "Unknown action"


def label_for(action: AuditAction | str) -> str:
    """Return the human label for an action, falling back for an unknown value.

    Accepts the enum or its raw string value, because a row read back from the
    table carries the string. An unrecognised value returns
    ``UNKNOWN_ACTION_LABEL`` rather than the key it was given.
    """
    try:
        known = AuditAction(action)
    except ValueError:
        return UNKNOWN_ACTION_LABEL
    return AUDIT_ACTION_LABELS[known]

