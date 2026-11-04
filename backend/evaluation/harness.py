"""The offline, reproducible evidence run behind the dissertation.

The harness scores the Prioritization Engine against labelled data through the
pure engine boundary (Seam B). It opens no database, starts no server and uses
no clock: the same fixed inputs produce the same figures, byte for byte.

Two modes, reported separately
------------------------------
``cross_validated``
    Stratified k-fold cross-validation on the published training dataset. A
    model is refit inside every fold with exactly the training step's estimator,
    so the score measures learning rather than resubstitution. The published
    source labels rows with its own three-level triage category; the ESI rubric
    does not apply to this run, and the artefact records that explicitly. The
    resulting figures reproduce the ``cross_validation`` block the shipped
    engine artefact already carries.

``pipeline``
    The whole pipeline on the rubric-labelled synthetic corpus: free-text
    complaint → Symptom Group recognition → classifier → red-flag safety layer →
    Machine Recommendation. Ground truth comes only from the independent ESI v4
    rubric, never from the engine.

The primary runs leave the fallback disabled, because a runtime provider is not
reproducible. A third run enables the fallback and reports *coverage* — the
share of Encounters whose complaint matched no Symptom Group — as its own
statistic rather than folding it into the primary score. With no provider
configured the run takes the documented degraded path (Medium, then the safety
layer, flagged unclassified), which is deterministic and therefore auditable.

The majority-class baseline is reported beside every score. The shipped model
is below it: the training source records no complaint, pain or duration, so the
classifier sees only age and the four vitals. That is a finding to display, not
a number to hide.

Usage, from ``backend/``::

    uv run python -m evaluation.harness

The versioned artefact is written to
``evaluation/results/accuracy-evaluation-v1.0.0.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.classifier import ARTEFACT_PATH
from app.fallback import (
    DEFAULT_TIMEOUT_LEVEL,
    FallbackResolver,
    MemoryFallbackCache,
    UnavailableFallbackProvider,
)
from app.features import FeatureInputs
from app.prioritisation import (
    PrioritisationInputs,
    UrgencyLevel,
    assess,
)
from app.red_flags import apply_safety_layer
from app.symptom_groups import recognise, vocabulary
from evaluation import triage_datasets as datasets
from evaluation.artefact import HARNESS_VERSION, RESULTS_PATH, SCHEMA_VERSION
from evaluation.corpus import CORPUS_PATH, Corpus, load_corpus
from evaluation.generator import LabelledEncounter
from evaluation.triage_datasets import DatasetIdentity, TrainingEncounter
from evaluation.train_classifier import DEFAULT_SEED, build_estimator

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PRIMARY_FOLDS = 5
PRIMARY_SEED = DEFAULT_SEED

#: Rows and columns of the confusion matrix, and the order of per-class figures.
CLASS_ORDER: tuple[str, ...] = (
    UrgencyLevel.high.value,
    UrgencyLevel.medium.value,
    UrgencyLevel.low.value,
)

METRIC_DEFINITIONS: dict[str, str] = {
    "accuracy": "correct Machine Recommendations divided by scored Encounters",
    "per_class": (
        "precision = correctly recommended as this level / all recommended as "
        "this level; recall = correctly recommended as this level / all labelled "
        "as this level; zero_division is reported as 0"
    ),
    "confusion_matrix": (
        "rows are ground-truth Urgency Levels and columns are Machine "
        "Recommendations, in the order High, Medium, Low"
    ),
    "false_high_priority": (
        "share of ground-truth Medium or Low Encounters recommended High "
        "(over-triage): recommended High with a non-High truth / every "
        "non-High truth"
    ),
    "false_low_priority": (
        "share of ground-truth Medium or High Encounters recommended Low "
        "(under-triage): recommended Low with a non-Low truth / every "
        "non-Low truth"
    ),
    "high_class_recall": (
        "share of ground-truth High Encounters recommended High; its "
        "complement is the missed-urgent-cases signal"
    ),
    "majority_baseline": (
        "always predicting the commonest ground-truth class in the scored set; "
        "beats_baseline is true only when accuracy is strictly greater"
    ),
    "coverage": (
        "share of Encounters whose complaint matched no Symptom Group and was "
        "therefore resolved by the fallback path"
    ),
}


@dataclass(frozen=True)
class PipelinePrediction:
    """One scored Encounter in the whole-pipeline run."""

    encounter_id: str
    ground_truth: str
    machine_recommendation: str
    recognised_symptom_groups: tuple[str, ...]
    fallback_used: bool
    unclassified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "encounter_id": self.encounter_id,
            "ground_truth": self.ground_truth,
            "machine_recommendation": self.machine_recommendation,
            "recognised_symptom_groups": list(self.recognised_symptom_groups),
            "fallback_used": self.fallback_used,
            "unclassified": self.unclassified,
        }


# --- metrics ----------------------------------------------------------------


def compute_metrics(
    ground_truth: Sequence[object],
    predictions: Sequence[object],
) -> dict[str, Any]:
    """Return every figure the Accuracy Evaluation Report needs for one run.

    The function is deliberately plain Python: the same inputs give the same
    numbers, with no library version drift in the scoring itself.
    """
    truth = [_level_name(value) for value in ground_truth]
    predicted = [_level_name(value) for value in predictions]
    if len(truth) != len(predicted):
        raise ValueError("ground truth and predictions must have equal length")
    if not truth:
        raise ValueError("there is nothing to score")
    unknown = (set(truth) | set(predicted)) - set(CLASS_ORDER)
    if unknown:
        raise ValueError(f"unknown Urgency Level(s): {sorted(unknown)}")

    matrix = [[0 for _ in CLASS_ORDER] for _ in CLASS_ORDER]
    for actual, guess in zip(truth, predicted):
        matrix[CLASS_ORDER.index(actual)][CLASS_ORDER.index(guess)] += 1

    total = len(truth)
    correct = sum(matrix[index][index] for index in range(len(CLASS_ORDER)))
    accuracy = correct / total

    per_class: dict[str, dict[str, object]] = {}
    f1_scores: list[float] = []
    truth_counts = Counter(truth)
    prediction_counts = Counter(predicted)
    for index, level in enumerate(CLASS_ORDER):
        true_positive = matrix[index][index]
        support = truth_counts.get(level, 0)
        predicted_count = prediction_counts.get(level, 0)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        f1_scores.append(f1)
        per_class[level] = {
            "precision": _round(precision),
            "recall": _round(recall),
            "f1": _round(f1),
            "support": support,
        }

    majority_class = _majority_class(truth_counts)
    majority_accuracy = truth_counts[majority_class] / total

    non_high = [index for index, level in enumerate(truth) if level != CLASS_ORDER[0]]
    non_low = [index for index, level in enumerate(truth) if level != CLASS_ORDER[2]]
    false_high = sum(1 for index in non_high if predicted[index] == CLASS_ORDER[0])
    false_low = sum(1 for index in non_low if predicted[index] == CLASS_ORDER[2])
    high_support = truth_counts.get(CLASS_ORDER[0], 0)
    high_correct = matrix[0][0]

    return {
        "encounter_count": total,
        "accuracy": _round(accuracy),
        "macro_f1": _round(sum(f1_scores) / len(f1_scores)),
        "majority_baseline": {
            "class": majority_class,
            "accuracy": _round(majority_accuracy),
            "model_minus_baseline": _round(accuracy - majority_accuracy),
            "beats_baseline": accuracy > majority_accuracy,
        },
        "confusion_matrix": {
            "labels": list(CLASS_ORDER),
            "rows": matrix,
        },
        "per_class": per_class,
        "false_high_priority": {
            "count": false_high,
            "denominator": len(non_high),
            "rate": _round(false_high / len(non_high)) if non_high else 0.0,
        },
        "false_low_priority": {
            "count": false_low,
            "denominator": len(non_low),
            "rate": _round(false_low / len(non_low)) if non_low else 0.0,
        },
        "high_class_recall": {
            "count": high_correct,
            "denominator": high_support,
            "rate": _round(high_correct / high_support) if high_support else 0.0,
        },
    }


def _majority_class(counts: Counter[str]) -> str:
    """The commonest label, breaking ties in :data:`CLASS_ORDER` order."""
    best = CLASS_ORDER[0]
    for level in CLASS_ORDER[1:]:
        if counts.get(level, 0) > counts.get(best, 0):
            best = level
    return best


def _level_name(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _round(value: float) -> float:
    return round(float(value), 12)


# --- the pure engine boundary ----------------------------------------------


def cross_validated_predictions(
    records: Sequence[TrainingEncounter],
    *,
    folds: int = PRIMARY_FOLDS,
    seed: int = PRIMARY_SEED,
) -> list[str]:
    """Score the learned layer out of fold, with no database in the path.

    The estimator and fold split are the training step's own, so this run
    reproduces the artefact's recorded cross-validation rather than inventing a
    second procedure.
    """
    if not records:
        raise ValueError("no training records")
    if folds < 2:
        raise ValueError("cross-validation needs at least two folds")

    labels = np.array(
        [record.urgency_level.value for record in records], dtype=object
    )
    present = set(labels.tolist())
    if len(present) < 2:
        raise ValueError("training data must cover at least two Urgency Levels")
    counts = Counter(labels.tolist())
    for level in present:
        if counts[level] < folds:
            raise ValueError(
                f"{level} has fewer than {folds} Encounters; reduce --folds"
            )

    matrix = np.array([record.inputs.vector() for record in records], dtype=float)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    predicted = cross_val_predict(
        build_estimator(seed), matrix, labels, cv=splitter
    )
    return [str(value) for value in predicted]


def composed_predictions(
    records: Sequence[TrainingEncounter],
    classifier_predictions: Sequence[str],
) -> list[str]:
    """Apply the deterministic safety layer to out-of-fold predictions."""
    if len(records) != len(classifier_predictions):
        raise ValueError("one prediction is needed per record")
    return [
        apply_safety_layer(
            prioritisation_inputs_from_features(record.inputs),
            UrgencyLevel(str(prediction)),
        ).value
        for record, prediction in zip(records, classifier_predictions)
    ]


def prioritisation_inputs_from_features(
    features: FeatureInputs,
) -> PrioritisationInputs:
    """Adapt a training feature row to the Seam B input dataclass."""
    return PrioritisationInputs(
        presenting_complaint="",
        age=int(round(features.age)),
        pain_level=int(features.pain_level),
        illness_duration_hours=float(features.illness_duration_hours),
        temperature_c=float(features.temperature_c),
        heart_rate_bpm=int(features.heart_rate_bpm),
        systolic_bp=int(features.systolic_bp),
        diastolic_bp=int(features.diastolic_bp),
        oxygen_saturation_percent=int(features.oxygen_saturation_percent),
        recognised_symptom_groups=tuple(features.recognised_symptom_groups),
    )


def pipeline_inputs(encounter: LabelledEncounter) -> PrioritisationInputs:
    """Build exactly the intake inputs the product would pass to the engine."""
    intake = encounter.intake
    return PrioritisationInputs(
        presenting_complaint=intake.presenting_complaint,
        age=int(round(encounter.patient_age_years)),
        pain_level=intake.pain_level,
        illness_duration_hours=intake.illness_duration_hours,
        temperature_c=intake.temperature_c,
        heart_rate_bpm=intake.heart_rate_bpm,
        systolic_bp=intake.systolic_bp,
        diastolic_bp=intake.diastolic_bp,
        oxygen_saturation_percent=intake.oxygen_saturation_percent,
        recognised_symptom_groups=recognise(intake.presenting_complaint),
    )


def score_pipeline(
    corpus: Corpus,
    *,
    fallback: FallbackResolver | None = None,
) -> tuple[PipelinePrediction, ...]:
    """Run every corpus Encounter through intake to Machine Recommendation."""
    scored: list[PipelinePrediction] = []
    for encounter in corpus.encounters:
        inputs = pipeline_inputs(encounter)
        recommendation = assess(inputs, fallback=fallback)
        scored.append(
            PipelinePrediction(
                encounter_id=encounter.encounter_id,
                ground_truth=encounter.ground_truth.urgency_level.value,
                machine_recommendation=recommendation.level.value,
                recognised_symptom_groups=inputs.recognised_symptom_groups,
                fallback_used=recommendation.fallback_used,
                unclassified=recommendation.unclassified,
            )
        )
    return tuple(scored)


def evaluation_fallback() -> FallbackResolver:
    """The deterministic fallback configuration used for the coverage run.

    No external provider is configured, so every fallback call takes the
    documented degraded path: Medium, then the safety layer, flagged
    unclassified. A fake provider that invented labels would make the coverage
    figure look richer while making it unreproducible.
    """
    return FallbackResolver(
        UnavailableFallbackProvider(
            "no fallback provider is configured for the offline evaluation"
        ),
        cache=MemoryFallbackCache(),
        default_level=DEFAULT_TIMEOUT_LEVEL,
    )


# --- provenance -------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(BACKEND_ROOT).as_posix()
    except ValueError:
        return str(path)


def _label_counts(labels: Sequence[str]) -> dict[str, int]:
    counts = Counter(labels)
    return {level: counts.get(level, 0) for level in CLASS_ORDER}


def engine_identity(path: Path = ARTEFACT_PATH) -> dict[str, object]:
    """Everything needed to say which engine artefact produced a figure."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    training = data["training"]
    return {
        "artefact_version": str(data["artefact_version"]),
        "artefact_path": _relative(path),
        "artefact_sha256": _sha256(path),
        "model_family": str(data["model_family"]),
        "vocabulary_version": str(data["vocabulary_version"]),
        "classes": [str(name) for name in data["classes"]],
        "feature_count": len(data["feature_names"]),
        "training": {
            "encounter_count": int(training["encounter_count"]),
            "label_counts": dict(training["label_counts"]),
            "source_counts": dict(training["source_counts"]),
            "folds": int(training["folds"]),
            "seed": int(training["seed"]),
            "datasets": list(training["datasets"]),
            "constant_features": list(training["constant_features"]),
            "limitations": list(training["limitations"]),
        },
    }


