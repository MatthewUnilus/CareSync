"""Apply the written ground-truth rubric to a described presentation."""

from __future__ import annotations

from evaluation.rubric import (
    GroundTruthLabel,
    Presentation,
    UrgencyLevel,
    label as apply_rubric,
)


def label(presentation: Presentation) -> GroundTruthLabel:
    """Return the one Urgency Level the written rubric assigns."""
    return apply_rubric(presentation)


def urgency_level(presentation: Presentation) -> UrgencyLevel:
    """Return only the Urgency Level for a presentation."""
    return label(presentation).urgency_level
