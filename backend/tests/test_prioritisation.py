"""Seam B: the Prioritization Engine is a pure function.

These tests call the engine directly with constructed inputs. They import no
database, open no session, and assert only the returned Urgency Level, so they
survive any refactor of the engine's internals. Since ticket 06 the level comes
from the trained classifier; the anchors below are the presentations the shipped
interim artefact separates, and they are asserted exactly because the engine is
deterministic.
"""

import time
from dataclasses import replace

import pytest

from app.prioritisation import (
    PrioritisationInputs,
    UrgencyLevel,
    recommend,
)

# A young patient with quiet vitals: the artefact's Low anchor.
BASE_INPUTS = PrioritisationInputs(
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

# An older patient with moderate observations: the artefact's Medium anchor.
MEDIUM_OVERVIEW = {
    "age": 80,
    "temperature_c": 36.8,
    "heart_rate_bpm": 80,
    "systolic_bp": 110,
    "diastolic_bp": 70,
    "oxygen_saturation_percent": 94,
}

# A deteriorating presentation: the artefact's High anchor.
HIGH_OVERVIEW = {
    "age": 78,
    "temperature_c": 38.4,
    "heart_rate_bpm": 130,
    "systolic_bp": 95,
    "diastolic_bp": 58,
    "oxygen_saturation_percent": 88,
}

ALL_LEVELS = {UrgencyLevel.high, UrgencyLevel.medium, UrgencyLevel.low}


def engine(**overrides: object) -> UrgencyLevel:
    return recommend(replace(BASE_INPUTS, **overrides))


def test_quiet_vitals_in_a_young_patient_recommend_low() -> None:
    assert engine() is UrgencyLevel.low


def test_a_moderate_presentation_recommends_medium() -> None:
    assert engine(**MEDIUM_OVERVIEW) is UrgencyLevel.medium


def test_a_deteriorating_presentation_recommends_high() -> None:
    assert engine(**HIGH_OVERVIEW) is UrgencyLevel.high


def test_the_recommendation_runs_on_the_structured_inputs_not_the_text() -> None:
    first = engine(presenting_complaint="Mild headache")
    second = engine(presenting_complaint="Crushing chest pain, cannot breathe")

    assert first is second


def test_the_same_constructed_inputs_always_give_the_same_answer() -> None:
    first = engine(**HIGH_OVERVIEW)
    second = engine(**HIGH_OVERVIEW)

    assert first is second
    assert first in ALL_LEVELS


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {**MEDIUM_OVERVIEW},
        {**HIGH_OVERVIEW},
        {"oxygen_saturation_percent": 84},
        {"heart_rate_bpm": 150},
        {"systolic_bp": 80, "diastolic_bp": 50},
        {"temperature_c": 40.1},
        {"age": 95},
        {"pain_level": 10},
        {"recognised_symptom_groups": ("chest pain", "shortness of breath")},
    ],
)
def test_the_answer_is_always_exactly_one_urgency_level(
    overrides: dict[str, object],
) -> None:
    assert engine(**overrides) in ALL_LEVELS


def test_inference_fits_inside_the_three_second_budget() -> None:
    started = time.perf_counter()
    for _ in range(1000):
        engine(**HIGH_OVERVIEW)
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0
