"""Seam B: the red-flag safety layer is pure, deterministic, and only raises.

These tests call the engine and the layer directly with constructed inputs. A
rule's firing and its just-outside-the-threshold behaviour are both asserted, so
a threshold cannot drift silently. Every firing case is also a presentation the
classifier alone does not call High, which is what makes the layer load-bearing
rather than decoration.

The API test at the end proves that the composed result — not the classifier's
own answer — is what the Assessment stores and what the Queue orders by.
"""

import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.classifier import load_default_model
from app.features import build_feature_vector
from app.prioritisation import (
    URGENCY_RANK,
    PrioritisationInputs,
    UrgencyLevel,
    recommend,
)
from app.red_flags import RULES, apply_safety_layer, fired_rules

# Quiet vitals for a healthy young adult. Every case below changes only what
# the rule under test needs, so the classifier's own answer stays Low.
BASE = PrioritisationInputs(
    presenting_complaint="Mild headache",
    age=24,
    pain_level=2,
    illness_duration_hours=24.0,
    temperature_c=36.6,
    heart_rate_bpm=70,
    systolic_bp=116,
    diastolic_bp=72,
    oxygen_saturation_percent=99,
)

ALL_LEVELS = (UrgencyLevel.high, UrgencyLevel.medium, UrgencyLevel.low)


def inputs(**overrides: object) -> PrioritisationInputs:
    return replace(BASE, **overrides)


def classifier_only(case: PrioritisationInputs) -> UrgencyLevel:
    """The answer layer (1) gives, before the safety layer sees it."""
    return load_default_model().predict(build_feature_vector(case))


def fired_ids(case: PrioritisationInputs) -> set[str]:
    return {rule.id for rule in fired_rules(case)}


# One presentation per documented rule. Ages are chosen so the age bands do not
# overlap the rule being exercised.
FIRING_CASES: dict[str, PrioritisationInputs] = {
    "oxygen_saturation_below_90": inputs(
        age=7, oxygen_saturation_percent=89
    ),
    "adult_hypoxaemia": inputs(age=40, oxygen_saturation_percent=91),
    "infant_tachycardia": inputs(age=1, heart_rate_bpm=165),
    "child_tachycardia": inputs(age=5, heart_rate_bpm=145),
    "adult_tachycardia": inputs(age=40, heart_rate_bpm=101),
    "infant_fever": inputs(age=0, temperature_c=38.1),
    "adult_hypotension": inputs(age=40, systolic_bp=89, diastolic_bp=60),
    "adult_severe_hypertension": inputs(
        age=40, systolic_bp=215, diastolic_bp=100
    ),
    "chest_pain": inputs(recognised_symptom_groups=("chest pain",)),
    "stroke_signs": inputs(recognised_symptom_groups=("slurred speech",)),
    "altered_mental_status": inputs(recognised_symptom_groups=("confusion",)),
    "seizure": inputs(recognised_symptom_groups=("seizure",)),
    "suicidal_or_self_harm": inputs(
        recognised_symptom_groups=("suicidal thoughts",)
    ),
    "major_haemorrhage": inputs(recognised_symptom_groups=("vomiting blood",)),
    "anaphylaxis": inputs(recognised_symptom_groups=("anaphylaxis",)),
    "overdose": inputs(recognised_symptom_groups=("overdose",)),
    "head_injury": inputs(recognised_symptom_groups=("head injury",)),
    "neck_stiffness": inputs(recognised_symptom_groups=("neck stiffness",)),
    "vaginal_bleeding": inputs(recognised_symptom_groups=("vaginal bleeding",)),
    "syncope": inputs(recognised_symptom_groups=("fainting",)),
}