def _run_engine_identity(
    engine: dict[str, object], *, scored_by: str, note: str
) -> dict[str, object]:
    return {
        "artefact_version": engine["artefact_version"],
        "artefact_path": engine["artefact_path"],
        "artefact_sha256": engine["artefact_sha256"],
        "scored_by": scored_by,
        "note": note,
    }


def corpus_identity(
    corpus: Corpus, path: Path = CORPUS_PATH
) -> dict[str, object]:
    metadata = corpus.metadata
    return {
        "kind": "rubric_labelled_synthetic_corpus",
        "path": _relative(path),
        "corpus_sha256": _sha256(path),
        "schema_version": corpus.schema_version,
        "rubric_version": corpus.rubric_version,
        "rubric_citation": str(metadata["rubric_citation"]),
        "rubric_document": str(metadata["rubric_document"]),
        "generator_version": str(metadata["generator_version"]),
        "seed": corpus.seed,
        "encounter_count": corpus.encounter_count,
        "label_counts": _label_counts(
            [
                encounter.ground_truth.urgency_level.value
                for encounter in corpus.encounters
            ]
        ),
    }


def _corpus_ground_truth(corpus: Corpus) -> dict[str, object]:
    return {
        "kind": "esi_v4_rubric",
        "rubric_version": corpus.rubric_version,
        "rubric_document": str(corpus.metadata["rubric_document"]),
        "rubric_citation": str(corpus.metadata["rubric_citation"]),
        "label_namespace": "ground_truth",
        "independent_of_engine": True,
        "note": (
            "every label is the output of evaluation.rubric.label applied to "
            "the Encounter's described presentation"
        ),
    }


