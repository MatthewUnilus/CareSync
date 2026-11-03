"""Seam B — the Prioritization Engine.

The engine is a pure function: given the inputs captured for a Triage
Assessment it returns exactly one Urgency Level. It takes no session, touches no
database, and is called directly from unit tests with constructed inputs.

The real engine is layered (classifier, red-flag safety layer, cached fallback)
and is built by later tickets. This ticket ships a **deliberately simple
deterministic stub** so that the Queue, the Assessment record and the board can
be built and tested against a stable boundary. The stub is replaced by the
trained classifier in ticket 06; tickets 05, 07 and 08 add recognition, the
safety layer and the fallback behind the same boundary.

The stub rule, in one paragraph: **High** if any single severe observation is
present — oxygen saturation below 92%, heart rate outside 50–120, systolic
pressure outside 90–179, temperature outside 35.0–38.9 °C, or pain 8 or more;
otherwise **Medium** if any moderate observation is present — oxygen saturation
below 95%, heart rate above 100, systolic pressure below 100 or 160 and above,
temperature 38.0 °C or above or below 36.0 °C, or pain 5 or more; otherwise
**Low**. It ignores the complaint text, age, illness duration and recognised
Symptom Groups; that is deliberate, and it is why the answer is easy to explain
but clinically shallow. It has no I/O, so the three-second budget is trivially
met; a later implementation may do work inside the same signature without the
callers changing.

`PrioritisationInputs.recognised_symptom_groups` is part of the captured inputs
so ticket 05 can fill it without changing the boundary. The stub ignores it.
"""

from dataclasses import dataclass
from enum import Enum


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

    The free-text complaint and the Patient's age are captured because a later
    engine uses them, even though the current stub does not.
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


# Stub thresholds. Ticket 06 replaces this function; keep the names local so it
# is obvious what has to disappear with the stub.
_SEVERE_OXYGEN_SATURATION = 92
_SEVERE_HEART_RATE_LOW = 50
_SEVERE_HEART_RATE_HIGH = 120
_SEVERE_SYSTOLIC_LOW = 90
_SEVERE_SYSTOLIC_HIGH = 180
_SEVERE_TEMPERATURE_LOW = 35.0
_SEVERE_TEMPERATURE_HIGH = 38.9
_SEVERE_PAIN = 8

_MODERATE_OXYGEN_SATURATION = 95
_MODERATE_HEART_RATE_HIGH = 100
_MODERATE_SYSTOLIC_LOW = 100
_MODERATE_SYSTOLIC_HIGH = 160
_MODERATE_TEMPERATURE_LOW = 36.0
_MODERATE_TEMPERATURE_HIGH = 38.0
_MODERATE_PAIN = 5


def recommend(inputs: PrioritisationInputs) -> UrgencyLevel:
    """Return the Machine Recommendation for these captured inputs.

    **Stub — replaced by the trained classifier in ticket 06.** See the module
    docstring for the rule in full.
    """
    if (
        inputs.oxygen_saturation_percent < _SEVERE_OXYGEN_SATURATION
        or inputs.heart_rate_bpm < _SEVERE_HEART_RATE_LOW
        or inputs.heart_rate_bpm > _SEVERE_HEART_RATE_HIGH
        or inputs.systolic_bp < _SEVERE_SYSTOLIC_LOW
        or inputs.systolic_bp >= _SEVERE_SYSTOLIC_HIGH
        or inputs.temperature_c < _SEVERE_TEMPERATURE_LOW
        or inputs.temperature_c > _SEVERE_TEMPERATURE_HIGH
        or inputs.pain_level >= _SEVERE_PAIN
    ):
        return UrgencyLevel.high

    if (
        inputs.oxygen_saturation_percent < _MODERATE_OXYGEN_SATURATION
        or inputs.heart_rate_bpm > _MODERATE_HEART_RATE_HIGH
        or inputs.systolic_bp < _MODERATE_SYSTOLIC_LOW
        or inputs.systolic_bp >= _MODERATE_SYSTOLIC_HIGH
        or inputs.temperature_c < _MODERATE_TEMPERATURE_LOW
        or inputs.temperature_c >= _MODERATE_TEMPERATURE_HIGH
        or inputs.pain_level >= _MODERATE_PAIN
    ):
        return UrgencyLevel.medium

    return UrgencyLevel.low
