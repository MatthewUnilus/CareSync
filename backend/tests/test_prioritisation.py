"""Seam B: the Prioritization Engine is a pure function.

These tests call the engine directly with constructed inputs. They import no
database, open no session, and assert only the returned Urgency Level, so they
survive any refactor of the engine's internals.
"""

from dataclasses import replace

import pytest

from app.prioritisation import (
    PrioritisationInputs,
    UrgencyLevel,
    recommend,
)

BASE_INPUTS = PrioritisationInputs(
    presenting_complaint="Mild headache",
    age=40,
    pain_level=2,
    illness_duration_hours=4.0,
    temperature_c=36.8,
    heart_rate_bpm=78,
    systolic_bp=120,
    diastolic_bp=80,
    oxygen_saturation_percent=98,
)

ALL_LEVELS = {UrgencyLevel.high, UrgencyLevel.medium, UrgencyLevel.low}


def engine(**overrides: object) -> UrgencyLevel:
    return recommend(replace(BASE_INPUTS, **overrides))


def test_quiet_vitals_and_low_pain_recommend_low() -> None:
    assert engine() is UrgencyLevel.low


def test_moderate_pain_recommends_medium() -> None:
    assert engine(pain_level=6) is UrgencyLevel.medium


def test_severe_pain_recommends_high() -> None:
    assert engine(pain_level=9) is UrgencyLevel.high


@pytest.mark.parametrize(
    "overrides",
    [
        {"oxygen_saturation_percent": 89},
        {"heart_rate_bpm": 132},
        {"heart_rate_bpm": 44},
        {"systolic_bp": 84},
        {"systolic_bp": 186},
        {"temperature_c": 39.4},
        {"temperature_c": 34.6},
        {"pain_level": 10},
    ],
)
def test_a_single_severe_vital_or_severe_pain_recommends_high(
    overrides: dict[str, object],
) -> None:
    assert engine(**overrides) is UrgencyLevel.high


@pytest.mark.parametrize(
    "overrides",
    [
        {"oxygen_saturation_percent": 94},
        {"heart_rate_bpm": 108},
        {"systolic_bp": 96},
        {"systolic_bp": 166},
        {"temperature_c": 38.3},
        {"temperature_c": 35.4},
        {"pain_level": 5},
    ],
)
def test_a_moderate_vital_or_moderate_pain_recommends_medium(
    overrides: dict[str, object],
) -> None:
    assert engine(**overrides) is UrgencyLevel.medium


def test_threshold_boundaries_are_deterministic() -> None:
    assert engine(oxygen_saturation_percent=92) is UrgencyLevel.medium
    assert engine(oxygen_saturation_percent=91) is UrgencyLevel.high
    assert engine(pain_level=7) is UrgencyLevel.medium
    assert engine(pain_level=8) is UrgencyLevel.high


def test_the_same_constructed_inputs_always_give_the_same_answer() -> None:
    first = engine(pain_level=4, temperature_c=38.9)
    second = engine(pain_level=4, temperature_c=38.9)

    assert first is second
    assert first in ALL_LEVELS


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"pain_level": 6},
        {"pain_level": 9},
        {"oxygen_saturation_percent": 88},
        {"heart_rate_bpm": 140},
        {"temperature_c": 39.5},
    ],
)
def test_the_answer_is_always_exactly_one_urgency_level(
    overrides: dict[str, object],
) -> None:
    assert engine(**overrides) in ALL_LEVELS
