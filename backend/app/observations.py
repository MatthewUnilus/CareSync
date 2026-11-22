"""The Observation chart: its reference ranges, and how a set is staged.

Vital signs live in one place. Every set is an Observation attached to an
Encounter or an Admission, never both and never neither (ADR 0008), and it is
append-only once written: charting is a new row, never an edit.

Reference ranges
----------------
A reading outside its adult resting reference interval is marked for display and
nothing more (ADR 0010): the value is never altered, nothing is scored, nothing
is reordered and no alert is raised. The intervals are the ordinary adult resting
ranges, not the ESI danger-zone thresholds the removed red-flag layer carried:
those mark a patient who is already in danger, which is not the same thing as
the band an ordinary resting reading sits in. The facts are taken from the
National Library of Medicine, not their prose:

    MedlinePlus (NLM). "Vital signs."
    https://medlineplus.gov/ency/article/002341.htm
    Adult resting: blood pressure 90/60 to 120/80 mmHg, breathing 12 to 18 per
    minute, pulse 60 to 100 per minute, temperature 36.5 to 37.3 C.

    MedlinePlus (NLM). "Pulse Oximetry."
    https://medlineplus.gov/lab-tests/pulse-oximetry/
    A normal oxygen saturation level is 95 to 100 percent.

The same Vital signs page notes that normal vital signs change with age. An
Observation carries no age of its own, but its Patient does, and the adult
intervals are **not** applied to a patient under 18: ``reference_range_applies``
is false and ``abnormal_fields`` is empty, so a child is never marked against a
range that was never a child's normal. The response also carries a note for the
interface to show in place of the marks.

The comparison is always against the adult intervals only and never produces a
score, a level or an alert. A value inside its interval is not marked; one
outside it is, and nothing else changes.

What is marked
--------------
Only the readings with an adult resting interval are marked, and the interval is
inclusive at both ends: a value on the boundary is normal, and the mark begins
one step outside. Pain level and illness duration have no generic normal
interval, so they are never marked rather than given a threshold of their own
invention.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Observation
from app.schemas import ObservationPayload

#: Age at which the adult resting intervals begin to apply, in whole years.
ADULT_MINIMUM_AGE = 18

#: Shown by the interface in place of marks when the adult ranges do not apply.
REFERENCE_RANGE_NOTE = (
    "Adult resting reference ranges do not apply to a patient under 18; no "
    "readings are marked."
)


@dataclass(frozen=True)
class ReadingRange:
    """One reading, its adult resting interval, and where the interval comes from.

    ``field`` is the name the response marks, matching the intake field name
    (``blood_pressure`` names the pair). ``is_abnormal`` compares a value against
    the interval for display only: it decides a mark on the chart and touches
    nothing.
    """

    field: str
    normal: str
    citation: str
    is_abnormal: Callable[[Observation], bool]


_MEDLINEPLUS = (
    "MedlinePlus (NLM), 'Vital signs', "
    "https://medlineplus.gov/ency/article/002341.htm (adult resting range)"
)

#: The adult resting reference intervals, in the order the readings are charted.
#: A reading outside its interval is named in ``ObservationResponse.abnormal_fields``.
ADULT_REFERENCE_RANGES: tuple[ReadingRange, ...] = (
    ReadingRange(
        field="temperature_c",
        normal="36.5-37.3 C",
        citation=_MEDLINEPLUS,
        is_abnormal=lambda observation: (
            observation.temperature_c < 36.5 or observation.temperature_c > 37.3
        ),
    ),
    ReadingRange(
        field="heart_rate_bpm",
        normal="60-100 bpm",
        citation=_MEDLINEPLUS,
        is_abnormal=lambda observation: (
            observation.heart_rate_bpm < 60 or observation.heart_rate_bpm > 100
        ),
    ),
    ReadingRange(
        field="respiratory_rate_bpm",
        normal="12-18 per minute",
        citation=_MEDLINEPLUS,
        is_abnormal=lambda observation: (
            observation.respiratory_rate_bpm < 12
            or observation.respiratory_rate_bpm > 18
        ),
    ),
    ReadingRange(
        field="blood_pressure",
        normal="systolic 90-120 and diastolic 60-80 mmHg",
        citation=_MEDLINEPLUS,
        is_abnormal=lambda observation: (
            observation.systolic < 90
            or observation.systolic > 120
            or observation.diastolic < 60
            or observation.diastolic > 80
        ),
    ),
    ReadingRange(
        field="oxygen_saturation_percent",
        normal="95-100 percent",
        citation=(
            "MedlinePlus (NLM), 'Pulse Oximetry', "
            "https://medlineplus.gov/lab-tests/pulse-oximetry/ (normal oxygen "
            "saturation 95-100 percent)"
        ),
        is_abnormal=lambda observation: (
            observation.oxygen_saturation_percent < 95
            or observation.oxygen_saturation_percent > 100
        ),
    ),
)


def reference_range_applies(observation: Observation) -> bool:
    """Whether the adult resting intervals apply to this Observation's Patient.

    False for a patient under 18: the adult intervals are not a child's normal,
    so the chart marks nothing rather than marking a child against them.
    """
    return observation.patient.age >= ADULT_MINIMUM_AGE


def abnormal_fields(observation: Observation) -> list[str]:
    """Name each reading outside its adult resting interval, for display marking.

    A comparison, not a judgement (ADR 0010): the caller shows the marks and
    changes nothing. A patient under 18 yields no marks at all, because the adult
    intervals do not apply to them. The names come from
    ``ADULT_REFERENCE_RANGES``, so a mark and the field it names cannot drift.
    """
    if not reference_range_applies(observation):
        return []
    return [
        reading.field
        for reading in ADULT_REFERENCE_RANGES
        if reading.is_abnormal(observation)
    ]


def stage_observation(
    session: Session,
    *,
    actor,
    payload: ObservationPayload,
    patient,
    encounter=None,
    admission=None,
) -> Observation:
    """Build one Observation from a charted set and add it, without committing.

    Exactly one of ``encounter`` and ``admission`` is supplied by the caller;
    the data layer refuses anything else (``ck_observations_exactly_one_subject``).
    The caller commits, so the Observation, its subject and the audit entry land
    in one transaction.
    """
    observation = Observation(
        actor=actor,
        patient=patient,
        encounter=encounter,
        admission=admission,
        pain_level=payload.pain_level,
        illness_duration_hours=payload.illness_duration_hours,
        temperature_c=payload.temperature_c,
        heart_rate_bpm=payload.heart_rate_bpm,
        respiratory_rate_bpm=payload.respiratory_rate_bpm,
        systolic=payload.blood_pressure.systolic,
        diastolic=payload.blood_pressure.diastolic,
        oxygen_saturation_percent=payload.oxygen_saturation_percent,
        notes=payload.notes,
    )
    session.add(observation)
    return observation


def previous_observation(
    session: Session, observation: Observation
) -> Observation | None:
    """The Observation taken before ``observation`` for the same Patient, or None.

    "Before" is by the instant it was taken, breaking a tie on the row id being
    lower than this row's, so the chart's direction of travel is the order the
    readings were taken and two sets taken at the same instant still read in a
    stable order.
    """
    return session.scalar(
        select(Observation)
        .where(
            Observation.patient_id == observation.patient_id,
            or_(
                Observation.taken_at < observation.taken_at,
                and_(
                    Observation.taken_at == observation.taken_at,
                    Observation.id < observation.id,
                ),
            ),
        )
        .order_by(Observation.taken_at.desc(), Observation.id.desc())
        .limit(1)
    )
