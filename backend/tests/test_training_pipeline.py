"""Training is reproducible, dataset-agnostic, and records its own evidence.

These tests do not need the published datasets: they train on constructed
records. One further test retrains from the cached published datasets and
compares the result with the committed artefact, skipping when the cache is
absent (a fresh clone without network).
"""

import json
from pathlib import Path

import pytest

from app.classifier import load_model
from app.features import (
    FEATURE_NAMES,
    MISSING_RESPIRATORY_RATE_BPM,
    FeatureInputs,
)
from app.prioritisation import UrgencyLevel
from evaluation import triage_datasets as datasets
from evaluation.train_classifier import (
    ARTEFACT_PATH,
    build_artefact,
    write_artefact,
)

SOURCE = datasets.DatasetIdentity(
    source_id="constructed",
    title="Constructed records",
    citation="Constructed for the test suite.",
    licence="Not applicable",
    doi=None,
    file_sha256=(),
    note="",
)


def constructed_records() -> list[datasets.TrainingEncounter]:
    records: list[datasets.TrainingEncounter] = []
    for index in range(24):
        level = (
            UrgencyLevel.high if index < 8 else UrgencyLevel.medium if index < 16 else UrgencyLevel.low
        )
        offset = index % 8
        saturation = 82 + offset if level is UrgencyLevel.high else 94 + offset if level is UrgencyLevel.medium else 98
        heart_rate = 130 + offset if level is UrgencyLevel.high else 100 + offset if level is UrgencyLevel.medium else 70 + offset
        pain = 8 if level is UrgencyLevel.high else 5 if level is UrgencyLevel.medium else 1
        records.append(
            datasets.TrainingEncounter(
                source_id=SOURCE.source_id,
                encounter_id=f"constructed-{index:03d}",
                urgency_level=level,
                inputs=FeatureInputs(
                    recognised_symptom_groups=("fever",) if index % 2 else (),
                    pain_level=pain,
                    illness_duration_hours=float(index),
                    age=20 + index,
                    temperature_c=37.0 + (index % 5) * 0.2,
                    heart_rate_bpm=heart_rate,
                    systolic_bp=120,
                    diastolic_bp=80,
                    oxygen_saturation_percent=saturation,
                    respiratory_rate_bpm=MISSING_RESPIRATORY_RATE_BPM,
                ),
            )
        )
    return records


def test_the_artefact_carries_the_shape_the_engine_needs() -> None:
    artefact = build_artefact(
        constructed_records(),
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )

    assert artefact["feature_names"] == list(FEATURE_NAMES)
    assert artefact["classes"] == ["High", "Medium", "Low"]
    assert len(artefact["coef"]) == 3
    assert all(len(row) == len(FEATURE_NAMES) for row in artefact["coef"])
    assert len(artefact["intercept"]) == 3
    assert len(artefact["scaler"]["mean"]) == len(FEATURE_NAMES)
    assert len(artefact["scaler"]["scale"]) == len(FEATURE_NAMES)


def test_the_artefact_records_cross_validated_evidence() -> None:
    artefact = build_artefact(
        constructed_records(),
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )

    scores = artefact["cross_validation"]
    assert 0.0 <= scores["accuracy"] <= 1.0
    assert 0.0 <= scores["macro_f1"] <= 1.0
    assert scores["folds"] == 3
    assert scores["majority_baseline_accuracy"] == pytest.approx(1 / 3)
    assert len(scores["confusion_matrix"]) == 3
    assert set(scores["per_class"]) == {"High", "Medium", "Low"}
    for level in scores["per_class"].values():
        assert 0.0 <= level["precision"] <= 1.0
        assert 0.0 <= level["recall"] <= 1.0


def test_the_artefact_records_the_dataset_identity_and_vocabulary_version() -> None:
    artefact = build_artefact(
        constructed_records(),
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )

    assert artefact["training"]["datasets"][0]["source_id"] == "constructed"
    assert artefact["training"]["datasets"][0]["licence"] == "Not applicable"
    assert artefact["training"]["encounter_count"] == 24
    assert artefact["training"]["label_counts"] == {"High": 8, "Medium": 8, "Low": 8}
    assert artefact["vocabulary_version"]


def test_training_the_same_records_twice_is_byte_identical(tmp_path: Path) -> None:
    first = build_artefact(
        constructed_records(), sources=(SOURCE,), folds=3, seed=20261103
    )
    second = build_artefact(
        constructed_records(), sources=(SOURCE,), folds=3, seed=20261103
    )

    first_path = write_artefact(first, tmp_path / "first.json")
    second_path = write_artefact(second, tmp_path / "second.json")

    assert first_path.read_bytes() == second_path.read_bytes()


def test_a_written_artefact_can_be_loaded_and_used_by_the_engine(
    tmp_path: Path,
) -> None:
    artefact = build_artefact(
        constructed_records(), sources=(SOURCE,), folds=3, seed=20261103
    )
    path = write_artefact(artefact, tmp_path / "artefact.json")

    model = load_model(path)

    assert model.feature_names == FEATURE_NAMES
    assert set(model.classes) == {"High", "Medium", "Low"}
    assert model.predict(tuple(0.0 for _ in FEATURE_NAMES)) in {
        UrgencyLevel.high,
        UrgencyLevel.medium,
        UrgencyLevel.low,
    }


def test_the_committed_artefact_matches_the_shipped_training_code() -> None:
    if not datasets.cached_files_exist():
        pytest.skip("published datasets are not cached; run the documented fetch first")

    records = datasets.load_training_records()
    provenance = datasets.dataset_identities()
    regenerated = build_artefact(
        records,
        sources=provenance,
        folds=5,
        seed=20261103,
    )
    committed = json.loads(ARTEFACT_PATH.read_text(encoding="utf-8"))

    assert regenerated == committed
