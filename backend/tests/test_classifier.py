"""The shipped classifier artefact, loaded and used without a database.

These tests pin the contract the trained artefact has to satisfy: the feature
names match the engine's vector, the classes are the three Urgency Levels, the
provenance and cross-validated scores are recorded, and inference is fast and
deterministic.
"""

import json
import time

import pytest

from app.classifier import ARTEFACT_PATH, load_model
from app.features import FEATURE_NAMES
from app.prioritisation import UrgencyLevel
from app.symptom_groups import vocabulary


@pytest.fixture(scope="module")
def model():
    return load_model(ARTEFACT_PATH)


def test_the_shipped_artefact_exists_and_is_json() -> None:
    assert ARTEFACT_PATH.exists(), "run the documented training command"
    json.loads(ARTEFACT_PATH.read_text(encoding="utf-8"))


def test_the_artefact_was_trained_on_the_current_feature_vector(model) -> None:
    assert model.feature_names == FEATURE_NAMES
    assert model.vocabulary_version == vocabulary().version


def test_the_artefact_answers_with_the_three_urgency_levels(model) -> None:
    assert model.classes == (
        UrgencyLevel.high.value,
        UrgencyLevel.medium.value,
        UrgencyLevel.low.value,
    )


def test_the_artefact_records_its_dataset_provenance(model) -> None:
    sources = model.metadata["training"]["datasets"]

    assert sources
    for source in sources:
        assert source["title"]
        assert source["citation"]
        assert source["licence"]
        assert source["file_sha256"]


def test_the_artefact_records_cross_validated_scores(model) -> None:
    scores = model.metadata["cross_validation"]

    assert scores["folds"] >= 2
    assert 0.0 <= scores["accuracy"] <= 1.0
    assert 0.0 <= scores["macro_f1"] <= 1.0
    assert len(scores["confusion_matrix"]) == 3


def test_prediction_is_the_argmax_of_the_probabilities(model) -> None:
    vector = tuple(0.0 for _ in FEATURE_NAMES)

    probabilities = model.probabilities(vector)

    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert max(probabilities, key=probabilities.__getitem__) == model.predict(
        vector
    ).value


def test_the_same_vector_always_gives_the_same_level(model) -> None:
    vector = tuple(float(index) for index in range(len(FEATURE_NAMES)))

    assert model.predict(vector) is model.predict(vector)


def test_a_vector_of_the_wrong_length_is_rejected(model) -> None:
    with pytest.raises(ValueError):
        model.predict((1.0, 2.0, 3.0))


def test_inference_fits_inside_the_three_second_budget(model) -> None:
    vector = tuple(0.0 for _ in FEATURE_NAMES)

    started = time.perf_counter()
    for _ in range(1000):
        model.predict(vector)
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0


def test_the_artefact_is_small_enough_to_commit() -> None:
    assert ARTEFACT_PATH.stat().st_size < 512 * 1024
