"""An independent, citable ESI v4 ground-truth rubric.

This module translates published Emergency Severity Index (ESI) version 4
criteria into a deterministic three-level Urgency Level. It is authored from
the AHRQ ESI v4 implementation handbook (see ``PUBLISHED_SOURCE`` and
``RUBRIC.md``) and deliberately knows nothing about the Prioritization Engine's
rules or feature representation.

The public entry point is :func:`label`, which maps one :class:`Presentation`
to exactly one :class:`GroundTruthLabel`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from enum import Enum

RUBRIC_VERSION = "esi-v4-rubric-v1.0.0"


class UrgencyLevel(str, Enum):
    """The three-level clinical output category defined in CONTEXT.md."""

    high = "High"
    medium = "Medium"
    low = "Low"


class EsiLevel(int, Enum):
    """The published five-level ESI categories, used only as ground truth."""

    one = 1
    two = 2
    three = 3
    four = 4
    five = 5


ESI_TO_URGENCY: dict[EsiLevel, UrgencyLevel] = {
    EsiLevel.one: UrgencyLevel.high,
    EsiLevel.two: UrgencyLevel.high,
    EsiLevel.three: UrgencyLevel.medium,
    EsiLevel.four: UrgencyLevel.low,
    EsiLevel.five: UrgencyLevel.low,
}


class MentalStatus(str, Enum):
    """The AVPU scale used by the ESI algorithm (handbook Table 2-2)."""

    alert = "A"
    verbal = "V"
    pain = "P"
    unresponsive = "U"


class HighRiskFlag(str, Enum):
    """High-risk presentations named as ESI level-2 examples in the handbook."""

    suspected_acute_coronary_syndrome = "suspected_acute_coronary_syndrome"
    signs_of_stroke = "signs_of_stroke"
    suspected_subarachnoid_haemorrhage = "suspected_subarachnoid_haemorrhage"
    suspected_pneumothorax = "suspected_pneumothorax"
    suspected_ectopic_pregnancy = "suspected_ectopic_pregnancy"
    immunocompromised_with_fever = "immunocompromised_with_fever"
    suicidal_or_homicidal_ideation = "suicidal_or_homicidal_ideation"
    major_trauma_mechanism = "major_trauma_mechanism"


class EsiResource(str, Enum):
    """Expected resource types counted by ESI decision point C.

    The vocabulary follows handbook Table 2-3. ``complex_procedure`` counts as
    two resource types; every other member counts as one.
    """

    labs = "labs"
    ecg = "ecg"
    x_ray = "x_ray"
    ct = "ct"
    mri = "mri"
    ultrasound = "ultrasound"
    angiography = "angiography"
    iv_fluids = "iv_fluids"
    iv_medications = "iv_medications"
    im_medications = "im_medications"
    nebulized_medications = "nebulized_medications"
    specialty_consultation = "specialty_consultation"
    simple_procedure = "simple_procedure"
    complex_procedure = "complex_procedure"


@dataclass(frozen=True)
class PublishedSource:
    authors: str
    title: str
    edition: str
    publication: str
    publisher: str
    year: str
    locator: str


PUBLISHED_SOURCE = PublishedSource(
    authors="Gilboy N, Tanabe P, Travers D, Rosenau AM",
    title=(
        "Emergency Severity Index (ESI): A Triage Tool for Emergency Department "
        "Care, Version 4"
    ),
    edition="Implementation Handbook, 2012 Edition",
    publication="AHRQ Publication No. 12-0014",
    publisher="Agency for Healthcare Research and Quality, Rockville, MD",
    year="November 2011",
    locator="https://esitriage.org/handbook.asp",
)

CITATION = (
    f"{PUBLISHED_SOURCE.authors}. {PUBLISHED_SOURCE.title}. "
    f"{PUBLISHED_SOURCE.edition}. {PUBLISHED_SOURCE.publication}. "
    f"{PUBLISHED_SOURCE.publisher}; {PUBLISHED_SOURCE.year}."
)


@dataclass(frozen=True)
class Presentation:
    """A described presentation, broader than the engine's feature vector.

    The first nine fields mirror the intake the Prioritization Engine can see.
    The remaining fields are deliberately additional clinical information the
    rubric uses: onset, respiratory rate, mental status, associated symptoms,
    mechanism of injury, past history, high-risk flags and expected resources.
    """

    age_years: float
    sex: str
    presenting_complaint: str
    onset: str
    illness_duration_hours: float
    pain_level: int
    pain_requires_intervention_beyond_triage: bool
    temperature_c: float
    heart_rate_bpm: int
    respiratory_rate_bpm: int
    systolic_bp: int
    diastolic_bp: int
    oxygen_saturation_percent: int
    mental_status: MentalStatus
    new_onset_altered_mental_status: bool
    associated_symptoms: frozenset[str]
    mechanism_of_injury: str | None
    medical_history: frozenset[str]
    high_risk_flags: frozenset[HighRiskFlag]
    severe_distress: bool
    life_saving_intervention_required: bool
    severe_respiratory_distress: bool
    expected_resources: tuple[EsiResource, ...]

    def __post_init__(self) -> None:
        _check_range("age_years", self.age_years, 0, 120)
        if not isinstance(self.sex, str) or not self.sex.strip():
            raise ValueError("sex must be a non-empty string")
        if not isinstance(self.presenting_complaint, str) or not self.presenting_complaint.strip():
            raise ValueError("presenting_complaint must be a non-empty string")
        if self.onset not in {"sudden", "gradual", "unknown"}:
            raise ValueError("onset must be 'sudden', 'gradual' or 'unknown'")
        _check_range("illness_duration_hours", self.illness_duration_hours, 0, 8760)
        _check_int_range("pain_level", self.pain_level, 0, 10)
        _check_bool(
            "pain_requires_intervention_beyond_triage",
            self.pain_requires_intervention_beyond_triage,
        )
        _check_range("temperature_c", self.temperature_c, 30, 45)
        _check_int_range("heart_rate_bpm", self.heart_rate_bpm, 20, 300)
        _check_int_range("respiratory_rate_bpm", self.respiratory_rate_bpm, 0, 80)
        _check_int_range("systolic_bp", self.systolic_bp, 50, 300)
        _check_int_range("diastolic_bp", self.diastolic_bp, 20, 200)
        if self.systolic_bp <= self.diastolic_bp:
            raise ValueError("systolic_bp must be greater than diastolic_bp")
        _check_int_range(
            "oxygen_saturation_percent", self.oxygen_saturation_percent, 50, 100
        )
        if not isinstance(self.mental_status, MentalStatus):
            raise ValueError("mental_status must be a MentalStatus value")
        _check_bool(
            "new_onset_altered_mental_status", self.new_onset_altered_mental_status
        )
        _check_frozenset("associated_symptoms", self.associated_symptoms)
        if self.mechanism_of_injury is not None and (
            not isinstance(self.mechanism_of_injury, str)
            or not self.mechanism_of_injury.strip()
        ):
            raise ValueError("mechanism_of_injury must be a non-empty string or None")
        _check_frozenset("medical_history", self.medical_history)
        _check_frozenset("high_risk_flags", self.high_risk_flags)
        if not all(isinstance(flag, HighRiskFlag) for flag in self.high_risk_flags):
            raise ValueError("high_risk_flags must contain HighRiskFlag values")
        _check_bool("severe_distress", self.severe_distress)
        _check_bool(
            "life_saving_intervention_required",
            self.life_saving_intervention_required,
        )
        _check_bool("severe_respiratory_distress", self.severe_respiratory_distress)
        if not isinstance(self.expected_resources, tuple):
            raise ValueError("expected_resources must be a tuple")
        if not all(isinstance(resource, EsiResource) for resource in self.expected_resources):
            raise ValueError("expected_resources must contain EsiResource values")
        if len(set(self.expected_resources)) != len(self.expected_resources):
            raise ValueError("expected_resources must not repeat a resource type")


@dataclass(frozen=True)
class RubricRule:
    rule_id: str
    esi_level: EsiLevel
    description: str
    citation: str
    applies: Callable[[Presentation], bool]


@dataclass(frozen=True)
class GroundTruthLabel:
    urgency_level: UrgencyLevel
    esi_level: EsiLevel
    rubric_version: str
    matched_rule: str
    citation: str


RUBRIC_INPUT_FIELDS = frozenset(field.name for field in fields(Presentation))


def resource_units(resources: tuple[EsiResource, ...]) -> int:
    """Count ESI resource types, with a complex procedure counting as two."""
    return sum(
        2 if resource is EsiResource.complex_procedure else 1
        for resource in resources
    )


def danger_zone_exceeded(presentation: Presentation) -> bool:
    """True when an age-specific danger-zone vital sign is exceeded.

    Thresholds are transcribed from handbook Figure 5-1 (p. 35). The figure
    states the bands as under 3 months, 3 months to 3 years, 3 to 8 years, and
    over 8 years; the boundary at exactly 8 years is treated as the adult band.
    """
    age = presentation.age_years
    if age < 0.25:
        return (
            presentation.heart_rate_bpm > 180
            or presentation.respiratory_rate_bpm > 50
        )
    if age < 3:
        return (
            presentation.heart_rate_bpm > 160
            or presentation.respiratory_rate_bpm > 40
        )
    if age < 8:
        return (
            presentation.heart_rate_bpm > 140
            or presentation.respiratory_rate_bpm > 30
        )
    return (
        presentation.heart_rate_bpm > 100
        or presentation.respiratory_rate_bpm > 20
        or presentation.oxygen_saturation_percent < 92
    )


def _immediate_life_saving(presentation: Presentation) -> bool:
    return presentation.life_saving_intervention_required


def _severe_respiratory_distress(presentation: Presentation) -> bool:
    return presentation.severe_respiratory_distress


def _hypoxaemia(presentation: Presentation) -> bool:
    return presentation.oxygen_saturation_percent < 90


def _unresponsive(presentation: Presentation) -> bool:
    return presentation.mental_status in {
        MentalStatus.pain,
        MentalStatus.unresponsive,
    }


def _high_risk(presentation: Presentation) -> bool:
    return bool(presentation.high_risk_flags)


def _new_onset_altered_mental_status(presentation: Presentation) -> bool:
    return presentation.new_onset_altered_mental_status


def _severe_pain(presentation: Presentation) -> bool:
    return (
        presentation.pain_level >= 7
        and presentation.pain_requires_intervention_beyond_triage
    )


def _severe_distress(presentation: Presentation) -> bool:
    return presentation.severe_distress


def _two_or_more_resources(presentation: Presentation) -> bool:
    return resource_units(presentation.expected_resources) >= 2


def _one_resource(presentation: Presentation) -> bool:
    return resource_units(presentation.expected_resources) == 1


def _no_resources(presentation: Presentation) -> bool:
    return resource_units(presentation.expected_resources) == 0


RULES: tuple[RubricRule, ...] = (
    RubricRule(
        rule_id="esi_1_immediate_life_saving_intervention",
        esi_level=EsiLevel.one,
        description=(
            "Immediate life-saving intervention is required (airway, breathing, "
            "circulation or a major change in level of consciousness)."
        ),
        citation=f"{CITATION} Chapter 2, p. 8 and Figure 2-1a; Table 2-1, p. 10.",
        applies=_immediate_life_saving,
    ),
    RubricRule(
        rule_id="esi_1_severe_respiratory_distress",
        esi_level=EsiLevel.one,
        description="The patient is in severe respiratory distress.",
        citation=f"{CITATION} Chapter 2, p. 8 and Figure 2-1a.",
        applies=_severe_respiratory_distress,
    ),
    RubricRule(
        rule_id="esi_1_hypoxaemia",
        esi_level=EsiLevel.one,
        description="Oxygen saturation is below 90 percent.",
        citation=f"{CITATION} Chapter 2, p. 8 and Figure 2-1a; p. 10.",
        applies=_hypoxaemia,
    ),
    RubricRule(
        rule_id="esi_1_unresponsive",
        esi_level=EsiLevel.one,
        description="The patient responds only to pain or is unresponsive (AVPU P or U).",
        citation=f"{CITATION} Chapter 2, p. 10 and Table 2-2.",
        applies=_unresponsive,
    ),
    RubricRule(
        rule_id="esi_2_high_risk_situation",
        esi_level=EsiLevel.two,
        description=(
            "The presentation is a high-risk situation that could deteriorate or "
            "needs time-sensitive treatment (for example suspected acute coronary "
            "syndrome, stroke, ectopic pregnancy, neutropenic fever, major trauma "
            "mechanism, or suicidal ideation)."
        ),
        citation=(
            f"{CITATION} Chapter 2, pp. 11-12; Chapter 3, Table 3-1, pp. 23-27."
        ),
        applies=_high_risk,
    ),
    RubricRule(
        rule_id="esi_2_new_onset_altered_mental_status",
        esi_level=EsiLevel.two,
        description="New onset confusion, lethargy or disorientation.",
        citation=f"{CITATION} Chapter 2, pp. 11-12; Chapter 3, p. 26.",
        applies=_new_onset_altered_mental_status,
    ),
    RubricRule(
        rule_id="esi_2_severe_pain",
        esi_level=EsiLevel.two,
        description=(
            "Pain is rated 7/10 or more and needs intervention beyond what triage "
            "can provide."
        ),
        citation=f"{CITATION} Chapter 2, p. 12; Chapter 3, p. 26.",
        applies=_severe_pain,
    ),
    RubricRule(
        rule_id="esi_2_severe_distress",
        esi_level=EsiLevel.two,
        description="The patient is in severe physiological or psychological distress.",
        citation=f"{CITATION} Chapter 2, p. 13; Chapter 3, p. 27.",
        applies=_severe_distress,
    ),
    RubricRule(
        rule_id="esi_2_danger_zone_vitals",
        esi_level=EsiLevel.two,
        description=(
            "An age-specific danger-zone vital sign is exceeded (heart rate, "
            "respiratory rate, or oxygen saturation)."
        ),
        citation=f"{CITATION} Chapter 5, Figure 5-1, p. 35.",
        applies=danger_zone_exceeded,
    ),
    RubricRule(
        rule_id="esi_3_two_or_more_resources",
        esi_level=EsiLevel.three,
        description="Two or more ESI resource types are expected.",
        citation=(
            f"{CITATION} Chapter 2, pp. 13-14 and Tables 2-3 and 2-4; Chapter 4."
        ),
        applies=_two_or_more_resources,
    ),
    RubricRule(
        rule_id="esi_4_one_resource",
        esi_level=EsiLevel.four,
        description="Exactly one ESI resource type is expected.",
        citation=f"{CITATION} Chapter 2, p. 14 and Tables 2-3 and 2-4; Chapter 4.",
        applies=_one_resource,
    ),
    RubricRule(
        rule_id="esi_5_no_resources",
        esi_level=EsiLevel.five,
        description="No ESI resource types are expected.",
        citation=f"{CITATION} Chapter 2, p. 14 and Tables 2-3 and 2-4; Chapter 4.",
        applies=_no_resources,
    ),
)


def label(presentation: Presentation) -> GroundTruthLabel:
    """Apply the written rubric and return exactly one ground-truth label."""
    for rule in RULES:
        if rule.applies(presentation):
            return GroundTruthLabel(
                urgency_level=ESI_TO_URGENCY[rule.esi_level],
                esi_level=rule.esi_level,
                rubric_version=RUBRIC_VERSION,
                matched_rule=rule.rule_id,
                citation=rule.citation,
            )
    raise AssertionError("the rubric is incomplete: no rule matched")


def _check_range(name: str, value: float, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def _check_int_range(name: str, value: int, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def _check_bool(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _check_frozenset(name: str, value: frozenset[object]) -> None:
    if not isinstance(value, frozenset):
        raise ValueError(f"{name} must be a frozenset")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{name} must contain non-empty strings")