def _published_dataset_identity(
    records: Sequence[TrainingEncounter],
    sources: Sequence[DatasetIdentity],
) -> dict[str, object]:
    return {
        "kind": "published_triage_dataset",
        "source_ids": [source.source_id for source in sources],
        "encounter_count": len(records),
        "label_counts": _label_counts(
            [record.urgency_level.value for record in records]
        ),
        "sources": [source.as_dict() for source in sources],
    }


def _published_ground_truth(
    sources: Sequence[DatasetIdentity],
) -> dict[str, object]:
    wanted = {source.source_id for source in sources}
    mapping: dict[str, str] = {}
    for source in datasets.provenance()["sources"]:
        if source["source_id"] in wanted and source.get("label_mapping"):
            mapping.update(
                {
                    str(key): str(value)
                    for key, value in source["label_mapping"].items()
                }
            )
    return {
        "kind": "published_triage_level",
        "rubric_version": None,
        "rubric_document": None,
        "label_source": (
            "the published source's own three-level triage category"
        ),
        "mapping": mapping,
        "note": (
            "the ESI rubric is not applicable to this run: the published "
            "dataset does not supply the presentation fields the rubric needs"
        ),
    }


def _published_procedure(folds: int, seed: int) -> dict[str, object]:
    return {
        "method": "stratified_k_fold_cross_validation",
        "folds": folds,
        "seed": seed,
        "estimator": "multinomial logistic regression (L2, class_weight=balanced)",
        "standardiser": "fit inside each fold",
        "database_involved": False,
        "fallback_enabled": False,
        "scored_by": (
            "a model refit inside each fold from the training step's own "
            "estimator configuration"
        ),
    }


