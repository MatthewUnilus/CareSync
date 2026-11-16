"""Loading and evaluating a trained Urgency classifier.

The artefact is a small, readable JSON file: standardisation constants, one
coefficient row per Urgency Level, and the evidence the training step produced
(dataset identity, vocabulary version, cross-validated scores). Keeping it as
numbers rather than a pickled estimator means inference needs no model library,
cannot drift with a library upgrade, and can be read in a code review.

The model family written by the training step is multinomial logistic
regression. Inference is a softmax over linear scores: pure, deterministic and
fast enough that no warm-up is required (a cold load is a few milliseconds).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.features import FEATURE_NAMES
from app.prioritisation import UrgencyLevel

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ARTEFACT_PATH = BACKEND_ROOT / "models" / "urgency-classifier-v1.1.0.json"
ARTEFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ClassifierModel:
    """A trained linear classifier plus the record of how it was produced."""

    feature_names: tuple[str, ...]
    classes: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coef: tuple[tuple[float, ...], ...]
    intercept: tuple[float, ...]
    vocabulary_version: str
    metadata: Mapping[str, Any]

    def scores(self, vector: Sequence[float]) -> tuple[float, ...]:
        """Return one linear score per class, in :attr:`classes` order."""
        if len(vector) != len(self.feature_names):
            raise ValueError(
                f"expected {len(self.feature_names)} features, got {len(vector)}"
            )
        standardised = tuple(
            (float(value) - mean) / scale
            for value, mean, scale in zip(vector, self.mean, self.scale)
        )
        return tuple(
            intercept + sum(
                weight * value for weight, value in zip(row, standardised)
            )
            for row, intercept in zip(self.coef, self.intercept)
        )

    def probabilities(self, vector: Sequence[float]) -> dict[str, float]:
        """Return a normalised probability for each Urgency Level name."""
        scores = self.scores(vector)
        largest = max(scores)
        weights = [math.exp(score - largest) for score in scores]
        total = sum(weights)
        return {
            name: weight / total
            for name, weight in zip(self.classes, weights)
        }

    def predict(self, vector: Sequence[float]) -> UrgencyLevel:
        """Return the single most probable Urgency Level.

        Ties break towards the earlier class in :attr:`classes`, which is
        High-first, so an ambiguous case errs towards being seen sooner.
        """
        probabilities = self.probabilities(vector)
        return UrgencyLevel(max(self.classes, key=probabilities.__getitem__))


def load_model(path: Path = ARTEFACT_PATH) -> ClassifierModel:
    """Load and validate an artefact written by the training step."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != ARTEFACT_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schema version {data.get('schema_version')!r}, "
            f"expected {ARTEFACT_SCHEMA_VERSION}"
        )

    feature_names = tuple(str(name) for name in data["feature_names"])
    classes = tuple(str(name) for name in data["classes"])
    coef = tuple(tuple(float(value) for value in row) for row in data["coef"])
    intercept = tuple(float(value) for value in data["intercept"])
    mean = tuple(float(value) for value in data["scaler"]["mean"])
    scale = tuple(float(value) for value in data["scaler"]["scale"])

    if not feature_names or not classes:
        raise ValueError(f"{path} declares no features or no classes")
    if len(coef) != len(classes) or len(intercept) != len(classes):
        raise ValueError(f"{path} has coefficient rows that do not match its classes")
    if any(len(row) != len(feature_names) for row in coef):
        raise ValueError(f"{path} has a coefficient row of the wrong width")
    if len(mean) != len(feature_names) or len(scale) != len(feature_names):
        raise ValueError(f"{path} has standardisation constants of the wrong width")
    if any(value == 0 for value in scale):
        raise ValueError(f"{path} has a zero scale; it cannot be applied")

    return ClassifierModel(
        feature_names=feature_names,
        classes=classes,
        mean=mean,
        scale=scale,
        coef=coef,
        intercept=intercept,
        vocabulary_version=str(data["vocabulary_version"]),
        metadata=data,
    )


@lru_cache(maxsize=1)
def load_default_model() -> ClassifierModel:
    """Load the shipped artefact once per process.

    The cache is the warm-up: the first call reads a small JSON file, every
    later call reuses it, and no startup hook is needed to stay inside the
    three-second budget.
    """
    model = load_model(ARTEFACT_PATH)
    if model.feature_names != FEATURE_NAMES:
        raise RuntimeError(
            "the shipped classifier was trained on a different feature vector; "
            "retrain it with `uv run python -m evaluation.train_classifier`"
        )
    return model