# The same rule one step outside its threshold, with everything else quiet.
BOUNDARY_CASES: dict[str, PrioritisationInputs] = {
    "oxygen_saturation_below_90": inputs(
        age=7, oxygen_saturation_percent=90
    ),
    "adult_hypoxaemia": inputs(age=40, oxygen_saturation_percent=92),
    "infant_tachycardia": inputs(age=1, heart_rate_bpm=160),
    "child_tachycardia": inputs(age=5, heart_rate_bpm=140),
    "adult_tachycardia": inputs(age=40, heart_rate_bpm=100),
    "infant_fever": inputs(age=0, temperature_c=38.0),
    "adult_hypotension": inputs(age=40, systolic_bp=90, diastolic_bp=61),
    "adult_severe_hypertension": inputs(
        age=40, systolic_bp=209, diastolic_bp=119
    ),
    "chest_pain": inputs(recognised_symptom_groups=("back pain",)),
    "stroke_signs": inputs(recognised_symptom_groups=("headache",)),
    "altered_mental_status": inputs(recognised_symptom_groups=("dizziness",)),
    "seizure": inputs(recognised_symptom_groups=("headache",)),
    "suicidal_or_self_harm": inputs(recognised_symptom_groups=("anxiety",)),
    "major_haemorrhage": inputs(recognised_symptom_groups=("vomiting",)),
    "anaphylaxis": inputs(recognised_symptom_groups=("allergic reaction",)),
    "overdose": inputs(recognised_symptom_groups=("nausea",)),
    "head_injury": inputs(recognised_symptom_groups=("laceration",)),
    "neck_stiffness": inputs(recognised_symptom_groups=("headache",)),
    "vaginal_bleeding": inputs(recognised_symptom_groups=("abdominal pain",)),
    "syncope": inputs(recognised_symptom_groups=("dizziness",)),
}

# Presentations with no red flag, spanning the classifier's own three answers.
QUIET_CASES = (
    BASE,
    # The classifier's Medium anchor from test_prioritisation.py.
    inputs(
        age=80,
        temperature_c=36.8,
        heart_rate_bpm=80,
        systolic_bp=110,
        diastolic_bp=70,
        oxygen_saturation_percent=94,
    ),
    # Unremarkable vitals and severe pain: a presentation the classifier may
    # call High or not, but which fires no rule.
    inputs(
        age=95,
        pain_level=10,
        illness_duration_hours=1.0,
        temperature_c=37.2,
        heart_rate_bpm=90,
        systolic_bp=100,
        diastolic_bp=60,
        oxygen_saturation_percent=95,
    ),
)


@pytest.mark.parametrize(
    ("rule_id", "case"), FIRING_CASES.items(), ids=list(FIRING_CASES)
)
def test_each_rule_fires_and_raises_to_high(
    rule_id: str, case: PrioritisationInputs
) -> None:
    assert rule_id in fired_ids(case)
    # The classifier alone does not see this red flag; otherwise the layer
    # would not be what rescues the presentation.
    assert classifier_only(case) is not UrgencyLevel.high
    assert recommend(case) is UrgencyLevel.high


@pytest.mark.parametrize(
    ("rule_id", "case"), BOUNDARY_CASES.items(), ids=list(BOUNDARY_CASES)
)
def test_each_rule_does_not_fire_just_outside_its_threshold(
    rule_id: str, case: PrioritisationInputs
) -> None:
    assert rule_id not in fired_ids(case)
    # These cases carry no other red flag, so the classifier's answer passes
    # through untouched.
    assert fired_rules(case) == ()
    assert recommend(case) is classifier_only(case)


def test_every_rule_has_both_a_firing_and_a_boundary_case() -> None:
    rule_ids = {rule.id for rule in RULES}
    assert set(FIRING_CASES) == rule_ids
    assert set(BOUNDARY_CASES) == rule_ids


def test_the_rule_set_is_deliberately_bounded_and_cited() -> None:
    assert 15 <= len(RULES) <= 20
    assert len({rule.id for rule in RULES}) == len(RULES)
    for rule in RULES:
        assert rule.finding
        assert "ESI v4" in rule.citation