def _pipeline_procedure(*, fallback_enabled: bool) -> dict[str, object]:
    stages = [
        "spaCy Symptom Group recognition",
        "trained classifier",
        "red-flag safety layer",
        "fallback" if fallback_enabled else "fallback disabled",
    ]
    return {
        "method": "whole_pipeline",
        "stages": stages,
        "database_involved": False,
        "fallback_enabled": fallback_enabled,
        "recognition": (
            "app.symptom_groups.recognise over the fixed vocabulary, version "
            f"{vocabulary().version}"
        ),
    }


def _matches_recorded(
    metrics: dict[str, Any], recorded: dict[str, Any]
) -> bool:
    if not _close(metrics["accuracy"], recorded["accuracy"]):
        return False
    if not _close(metrics["macro_f1"], recorded["macro_f1"]):
        return False
    if metrics["confusion_matrix"]["rows"] != recorded["confusion_matrix"]:
        return False
    for level in CLASS_ORDER:
        for statistic in ("precision", "recall", "f1", "support"):
            if not _close(
                metrics["per_class"][level][statistic],
                recorded["per_class"][level][statistic],
            ):
                return False
    return True


def _close(first: object, second: object) -> bool:
    return abs(float(first) - float(second)) <= 1e-9


# --- the artefact -----------------------------------------------------------


