"""The structured feature vector the classifier consumes.

One definition, used by both the Training step and Seam B, so a model can never
be trained on a different vector from the one it is asked to score. The vector
is built only from recognised Symptom Groups, pain level, illness duration, age
and the four vitals; the free-text complaint never enters it.

Dimensions, in order:

- one multi-hot dimension per Symptom Group in the vocabulary's authored order
- ``pain_level``, ``illness_duration_hours``, ``age``
- ``temperature_c``, ``heart_rate_bpm``, ``systolic_bp``, ``diastolic_bp``,
  ``oxygen_saturation_percent``

The vector is a plain tuple of floats. It has no notion of a database, a session
or a data source, which is what lets the same function serve the engine and the
training pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from app.symptom_groups import vocabulary

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from app.prioritisation import PrioritisationInputs

# A source that does not record a value must not silently look like a real one.
# Both sentinels sit outside the domain intake can produce, so a model trained
# on them can still learn from the value where it *is* recorded.
MISSING_PAIN_LEVEL = -1.0
MISSING_ILLNESS_DURATION_HOURS = -1.0

SCALAR_FEATURE_NAMES: tuple[str, ...] = (
    "pain_level",
    "illness_duration_hours",
    "age",
    "temperature_c",
    "heart_rate_bpm",
    "systolic_bp",
    "diastolic_bp",
    "oxygen_saturation_percent",
)


@dataclass(frozen=True)
class FeatureInputs:
    """The structured inputs, independent of where an Encounter came from."""

    recognised_symptom_groups: tuple[str, ...]
    pain_level: float
    illness_duration_hours: float
    age: float
    temperature_c: float
    heart_rate_bpm: float
    systolic_bp: float
    diastolic_bp: float
    oxygen_saturation_percent: float

    def vector(self) -> tuple[float, ...]:
        """Return the feature vector, in :data:`FEATURE_NAMES` order."""
        present = set(self.recognised_symptom_groups)
        groups = tuple(
            1.0 if group in present else 0.0 for group in vocabulary().groups
        )
        scalars = tuple(
            float(getattr(self, name)) for name in SCALAR_FEATURE_NAMES
        )
        return groups + scalars


@lru_cache(maxsize=1)
def feature_names() -> tuple[str, ...]:
    """The names of the vector's dimensions, in order.

    Cached because the vocabulary file is loaded once per process; the names are
    recorded in the artefact and checked when a model is loaded.
    """
    return tuple(
        f"symptom_group:{group}" for group in vocabulary().groups
    ) + SCALAR_FEATURE_NAMES


#: Set at import time for callers that want the names without calling a function.
FEATURE_NAMES: tuple[str, ...] = feature_names()


def build_feature_vector(inputs: "PrioritisationInputs") -> tuple[float, ...]:
    """Build the vector from the inputs a Triage Assessment captured."""
    return FeatureInputs(
        recognised_symptom_groups=inputs.recognised_symptom_groups,
        pain_level=inputs.pain_level,
        illness_duration_hours=inputs.illness_duration_hours,
        age=inputs.age,
        temperature_c=inputs.temperature_c,
        heart_rate_bpm=inputs.heart_rate_bpm,
        systolic_bp=inputs.systolic_bp,
        diastolic_bp=inputs.diastolic_bp,
        oxygen_saturation_percent=inputs.oxygen_saturation_percent,
    ).vector()


__all__ = [
    "FEATURE_NAMES",
    "MISSING_ILLNESS_DURATION_HOURS",
    "MISSING_PAIN_LEVEL",
    "SCALAR_FEATURE_NAMES",
    "FeatureInputs",
    "build_feature_vector",
    "feature_names",
]