def test_the_danger_zone_bands_meet_at_their_documented_ages() -> None:
    at_three = inputs(age=3, heart_rate_bpm=150)
    assert "infant_tachycardia" not in fired_ids(at_three)
    assert "child_tachycardia" in fired_ids(at_three)

    at_eight = inputs(age=8, heart_rate_bpm=120)
    assert "child_tachycardia" not in fired_ids(at_eight)
    assert "adult_tachycardia" in fired_ids(at_eight)

    # RUBRIC.md treats exactly 8 years as the adult band for saturation too.
    at_eight_hypoxaemic = inputs(age=8, oxygen_saturation_percent=91)
    assert "adult_hypoxaemia" in fired_ids(at_eight_hypoxaemic)


def test_an_otherwise_quiet_hypoxaemic_young_adult_is_raised_to_high() -> None:
    case = inputs(age=24, oxygen_saturation_percent=88)

    assert classifier_only(case) is not UrgencyLevel.high
    assert recommend(case) is UrgencyLevel.high


@pytest.mark.parametrize("case", list(FIRING_CASES.values()), ids=list(FIRING_CASES))
def test_no_rule_can_lower_a_recommendation(case: PrioritisationInputs) -> None:
    for level in ALL_LEVELS:
        result = apply_safety_layer(case, level)
        assert URGENCY_RANK[result] <= URGENCY_RANK[level]
        if level is not UrgencyLevel.high:
            assert result is UrgencyLevel.high


@pytest.mark.parametrize("case", QUIET_CASES)
def test_no_firing_rule_returns_the_classifier_result_unchanged(
    case: PrioritisationInputs,
) -> None:
    expected = classifier_only(case)

    assert fired_rules(case) == ()
    assert recommend(case) is expected
    for level in ALL_LEVELS:
        assert apply_safety_layer(case, level) is level


def test_the_layer_reads_only_the_structured_inputs() -> None:
    left = inputs(presenting_complaint="Mild headache")
    right = inputs(presenting_complaint="Crushing chest pain, cannot breathe")

    assert fired_rules(left) == fired_rules(right) == ()
    assert recommend(left) is recommend(right)


def test_the_layer_keeps_the_three_second_budget() -> None:
    case = FIRING_CASES["adult_tachycardia"]

    started = time.perf_counter()
    for _ in range(1000):
        recommend(case)
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0


def test_every_rule_and_citation_is_visible_in_the_documentation() -> None:
    docs = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "red-flag-safety-layer.md"
    ).read_text(encoding="utf-8")

    for rule in RULES:
        assert rule.id in docs
        assert rule.citation in docs


def _open_hypoxaemic_young_adult(client: TestClient) -> dict[str, object]:
    patient = client.post(
        "/api/clinical/patients",
        json={
            "full_name": "Ada Lovelace",
            "age": 24,
            "sex": "female",
            "contact_phone": "07700 900123",
            "contact_email": None,
        },
    )
    assert patient.status_code in (200, 201)

    encounter = client.post(
        "/api/clinical/encounters",
        json={
            "patient_id": patient.json()["id"],
            "intake": {
                "presenting_complaint": "Mild headache for a day",
                "pain_level": 2,
                "illness_duration_hours": 24,
                "temperature_c": 36.6,
                "heart_rate_bpm": 70,
                "blood_pressure": {"systolic": 116, "diastolic": 72},
                "oxygen_saturation_percent": 88,
                "notes": None,
            },
        },
    )
    assert encounter.status_code == 201, encounter.text
    return encounter.json()


def test_the_safety_layers_result_is_what_is_stored_and_queued(
    clinical_client: TestClient,
) -> None:
    encounter = _open_hypoxaemic_young_adult(clinical_client)

    assessment = encounter["assessment"]
    # The classifier alone calls this presentation Low; the stored
    # recommendation is the composed result, and the Queue orders by it.
    assert assessment["machine_recommendation"] == "High"
    assert assessment["final_decision"] == "High"

    (entry,) = clinical_client.get("/api/clinical/queue").json()["entries"]
    assert entry["encounter_id"] == encounter["id"]
    assert entry["urgency_level"] == "High"
    assert entry["assessment"]["machine_recommendation"] == "High"
