"""Seam B — the Prioritization Engine.

The engine is a pure function: given the inputs captured for a Triage
Assessment it returns exactly one Urgency Level. It takes no session, touches no
database, and is called directly from unit tests with constructed inputs.

The engine is layered (``spec.md``, "Prioritization Engine composition"):
(1) a trained supervised classifier over a structured feature vector; (2) a
deterministic red-flag safety layer that can raise — never lower — the output
(ticket 07); (3) a cached fallback for complaints matching no Symptom Group
(ticket 08). This ticket replaces the earlier stub with layer (1) alone, so the
Queue, the Assessment record and the board now see a recommendation produced by
the model behind an unchanged boundary.

The classifier is a multinomial logistic regression trained on published,
openly downloadable triage data (see ``evaluation/datasets/provenance.json``
for the exact sources and licences, and ``models/`` for the artefact and its
cross-validated scores). It consumes the vector built by
:func:`app.features.build_feature_vector` — recognised Symptom Groups, pain
level, illness duration, age and the four vitals. The free-text complaint is
never a feature.

The model is loaded once per process and cached, so the first call reads a small
JSON file and later calls do no I/O. Inference is a few microseconds, well
inside the three-second budget. Same inputs, same output, always.
"""

from dataclasses import dataclass
from enum import Enum

from app.features import build_feature_vector


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
    recognised_symptom_groups: tuple[str, ...] = ()


def recommend(inputs: PrioritisationInputs) -> UrgencyLevel:
    """Return the Machine Recommendation for these captured inputs."""
    # Imported here so the classifier module may import UrgencyLevel from this
    # one without a circular import at module load.
    from app.classifier import load_default_model

    return load_default_model().predict(build_feature_vector(inputs))
