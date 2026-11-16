"""Seam B — the Prioritization Engine.

The engine is a pure function: given the inputs captured for a Triage
Assessment it returns exactly one Urgency Level. It takes no session, touches no
database, and is called directly from unit tests with constructed inputs.

The engine is layered (``spec.md``, "Prioritization Engine composition"):
(1) a trained supervised classifier over a structured feature vector; (2) a
deterministic red-flag safety layer that can raise — never lower — the output
(ticket 07); (3) a cached fallback for complaints matching no Symptom Group
(ticket 08, :mod:`app.fallback`). Ticket 06 replaced the stub with layer (1).
Ticket 07 added layer (2). Ticket 08 adds layer (3) behind an injected resolver:
the fallback is only reached when recognition matched nothing, its provider is
replaceable, and its result is cached by the complaint text. The Queue, the
Assessment record and the board see the composed result behind an unchanged
boundary; passing no resolver is the fallback-disabled configuration used by the
evaluation harness.

The classifier is a multinomial logistic regression trained on published,
openly downloadable triage data (see ``evaluation/datasets/provenance.json``
for the exact sources and licences, and ``models/`` for the artefact and its
cross-validated scores). It consumes the vector built by
:func:`app.features.build_feature_vector` — recognised Symptom Groups, pain
level, illness duration, age and the four vitals. The free-text complaint is
never a feature.

The model is loaded once per process and cached, so the first call reads a small
JSON file and later calls do no I/O. The safety layer is twenty deterministic
predicates over the same inputs, so it adds microseconds. Inference is far
inside the three-second budget. Same inputs, same output, always.
"""

from dataclasses import dataclass
from enum import Enum

from app.fallback import FallbackResolver
from app.features import build_feature_vector
from app.red_flags import apply_safety_layer


class UrgencyLevel(str, Enum):
    """Exactly three Urgency Levels, in the vocabulary of `CONTEXT.md`."""

    high = "High"
    medium = "Medium"
    low = "Low"


# Lower rank sorts first in the Queue. High urgency is seen before Medium, etc.
URGENCY_RANK: dict[UrgencyLevel, int] = {
    UrgencyLevel.high: 0,
    UrgencyLevel.medium: 1,
    UrgencyLevel.low: 2,
}


@dataclass(frozen=True)
class PrioritisationInputs:
    """The inputs a Triage Assessment captures, as the engine sees them.

    The free-text complaint is captured and stored with the Assessment, but it
    is not a feature: only the Symptom Groups recognised from it reach the
    classifier.
    """

    presenting_complaint: str
    age: int
    pain_level: int
    illness_duration_hours: float
    temperature_c: float
    heart_rate_bpm: int
    systolic_bp: int
    diastolic_bp: int
    oxygen_saturation_percent: int
    # Live intake always supplies this; the default exists only so a caller that
    # constructs inputs directly (tests, and any adapter that has no rate) need
    # not repeat it. Zero is inside the intake domain and fires no tachypnoea
    # rule, so an omitted value is inert rather than dangerous. Ticket 18 wires
    # the real value through the evaluation adapters; training uses the
    # :data:`app.features.MISSING_RESPIRATORY_RATE_BPM` sentinel instead.
    respiratory_rate_bpm: int = 0
    recognised_symptom_groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class Recommendation:
    """The Machine Recommendation and what the engine can say about it.

    ``fallback_used`` is true when the complaint recognised no Symptom Group and
    the fallback layer therefore decided the level. ``unclassified`` is true when
    the external provider was unavailable or timed out, so the level came from
    the safety layer's default and a Clinical user should review it. A matched
    complaint is never either.
    """

    level: UrgencyLevel
    fallback_used: bool = False
    unclassified: bool = False


def assess(
    inputs: PrioritisationInputs,
    *,
    fallback: FallbackResolver | None = None,
) -> Recommendation:
    """Return the composed Machine Recommendation for these captured inputs.

    The classifier and safety layer always run. The fallback resolver is reached
    only when recognition matched no Symptom Group *and* one was supplied.
    Passing ``None`` is the "fallback disabled" configuration used by the
    reproducible evaluation run (ticket 15); it is not the runtime default.
    """
    # Imported here so the classifier module may import UrgencyLevel from this
    # one without a circular import at module load.
    from app.classifier import load_default_model

    classifier_level = load_default_model().predict(build_feature_vector(inputs))

    if fallback is None or inputs.recognised_symptom_groups:
        return Recommendation(level=apply_safety_layer(inputs, classifier_level))

    outcome = fallback.resolve(inputs)
    return Recommendation(
        level=outcome.level,
        fallback_used=True,
        unclassified=outcome.unclassified,
    )


def recommend(
    inputs: PrioritisationInputs,
    *,
    fallback: FallbackResolver | None = None,
) -> UrgencyLevel:
    """Return the Machine Recommendation for these captured inputs.

    This is the unchanged Seam B boundary. Callers that need the fallback
    provenance (the Assessment factory, the evaluation harness) use
    :func:`assess`; everything that only orders or compares levels keeps using
    this function.
    """
    return assess(inputs, fallback=fallback).level
