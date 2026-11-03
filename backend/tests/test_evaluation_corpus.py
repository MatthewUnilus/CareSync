"""Behaviour of the synthetic, rubric-labelled evaluation corpus."""

import json
from collections import Counter
from pathlib import Path

from evaluation.corpus import (
    CORPUS_PATH,
    CORPUS_SCHEMA_VERSION,
    build_corpus,
    load_corpus,
)
from evaluation.generator import DEFAULT_SEED, generate
from evaluation.rubric import RUBRIC_VERSION, UrgencyLevel, label


def test_fixed_seed_produces_an_identical_corpus() -> None:
    first = build_corpus(seed=7)
    second = build_corpus(seed=7)

    assert first == second


def test_different_seeds_produce_different_encounters() -> None:
    first = build_corpus(seed=7)
    second = build_corpus(seed=8)

    assert first["encounters"] != second["encounters"]


def test_corpus_covers_all_three_urgency_levels() -> None:
    encounters = generate(DEFAULT_SEED)

    levels = Counter(encounter.ground_truth.urgency_level for encounter in encounters)

    assert set(levels) == {
        UrgencyLevel.high,
        UrgencyLevel.medium,
        UrgencyLevel.low,
    }
    assert all(count > 0 for count in levels.values())


def test_corpus_spans_all_four_vitals() -> None:
    encounters = generate(DEFAULT_SEED)

    temperatures = {encounter.intake.temperature_c for encounter in encounters}
    heart_rates = {encounter.intake.heart_rate_bpm for encounter in encounters}
    blood_pressures = {
        (encounter.intake.systolic_bp, encounter.intake.diastolic_bp)
        for encounter in encounters
    }
    saturations = {
        encounter.intake.oxygen_saturation_percent for encounter in encounters
    }

    assert len(temperatures) >= 3
    assert len(heart_rates) >= 3
    assert len(blood_pressures) >= 3
    assert len(saturations) >= 3
    assert min(saturations) < 92
    assert max(temperatures) > 38.0


def test_every_label_comes_from_the_rubric() -> None:
    for encounter in generate(DEFAULT_SEED):
        assert encounter.ground_truth == label(encounter.presentation)
        assert encounter.ground_truth.rubric_version == RUBRIC_VERSION


def test_labels_are_structurally_separate_from_machine_recommendations() -> None:
    corpus = build_corpus(DEFAULT_SEED)

    assert "machine_recommendation" not in repr(corpus)
    assert "final_decision" not in repr(corpus)
    assert "override" not in repr(corpus)
    for encounter in corpus["encounters"]:
        assert "ground_truth" in encounter
        assert "machine_recommendation" not in encounter
        assert "final_decision" not in encounter
        assert "override" not in encounter
        assert encounter["ground_truth"]["rubric_version"] == RUBRIC_VERSION


def test_committed_corpus_is_the_seeded_generator_output() -> None:
    assert CORPUS_PATH.exists(), "the versioned corpus artefact must be committed"

    corpus = load_corpus(CORPUS_PATH)

    assert corpus.schema_version == CORPUS_SCHEMA_VERSION
    assert corpus.rubric_version == RUBRIC_VERSION
    assert corpus.seed == DEFAULT_SEED
    assert corpus.encounter_count == len(corpus.encounters)
    assert [encounter.to_dict() for encounter in corpus.encounters] == build_corpus(
        corpus.seed
    )["encounters"]


def test_corpus_can_be_consumed_without_regenerating(
    tmp_path: Path,
) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(build_corpus(DEFAULT_SEED)), encoding="utf-8")

    corpus = load_corpus(path)

    assert corpus.encounter_count >= 20
    assert corpus.encounters[0].ground_truth.urgency_level in set(UrgencyLevel)
