"""Train the Urgency classifier and record the evidence with the artefact.

Documented command, from ``backend/``::

    uv run python -m evaluation.train_classifier

It downloads the published datasets if they are not cached (verifying their
SHA-256 against ``evaluation/datasets/provenance.json``), trains a multinomial
logistic regression on the same feature vector the engine builds, computes
stratified k-fold cross-validated scores, and writes a small JSON artefact plus
the dataset identity to ``models/urgency-classifier-v1.0.0.json``.

Training is deterministic: one seed, one fold split, no sampling. Running the
command twice on the same data produces byte-identical output, which is what
lets the test suite check that the committed artefact really came from this
code.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.features import FEATURE_NAMES
from app.prioritisation import UrgencyLevel
from app.symptom_groups import vocabulary
from evaluation import triage_datasets as datasets
from evaluation.triage_datasets import DatasetIdentity, TrainingEncounter

ARTEFACT_PATH = datasets.ARTEFACT_PATH
SCHEMA_VERSION = 1
ARTEFACT_VERSION = "urgency-classifier-v1.0.0"
MODEL_FAMILY = "multinomial logistic regression (L2 penalty, class_weight=balanced)"
CLASS_ORDER: tuple[str, ...] = (
    UrgencyLevel.high.value,
    UrgencyLevel.medium.value,
    UrgencyLevel.low.value,
)
DEFAULT_FOLDS = 5
DEFAULT_SEED = 20261103


def build_artefact(
    records: Sequence[TrainingEncounter],
    *,
    datasets: Sequence[DatasetIdentity],
    folds: int = DEFAULT_FOLDS,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Train on ``records`` and return the self-describing artefact."""
    if not records:
        raise ValueError("no training records")
    if folds < 2:
        raise ValueError("cross-validation needs at least two folds")

    matrix = np.array([record.inputs.vector() for record in records], dtype=float)
    labels = np.array(
        [record.urgency_level.value for record in records], dtype=object
    )
    sources = np.array([record.source_id for record in records], dtype=object)

    present = set(labels)
    if len(present) < 2:
        raise ValueError("training data must cover at least two Urgency Levels")
    for level in present:
        if int((labels == level).sum()) < folds:
            raise ValueError(
                f"{level} has fewer than {folds} Encounters; reduce --folds"
            )

    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    estimator = _estimator()
    predictions = cross_val_predict(estimator, matrix, labels, cv=splitter)

    fitted = _estimator().fit(matrix, labels)
    scaler: StandardScaler = fitted.named_steps["standardscaler"]
    regression: LogisticRegression = fitted.named_steps["logisticregression"]
    order = [list(regression.classes_).index(name) for name in CLASS_ORDER]

    counts = Counter(labels.tolist())
    source_counts = Counter(sources.tolist())
    constant_features = [
        name
        for name, deviation in zip(FEATURE_NAMES, np.std(matrix, axis=0))
        if np.isclose(float(deviation), 0.0)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "artefact_version": ARTEFACT_VERSION,
        "model_family": MODEL_FAMILY,
        "vocabulary_version": vocabulary().version,
        "feature_names": list(FEATURE_NAMES),
        "classes": list(CLASS_ORDER),
        "scaler": {
            "mean": [_round(value) for value in scaler.mean_],
            "scale": [_round(value) for value in scaler.scale_],
        },
        "coef": [
            [_round(value) for value in regression.coef_[index]]
            for index in order
        ],
        "intercept": [
            _round(regression.intercept_[index]) for index in order
        ],
        "training": {
            "datasets": [identity.as_dict() for identity in datasets],
            "encounter_count": len(records),
            "label_counts": {
                name: counts.get(name, 0) for name in CLASS_ORDER
            },
            "source_counts": {
                str(name): int(count)
                for name, count in sorted(source_counts.items())
            },
            "folds": folds,
            "seed": seed,
            "constant_features": constant_features,
            "limitations": datasets_limitations(),
        },
        "cross_validation": _scores(
            labels, predictions, sources, folds=folds
        ),
    }


def write_artefact(
    artefact: dict[str, Any], path: Path = ARTEFACT_PATH
) -> Path:
    """Write the artefact as stable, sorted JSON and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artefact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _estimator():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=5000,
            class_weight="balanced",
            solver="lbfgs",
            random_state=DEFAULT_SEED,
        ),
    )


def _scores(
    labels: np.ndarray,
    predictions: np.ndarray,
    sources: np.ndarray,
    *,
    folds: int,
) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=CLASS_ORDER, zero_division=0
    )
    per_source = {}
    for name in sorted(set(sources.tolist())):
        mask = sources == name
        per_source[str(name)] = {
            "encounter_count": int(mask.sum()),
            "accuracy": _round(accuracy_score(labels[mask], predictions[mask])),
        }

    majority = max(Counter(labels.tolist()).values()) / len(labels)

    return {
        "method": (
            f"stratified {folds}-fold cross-validation; the standardiser is fit "
            "inside each fold"
        ),
        "folds": folds,
        "accuracy": _round(accuracy_score(labels, predictions)),
        "macro_f1": _round(f1_score(labels, predictions, average="macro", labels=CLASS_ORDER)),
        "majority_baseline_accuracy": _round(majority),
        "confusion_matrix": [
            [int(value) for value in row]
            for row in confusion_matrix(labels, predictions, labels=CLASS_ORDER)
        ],
        "per_class": {
            name: {
                "precision": _round(precision[index]),
                "recall": _round(recall[index]),
                "f1": _round(f1[index]),
                "support": int(support[index]),
            }
            for index, name in enumerate(CLASS_ORDER)
        },
        "per_source": per_source,
    }


def datasets_limitations() -> list[str]:
    return [str(note) for note in datasets.provenance().get("limitations", [])]


def _round(value: float) -> float:
    return round(float(value), 12)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train the Urgency classifier from the published datasets."
    )
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=ARTEFACT_PATH)
    parser.add_argument("--data-dir", type=Path, default=datasets.DATA_DIR)
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="download and verify the datasets, then stop",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="fail if the datasets are not already cached",
    )
    args = parser.parse_args(argv)

    if args.fetch_only:
        for path in datasets.fetch(args.data_dir):
            print(f"cached {path}")
        return 0
    if not datasets.cached_files_exist(args.data_dir) and not args.no_fetch:
        datasets.fetch(args.data_dir)

    records = datasets.load_training_records(args.data_dir)
    artefact = build_artefact(
        records,
        datasets=datasets.dataset_identities(),
        folds=args.folds,
        seed=args.seed,
    )
    path = write_artefact(artefact, args.out)

    scores = artefact["cross_validation"]
    print(f"wrote {path}")
    print(
        f"{artefact['training']['encounter_count']} Encounters "
        f"({artefact['training']['source_counts']})"
    )
    print(
        f"{scores['folds']}-fold accuracy {scores['accuracy']:.3f} "
        f"(majority baseline {scores['majority_baseline_accuracy']:.3f}), "
        f"macro F1 {scores['macro_f1']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
