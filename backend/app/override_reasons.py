"""The fixed Override Reason set, verbatim from `CONTEXT.md`.

One source of truth for the reasons: the API exposes this tuple to the client,
the Override request validates against it, and the data layer constrains the
stored column to the same values. Adding a reason is a glossary change first.

Free text is permitted only for ``other``; see :func:`allows_free_text`.
"""

from enum import Enum


class OverrideReason(str, Enum):
    """The stated justification for an Override.

    Values are the glossary wording exactly, because the reason is a
    reportable dimension rather than free commentary.
    """

    vitals_inconsistent = "vitals inconsistent with recommendation"
    symptom_not_captured = "symptom not captured"
    clinical_gestalt = "clinical gestalt"
    patient_deteriorating = "patient deteriorating"
    duplicate_entry = "duplicate entry"
    other = "other"


OVERRIDE_REASONS: tuple[OverrideReason, ...] = tuple(OverrideReason)


def allows_free_text(reason: OverrideReason) -> bool:
    return reason is OverrideReason.other