def build_evidence(
    records: Sequence[TrainingEncounter],
    corpus: Corpus,
    *,
    sources: Sequence[DatasetIdentity] | None = None,
    folds: int = PRIMARY_FOLDS,
    seed: int = PRIMARY_SEED,
    engine_path: Path = ARTEFACT_PATH,
    corpus_path: Path = CORPUS_PATH,
) -> dict[str, Any]:
    """Build the self-describing evidence artefact.

    No database, server or clock is touched. Every identity is read from the
    files that are actually scored, so the artefact cannot quietly describe a
    different dataset or engine from the one that produced its figures.
    """
    sources = tuple(
        sources if sources is not None else datasets.dataset_identities()
    )
    engine = engine_identity(engine_path)
    recorded_cross_validation = json.loads(
        Path(engine_path).read_text(encoding="utf-8")
    )["cross_validation"]

    # Mode one: cross-validated scoring of the composed engine. The primary
    # score is the Machine Recommendation the engine actually produces, so it
    # includes the deterministic safety layer. The classifier alone is kept
    # beside it as a clearly labelled secondary variant: it is not a Machine
    # Recommendation.
    classifier_predictions = cross_validated_predictions(
        records, folds=folds, seed=seed
    )
    labels = [record.urgency_level.value for record in records]
    classifier_only_metrics = compute_metrics(labels, classifier_predictions)
    composed_metrics = compute_metrics(
        labels, composed_predictions(records, classifier_predictions)
    )

    cross_validated_run = {
        "id": "cross_validated",
        "mode": "cross_validated",
        "description": (
            "the composed engine — out-of-fold classifier plus the "
            "deterministic red-flag safety layer — scored on the published "
            "training dataset; the primary metrics are Machine Recommendations"
        ),
        "fallback": "disabled",
        "dataset": _published_dataset_identity(records, sources),
        "ground_truth": _published_ground_truth(sources),
        "procedure": _published_procedure(folds, seed),
        "engine_artefact": _run_engine_identity(
            engine,
            scored_by="fold_refit",
            note=(
                "cross-validation refits the shipped artefact's training "
                "procedure; the shipped artefact's identity is recorded so the "
                "reproduction can be checked"
            ),
        ),
        "metrics": composed_metrics,
        "classifier_only": {
            "description": (
                "the learned classifier layer alone, without the safety layer; "
                "this is a secondary diagnostic and is not a Machine "
                "Recommendation"
            ),
            "metrics": classifier_only_metrics,
            "matches_recorded_artefact": _matches_recorded(
                classifier_only_metrics, recorded_cross_validation
            ),
        },
    }

    # Mode two: the whole pipeline, primary run with the fallback disabled.
    pipeline_scored = score_pipeline(corpus)
    pipeline_metrics = compute_metrics(
        [result.ground_truth for result in pipeline_scored],
        [result.machine_recommendation for result in pipeline_scored],
    )
    pipeline_run = {
        "id": "pipeline",
        "mode": "pipeline",
        "description": (
            "every rubric-labelled synthetic Encounter taken from intake "
            "inputs to Machine Recommendation, with the fallback disabled"
        ),
        "fallback": "disabled",
        "dataset": corpus_identity(corpus, corpus_path),
        "ground_truth": _corpus_ground_truth(corpus),
        "procedure": _pipeline_procedure(fallback_enabled=False),
        "engine_artefact": _run_engine_identity(
            engine,
            scored_by="shipped_artefact",
            note="the committed classifier artefact and safety layer",
        ),
        "metrics": pipeline_metrics,
        "predictions": [result.as_dict() for result in pipeline_scored],
    }

    # Separate run: fallback enabled, coverage reported as its own statistic.
    fallback_scored = score_pipeline(corpus, fallback=evaluation_fallback())
    fallback_metrics = compute_metrics(
        [result.ground_truth for result in fallback_scored],
        [result.machine_recommendation for result in fallback_scored],
    )
    fallback_used = sum(1 for result in fallback_scored if result.fallback_used)
    unclassified = sum(1 for result in fallback_scored if result.unclassified)
    fallback_run = {
        "id": "pipeline_fallback_enabled",
        "mode": "pipeline",
        "description": (
            "the same whole-pipeline run with the fallback enabled; its "
            "accuracy is not the primary score"
        ),
        "fallback": "enabled",
        "dataset": corpus_identity(corpus, corpus_path),
        "ground_truth": _corpus_ground_truth(corpus),
        "procedure": _pipeline_procedure(fallback_enabled=True),
        "engine_artefact": _run_engine_identity(
            engine,
            scored_by="shipped_artefact",
            note=(
                "the committed classifier artefact, safety layer and the "
                "deterministic degraded fallback"
            ),
        ),
        "coverage": {
            "encounters": len(fallback_scored),
            "fallback_used": fallback_used,
            "rate": _round(fallback_used / len(fallback_scored)),
            "unclassified": unclassified,
            "unclassified_rate": _round(unclassified / len(fallback_scored)),
            "provider": "unavailable",
            "default_level": DEFAULT_TIMEOUT_LEVEL,
            "note": (
                "coverage is the share of Encounters that reached the fallback "
                "path; no external provider is configured for the offline run, "
                "so every such Encounter is flagged unclassified"
            ),
        },
        "metrics": fallback_metrics,
        "predictions": [result.as_dict() for result in fallback_scored],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "class_order": list(CLASS_ORDER),
        "metric_definitions": dict(METRIC_DEFINITIONS),
        "engine": engine,
        "runs": [cross_validated_run, pipeline_run, fallback_run],
    }


