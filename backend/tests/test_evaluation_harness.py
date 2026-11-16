"""The offline evaluation harness: the reproducible evidence run.

The harness has two deliberately separate modes. A cross-validated run scores
the learned classifier on the published dataset; a whole-pipeline run scores the
composed engine on the rubric-labelled synthetic corpus. The primary runs leave
the fallback disabled, and a third run with it enabled reports coverage as its
own statistic. Every figure is derived through the pure engine boundary, with no
database, and running twice over the same inputs is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.classifier import ARTEFACT_PATH
from app.features import MISSING_RESPIRATORY_RATE_BPM, FeatureInputs
from app.prioritisation import UrgencyLevel, assess
from app.symptom_groups import recognise
from evaluation import harness
from evaluation import triage_datasets as datasets
from evaluation.corpus import CORPUS_PATH, load_corpus
from evaluation.rubric import RUBRIC_VERSION

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
    """A small, deterministic training set that needs no downloaded data."""
    records: list[datasets.TrainingEncounter] = []
    for index in range(24):
        level = (
            UrgencyLevel.high
            if index < 8
            else UrgencyLevel.medium
            if index < 16
            else UrgencyLevel.low
        )
        offset = index % 8
        saturation = (
            82 + offset
            if level is UrgencyLevel.high
            else 94 + offset
            if level is UrgencyLevel.medium
            else 98
        )
        heart_rate = (
            130 + offset
            if level is UrgencyLevel.high
            else 100 + offset
            if level is UrgencyLevel.medium
            else 70 + offset
        )
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


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


@pytest.fixture(scope="module")
def constructed_evidence(corpus):
    return harness.build_evidence(
        constructed_records(),
        corpus,
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )


@pytest.fixture(scope="module")
def published_evidence(corpus):
    if not datasets.cached_files_exist():
        pytest.skip("published datasets are not cached; run the documented fetch first")
    return harness.build_evidence(
        datasets.load_training_records(),
        corpus,
        sources=datasets.dataset_identities(),
    )


def run_named(evidence: dict[str, object], name: str) -> dict[str, object]:
    runs = evidence["runs"]
    assert isinstance(runs, list)
    for run in runs:
        if run["id"] == name:
            return run
    raise AssertionError(f"no run named {name!r}")


# --- the metrics themselves -------------------------------------------------


def test_metrics_report_per_class_precision_and_recall() -> None:
    metrics = harness.compute_metrics(
        ["High", "High", "Medium", "Low", "Low", "High"],
        ["High", "Low", "High", "Low", "High", "Medium"],
    )

    assert metrics["per_class"]["High"]["precision"] == pytest.approx(1 / 3)
    assert metrics["per_class"]["High"]["recall"] == pytest.approx(1 / 3)
    assert metrics["per_class"]["High"]["support"] == 3
    assert metrics["per_class"]["Medium"]["precision"] == pytest.approx(0.0)
    assert metrics["per_class"]["Medium"]["recall"] == pytest.approx(0.0)
    assert metrics["per_class"]["Low"]["precision"] == pytest.approx(0.5)
    assert metrics["per_class"]["Low"]["recall"] == pytest.approx(0.5)


def test_the_confusion_matrix_has_ground_truth_rows_and_prediction_columns() -> None:
    metrics = harness.compute_metrics(
        ["High", "High", "Medium", "Low", "Low", "High"],
        ["High", "Low", "High", "Low", "High", "Medium"],
    )

    assert metrics["confusion_matrix"]["labels"] == ["High", "Medium", "Low"]
    assert metrics["confusion_matrix"]["rows"] == [
        [1, 1, 1],
        [1, 0, 0],
        [1, 0, 1],
    ]


def test_false_low_priority_rate_is_low_recommendations_over_non_low_truths() -> None:
    # The documented one-vs-rest definition: recommended Low with a non-Low
    # truth, over every non-Low truth. A missed High is not the denominator.
    metrics = harness.compute_metrics(
        ["High", "High", "High", "Medium", "Low"],
        ["High", "Medium", "Low", "Low", "Low"],
    )

    assert metrics["false_low_priority"]["count"] == 2
    assert metrics["false_low_priority"]["denominator"] == 4
    assert metrics["false_low_priority"]["rate"] == pytest.approx(0.5)


def test_high_class_recall_is_reported_as_its_own_missed_urgent_signal() -> None:
    metrics = harness.compute_metrics(
        ["High", "High", "High", "Medium", "Low"],
        ["High", "Medium", "Low", "Medium", "Low"],
    )

    recall = metrics["high_class_recall"]
    assert recall["count"] == 1
    assert recall["denominator"] == 3
    assert recall["rate"] == pytest.approx(1 / 3)
    # Its complement is the missed-urgent-cases share, not False Low.
    assert 1 - recall["rate"] == pytest.approx(2 / 3)


def test_false_high_priority_rate_counts_only_overtriaged_non_high_urgency() -> None:
    metrics = harness.compute_metrics(
        ["High", "High", "High", "Medium", "Low"],
        ["High", "Medium", "Low", "Medium", "High"],
    )

    assert metrics["false_high_priority"]["count"] == 1
    assert metrics["false_high_priority"]["denominator"] == 2
    assert metrics["false_high_priority"]["rate"] == pytest.approx(0.5)


def test_a_model_below_the_majority_baseline_is_legible_as_such() -> None:
    metrics = harness.compute_metrics(
        ["Low", "Low", "Low", "High"],
        ["Low", "High", "Medium", "High"],
    )

    baseline = metrics["majority_baseline"]
    assert baseline["class"] == "Low"
    assert baseline["accuracy"] == pytest.approx(0.75)
    assert metrics["accuracy"] == pytest.approx(0.5)
    assert baseline["beats_baseline"] is False
    assert baseline["model_minus_baseline"] == pytest.approx(-0.25)


def test_unknown_labels_are_rejected_rather_than_silently_scored() -> None:
    with pytest.raises(ValueError):
        harness.compute_metrics(["High"], ["Critical"])


# --- the two runs are separate, and the fallback is disabled in both --------


def test_the_two_modes_are_separate_runs(published_evidence) -> None:
    cross_validated = run_named(published_evidence, "cross_validated")
    pipeline = run_named(published_evidence, "pipeline")

    assert cross_validated["mode"] == "cross_validated"
    assert pipeline["mode"] == "pipeline"
    assert cross_validated["dataset"]["kind"] == "published_triage_dataset"
    assert pipeline["dataset"]["kind"] == "rubric_labelled_synthetic_corpus"
    assert cross_validated["metrics"] != pipeline["metrics"]


def test_the_primary_accuracy_runs_disable_the_fallback(published_evidence) -> None:
    for name in ("cross_validated", "pipeline"):
        run = run_named(published_evidence, name)
        assert run["fallback"] == "disabled"
        assert run["procedure"]["fallback_enabled"] is False
        assert "coverage" not in run


def test_pipeline_predictions_are_the_pure_engine_boundary(
    published_evidence, corpus
) -> None:
    run = run_named(published_evidence, "pipeline")
    assert run["metrics"]["encounter_count"] == corpus.encounter_count

    for encounter, prediction in zip(corpus.encounters, run["predictions"]):
        inputs = harness.pipeline_inputs(encounter)
        recommendation = assess(inputs)
        assert prediction["encounter_id"] == encounter.encounter_id
        assert prediction["ground_truth"] == encounter.ground_truth.urgency_level.value
        assert prediction["machine_recommendation"] == recommendation.level.value
        assert prediction["recognised_symptom_groups"] == list(
            recognise(encounter.intake.presenting_complaint)
        )
        assert prediction["fallback_used"] is False
        assert prediction["unclassified"] is False


def test_fallback_coverage_is_reported_as_its_own_statistic(
    published_evidence, corpus
) -> None:
    run = run_named(published_evidence, "pipeline_fallback_enabled")
    expected = sum(
        1
        for encounter in corpus.encounters
        if not recognise(encounter.intake.presenting_complaint)
    )

    coverage = run["coverage"]
    assert run["fallback"] == "enabled"
    assert coverage["encounters"] == corpus.encounter_count
    assert coverage["fallback_used"] == expected
    assert coverage["rate"] == pytest.approx(expected / corpus.encounter_count)
    assert coverage["unclassified"] == expected
    assert coverage["unclassified_rate"] == pytest.approx(
        expected / corpus.encounter_count
    )
    # The coverage run is a separate figure; the primary pipeline score is not
    # contaminated by it.
    primary = run_named(published_evidence, "pipeline")
    assert run["metrics"] != primary["metrics"]


# --- provenance -------------------------------------------------------------


def test_every_run_records_its_dataset_rubric_and_engine_identity(
    published_evidence,
) -> None:
    engine_sha256 = hashlib.sha256(ARTEFACT_PATH.read_bytes()).hexdigest()
    assert published_evidence["engine"]["artefact_sha256"] == engine_sha256

    for name in (
        "cross_validated",
        "pipeline",
        "pipeline_fallback_enabled",
    ):
        run = run_named(published_evidence, name)
        assert run["dataset"]["encounter_count"] > 0
        assert run["ground_truth"]
        assert run["engine_artefact"]["artefact_sha256"] == engine_sha256
        assert run["engine_artefact"]["artefact_version"]

    cross_validated = run_named(published_evidence, "cross_validated")
    # The published dataset carries its own triage labels, not the ESI rubric.
    assert cross_validated["ground_truth"]["rubric_version"] is None
    assert cross_validated["ground_truth"]["kind"] == "published_triage_level"

    pipeline = run_named(published_evidence, "pipeline")
    assert pipeline["ground_truth"]["rubric_version"] == RUBRIC_VERSION
    assert pipeline["ground_truth"]["kind"] == "esi_v4_rubric"
    assert pipeline["dataset"]["corpus_sha256"] == hashlib.sha256(
        CORPUS_PATH.read_bytes()
    ).hexdigest()


def test_the_primary_cross_validated_metrics_are_the_composed_engine(
    published_evidence,
) -> None:
    run = run_named(published_evidence, "cross_validated")
    variant = run["classifier_only"]

    # The classifier alone is a secondary diagnostic. The primary metrics must
    # include the safety layer, which can only raise a recommendation. Raising
    # can lower accuracy when it over-triages, so equality of accuracy is not
    # the property to assert.
    assert variant["metrics"] != run["metrics"]
    assert variant["metrics"]["encounter_count"] == run["metrics"][
        "encounter_count"
    ]
    composed_high = sum(row[0] for row in run["metrics"]["confusion_matrix"]["rows"])
    classifier_high = sum(
        row[0] for row in variant["metrics"]["confusion_matrix"]["rows"]
    )
    assert composed_high >= classifier_high
    assert "not a Machine Recommendation" in variant["description"]


def test_the_cross_validated_run_reproduces_the_artefacts_recorded_scores(
    published_evidence,
) -> None:
    recorded = json.loads(ARTEFACT_PATH.read_text(encoding="utf-8"))[
        "cross_validation"
    ]
    variant = run_named(published_evidence, "cross_validated")["classifier_only"]
    metrics = variant["metrics"]

    # The recorded block is the classifier-only cross-validation, so it is the
    # variant that must reproduce it - not the composed primary score.
    assert metrics["accuracy"] == pytest.approx(recorded["accuracy"], abs=1e-12)
    assert metrics["macro_f1"] == pytest.approx(recorded["macro_f1"], abs=1e-12)
    assert metrics["confusion_matrix"]["rows"] == recorded["confusion_matrix"]
    for level in harness.CLASS_ORDER:
        for statistic in ("precision", "recall", "f1", "support"):
            assert metrics["per_class"][level][statistic] == pytest.approx(
                recorded["per_class"][level][statistic], abs=1e-12
            )
    assert variant["matches_recorded_artefact"] is True


def test_the_shipped_classifier_is_reported_as_below_the_majority_baseline(
    published_evidence,
) -> None:
    metrics = run_named(published_evidence, "cross_validated")["classifier_only"][
        "metrics"
    ]

    assert metrics["majority_baseline"]["class"] == "Low"
    assert metrics["accuracy"] < metrics["majority_baseline"]["accuracy"]
    assert metrics["majority_baseline"]["beats_baseline"] is False


# --- reproducibility --------------------------------------------------------


def test_building_the_evidence_twice_is_byte_identical(
    tmp_path: Path, corpus
) -> None:
    first = harness.build_evidence(
        constructed_records(),
        corpus,
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )
    second = harness.build_evidence(
        constructed_records(),
        corpus,
        sources=(SOURCE,),
        folds=3,
        seed=20261103,
    )

    first_path = harness.write_evidence(first, tmp_path / "first.json")
    second_path = harness.write_evidence(second, tmp_path / "second.json")

    assert first_path.read_bytes() == second_path.read_bytes()


def test_the_committed_artefact_exists_and_is_readable() -> None:
    assert harness.RESULTS_PATH.exists()

    artefact = json.loads(harness.RESULTS_PATH.read_text(encoding="utf-8"))
    assert artefact["schema_version"] == harness.SCHEMA_VERSION
    assert artefact["harness_version"] == harness.HARNESS_VERSION
    assert artefact["class_order"] == list(harness.CLASS_ORDER)


def test_the_committed_artefact_is_the_current_harness_output(
    published_evidence,
) -> None:
    committed = json.loads(harness.RESULTS_PATH.read_text(encoding="utf-8"))

    assert committed == published_evidence
