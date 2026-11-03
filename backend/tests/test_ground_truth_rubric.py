"""Behaviour of the written ESI v4 ground-truth rubric.

The rubric maps one described presentation to exactly one Urgency Level. It is
authored from the AHRQ ESI v4 handbook, not from the Prioritization Engine's
rules, so these tests talk only in clinical presentation terms.
"""

from dataclasses import fields, replace

import pytest

from app.prioritisation import PrioritisationInputs
from evaluation.rubric import (
    EsiResource,
    HighRiskFlag,
    MentalStatus,
    Presentation,
    RUBRIC_INPUT_FIELDS,
    RULES,
    UrgencyLevel,
    label,
)


def make_presentation(**overrides: object) -> Presentation:
    """A stable, low-acuity adult presentation used as a test baseline."""
    baseline = Presentation(
        age_years=34,
        sex="female",
        presenting_complaint="sore throat for two days",
        onset="gradual",
        illness_duration_hours=48.0,
        pain_level=3,
        pain_requires_intervention_beyond_triage=False,
        temperature_c=37.2,
        heart_rate_bpm=78,
        respiratory_rate_bpm=16,
        systolic_bp=118,
        diastolic_bp=74,
        oxygen_saturation_percent=98,
        mental_status=MentalStatus.alert,
        new_onset_altered_mental_status=False,
        associated_symptoms=frozenset({"cough"}),
        mechanism_of_injury=None,
        medical_history=frozenset(),
        high_risk_flags=frozenset(),
        severe_distress=False,
        life_saving_intervention_required=False,
        severe_respiratory_distress=False,
        expected_resources=(EsiResource.labs,),
    )
    return replace(baseline, **overrides)


def test_labelling_is_deterministic() -> None:
    presentation = make_presentation()

    first = label(presentation)
    second = label(presentation)

    assert first == second
    assert first.urgency_level is UrgencyLevel.low
    assert first.esi_level == 4