def write_evidence(
    evidence: dict[str, Any], path: Path = RESULTS_PATH
) -> Path:
    """Write the artefact as stable, sorted JSON and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


# --- command line -----------------------------------------------------------


def _print_run(run: dict[str, Any]) -> None:
    metrics = run["metrics"]
    baseline = metrics["majority_baseline"]
    relation = "above" if baseline["beats_baseline"] else "BELOW"
    print(
        f"{run['id']} ({run['mode']}, fallback {run['fallback']}): "
        f"accuracy {metrics['accuracy']:.3f} vs majority "
        f"{baseline['accuracy']:.3f} ({relation} baseline), "
        f"macro F1 {metrics['macro_f1']:.3f}"
    )
    if "coverage" in run:
        coverage = run["coverage"]
        print(
            f"  coverage {coverage['rate']:.3f} "
            f"({coverage['fallback_used']}/{coverage['encounters']}), "
            f"unclassified {coverage['unclassified_rate']:.3f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline evaluation harness and write the versioned "
            "accuracy-evaluation artefact."
        )
    )
    parser.add_argument("--folds", type=int, default=PRIMARY_FOLDS)
    parser.add_argument("--seed", type=int, default=PRIMARY_SEED)
    parser.add_argument("--out", type=Path, default=RESULTS_PATH)
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="fail if the published datasets are not already cached",
    )
    args = parser.parse_args(argv)

    if not datasets.cached_files_exist() and not args.no_fetch:
        datasets.fetch()

    records = datasets.load_training_records()
    corpus = load_corpus()
    evidence = build_evidence(
        records,
        corpus,
        sources=datasets.dataset_identities(),
        folds=args.folds,
        seed=args.seed,
    )
    path = write_evidence(evidence, args.out)

    print(f"wrote {path}")
    for run in evidence["runs"]:
        _print_run(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