def test_immediate_life_saving_intervention_labels_high() -> None:
    result = label(
        make_presentation(
            presenting_complaint="collapsed at home, not breathing normally",
            life_saving_intervention_required=True,
            mental_status=MentalStatus.unresponsive,
            oxygen_saturation_percent=84,
            heart_rate_bpm=132,
            respiratory_rate_bpm=30,
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 1
    assert result.matched_rule == "esi_1_immediate_life_saving_intervention"


def test_severe_respiratory_distress_labels_high() -> None:
    result = label(
        make_presentation(
            presenting_complaint="cannot speak in full sentences",
            severe_respiratory_distress=True,
            respiratory_rate_bpm=34,
            oxygen_saturation_percent=88,
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 1


def test_high_risk_condition_labels_high() -> None:
    result = label(
        make_presentation(
            presenting_complaint="crushing central chest pain radiating to left arm",
            pain_level=6,
            high_risk_flags=frozenset({HighRiskFlag.suspected_acute_coronary_syndrome}),
            expected_resources=(EsiResource.ecg, EsiResource.labs),
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 2
    assert result.matched_rule == "esi_2_high_risk_situation"


def test_new_onset_altered_mental_status_labels_high() -> None:
    result = label(
        make_presentation(
            age_years=79,
            presenting_complaint="found confused this morning",
            mental_status=MentalStatus.verbal,
            new_onset_altered_mental_status=True,
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 2


def test_severe_pain_that_cannot_wait_labels_high() -> None:
    result = label(
        make_presentation(
            presenting_complaint="severe flank pain, writhing",
            pain_level=9,
            pain_requires_intervention_beyond_triage=True,
            expected_resources=(EsiResource.labs, EsiResource.ct),
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 2


def test_severe_pain_manageable_at_triage_does_not_label_high() -> None:
    result = label(
        make_presentation(
            presenting_complaint="stubbed toe, severe pain but can weight-bear",
            pain_level=8,
            pain_requires_intervention_beyond_triage=False,
            expected_resources=(EsiResource.x_ray,),
        )
    )

    assert result.urgency_level is UrgencyLevel.low
    assert result.esi_level == 4


def test_adult_danger_zone_vital_labels_high() -> None:
    result = label(
        make_presentation(
            age_years=45,
            presenting_complaint="feels hot and shaky",
            temperature_c=38.2,
            heart_rate_bpm=118,
            respiratory_rate_bpm=18,
            oxygen_saturation_percent=97,
            expected_resources=(EsiResource.labs, EsiResource.iv_fluids),
        )
    )

    assert result.urgency_level is UrgencyLevel.high
    assert result.esi_level == 2
    assert result.matched_rule == "esi_2_danger_zone_vitals"


def test_paediatric_danger_zone_uses_higher_age_specific_threshold() -> None:
    child = label(
        make_presentation(
            age_years=5,
            presenting_complaint="cough and fever",
            heart_rate_bpm=120,
            respiratory_rate_bpm=26,
            temperature_c=38.1,
            expected_resources=(EsiResource.labs,),
        )
    )
    adult_with_same_rate = label(
        make_presentation(
            age_years=35,
            heart_rate_bpm=120,
            respiratory_rate_bpm=26,
            temperature_c=38.1,
            expected_resources=(EsiResource.labs,),
        )
    )

    # The paediatric danger-zone threshold is over 140 bpm for this age band;
    # the adult threshold is over 100 bpm.
    assert child.urgency_level is UrgencyLevel.low
    assert child.esi_level == 4
    assert adult_with_same_rate.urgency_level is UrgencyLevel.high
    assert adult_with_same_rate.esi_level == 2


def test_two_or_more_resources_labels_medium() -> None:
    result = label(
        make_presentation(
            presenting_complaint="right lower abdominal pain since this morning",
            pain_level=5,
            expected_resources=(EsiResource.labs, EsiResource.ct),
        )
    )

    assert result.urgency_level is UrgencyLevel.medium
    assert result.esi_level == 3
    assert result.matched_rule == "esi_3_two_or_more_resources"


def test_complex_procedure_counts_as_two_resources() -> None:
    result = label(
        make_presentation(
            presenting_complaint="deep laceration needing conscious sedation",
            expected_resources=(EsiResource.complex_procedure,),
        )
    )

    assert result.urgency_level is UrgencyLevel.medium
    assert result.esi_level == 3


def test_one_resource_labels_low() -> None:
    result = label(
        make_presentation(
            presenting_complaint="twisted ankle, able to walk",
            expected_resources=(EsiResource.x_ray,),
        )
    )

    assert result.urgency_level is UrgencyLevel.low
    assert result.esi_level == 4


def test_no_resources_labels_low() -> None:
    result = label(
        make_presentation(
            presenting_complaint="needs a prescription refill",
            expected_resources=(),
        )
    )

    assert result.urgency_level is UrgencyLevel.low
    assert result.esi_level == 5


def test_every_rule_cites_the_published_esi_source() -> None:
    assert RULES, "the rubric must define at least one rule"
    for rule in RULES:
        assert rule.citation.strip(), f"{rule.rule_id} is missing a citation"
        assert "ESI" in rule.citation or "Emergency Severity Index" in rule.citation


def test_rubric_inputs_are_strictly_broader_than_the_engine_feature_set() -> None:
    # The engine's captured inputs are its published feature boundary. The
    # engine receives recognised Symptom Groups rather than the raw complaint,
    # and calls age "age"; map those two names to the rubric's equivalent
    # descriptions before comparing.
    engine_features = {
        (
            "age_years"
            if name == "age"
            else "presenting_complaint"
            if name == "recognised_symptom_groups"
            else name
        )
        for name in (field.name for field in fields(PrioritisationInputs))
    }

    rubric_features = {field.name for field in fields(Presentation)}

    assert engine_features < rubric_features
    assert RUBRIC_INPUT_FIELDS == rubric_features
    assert {
        "onset",
        "respiratory_rate_bpm",
        "mental_status",
        "new_onset_altered_mental_status",
        "associated_symptoms",
        "mechanism_of_injury",
        "medical_history",
        "high_risk_flags",
        "expected_resources",
    } <= rubric_features - engine_features


def test_invalid_presentation_is_rejected_rather_than_guessed() -> None:
    with pytest.raises(ValueError):
        make_presentation(pain_level=11)

    with pytest.raises(ValueError):
        make_presentation(oxygen_saturation_percent=101)

    with pytest.raises(ValueError):
        make_presentation(mental_status="confused")  # type: ignore[arg-type]
