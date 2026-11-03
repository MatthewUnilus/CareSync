"""The Accuracy Evaluation Report: the project's central evidence.

What this module does
---------------------
It presents independent ground truth beside the engine's decisions. There are
two run sources, and the seam between them is deliberate:

* the **offline harness artefact**, the normal source. It is database-free and
  carries its own confusion matrix, per-class precision/recall, false-priority
  rates, majority baseline, macro F1 and sample size. Those figures are the
  reproducible evidence and are copied in without consulting the database.
* the **legacy per-case manifest**, for live assessment-derived runs. Each case
  names a stored Triage Assessment; the immutable ``machine_recommendation`` is
  read from that row. An Override moves ``final_decision`` and appends an
  Override row, but it cannot move a matrix cell, a precision or recall figure,
  or either false-priority rate. The ``final_decision`` column is never read.

Ground truth is not inferable from the engine, so it cannot live on the
Assessment. It lives in the run artefact under an explicit ``ground_truth``
object naming its source and version; the UI displays that source. No labels
means no score: :func:`build_report` returns an explicit empty or refused state
rather than a zero that could be mistaken for a measurement.

Metrics
-------
The confusion matrix has one row per Machine Recommendation and one column per
ground-truth Urgency Level, in Queue order (High, Medium, Low).

Per level, with ``m`` the machine level and ``g`` the ground-truth level:

* **Precision** = ``matrix[m][m] / sum over g of matrix[m][g]`` — of the cases
  the engine called ``m``, how many really were ``m``. ``None`` when the engine
  never predicted ``m``.
* **Recall** = ``matrix[m][m] / sum over m of matrix[m][g]`` — of the cases
  that really were ``m``, how many the engine called ``m``. ``None`` when no
  case had ground truth ``m``.

The two false-priority rates are one-vs-rest false-positive rates, kept apart
because they are different clinical risks:

* **False High-Priority** = recommended High when the truth was not High
  (over-triage), divided by every case whose truth was not High.
* **False Low-Priority** = recommended Low when the truth was not Low
  (under-triage, including a missed High), divided by every case whose truth
  was not Low.

An aggregate accuracy cannot show either risk, and averaging them together
would hide the one that matters most.

Override figures are computed over **all** stored Assessments, because they
describe where staff disagreed with the engine, not the labelled sample. The
Override rate is the number of Assessments carrying at least one Override
divided by all Assessments. The reason distribution counts Override rows by
their fixed reason, so the six glossary reasons always appear, including zeroes.

Fallback runs
-------------
Both sources record the fallback mode explicitly: ``fallback-disabled`` or
``fallback-enabled``. It is never inferred from Assessment rows. For a legacy
manifest a disabled run is rejected if any case claims the fallback ran; for a
harness run the artefact's own ``fallback`` field is used. Coverage is its own
statistic and is only defined for an enabled run:

* **Coverage** = scored cases whose recommendation came from the fallback path /
  all scored cases.
* **Unclassified rate** = scored cases the fallback could not classify / all
  scored cases.

Coverage never enters the accuracy figure. The cross-validated run is primary
for a harness artefact; the fallback-enabled pipeline sits beside it.

Run sources and precedence
--------------------------
:func:`load_configured_bundle` applies this order:

1. ``TRIAGEASSIST_ACCURACY_RUN_PATH`` if set, detected by document shape;
2. ``evaluation/results/accuracy-evaluation.json`` (legacy per-case manifest);
3. ``evaluation/results/accuracy-evaluation-<version>.json`` (harness).

The versioned name comes from :mod:`evaluation.artefact`, so the producer and
consumer share one version constant.

Legacy manifest contract
------------------------
See ``docs/accuracy-evaluation-report.md``. In outline::

    {
      "schema_version": 1,
      "runs": [
        {
          "run_id": "...",
          "mode": "fallback-disabled" | "fallback-enabled",
          "dataset": "...",
          "engine_artefact": "...",
          "ground_truth": {"name": "...", "version": "...",
                           "citation": "...", "document": "..."},
          "cases": [
            {"assessment_id": 12, "ground_truth": "High",
             "machine_recommendation": "Medium",
             "fallback_used": false, "unclassified": false}
          ]
        }
      ]
    }

``machine_recommendation`` on a case is optional and only a cross-check: when
present and different from the stored row, the stored row wins and the id is
reported as inconsistent. A reference to an Assessment that is not stored is
reported as missing rather than silently dropped.

Harness artefact contract
-------------------------
Run-level keys are read from the artefact the harness writes; see
``evaluation/results/README.md``. Its confusion matrix is ground-truth rows by
Machine Recommendation columns, so :func:`_parse_harness_matrix` transposes it
once. Required field sets are exported as :data:`HARNESS_RUN_FIELDS` and
:data:`HARNESS_METRIC_FIELDS` and pinned by a test, so a new producer field
fails the suite until the consumer deliberately reads it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Override, TriageAssessment
from app.override_reasons import OVERRIDE_REASONS, OverrideReason
from app.prioritisation import URGENCY_RANK, UrgencyLevel
from evaluation.artefact import LEGACY_MANIFEST_PATH, RESULTS_PATH

MANIFEST_SCHEMA_VERSION = 1

#: Run keys the consumer reads from a harness artefact. Pinned by a test: a new
#: key in the harness schema fails that test until the consumer's contract is
#: deliberately widened.
HARNESS_RUN_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "mode",
        "fallback",
        "dataset",
        "ground_truth",
        "engine_artefact",
        "metrics",
    }
)

#: Keys the harness currently emits beside the required run fields. They are
#: optional to the consumer, but a new key still has to be acknowledged here.
HARNESS_OPTIONAL_RUN_FIELDS: frozenset[str] = frozenset(
    {
        "coverage",
        "description",
        "matches_recorded_artefact",
        "predictions",
        "procedure",
        "safety_layer",
    }
)

HARNESS_METRIC_FIELDS: frozenset[str] = frozenset(
    {
        "accuracy",
        "confusion_matrix",
        "encounter_count",
        "false_high_priority",
        "false_low_priority",
        "macro_f1",
        "majority_baseline",
        "per_class",
    }
)

#: Queue order, used for every row, column and list in the report.
LEVELS: tuple[UrgencyLevel, ...] = tuple(
    sorted(UrgencyLevel, key=lambda level: URGENCY_RANK[level])
)


class AccuracyRunError(ValueError):
    """A run manifest that cannot be trusted to mean what it says."""


class FallbackMode(str, Enum):
    """Whether the fallback layer was part of the run. Explicit, never inferred."""

    disabled = "fallback-disabled"
    enabled = "fallback-enabled"


class RunSource(str, Enum):
    """Where a run's figures came from.

    ``assessments`` is the live form: a labelled case names a stored
    Assessment, and the Machine Recommendation is read from that row.
    ``harness`` is the offline form: the reproducible artefact carries its own
    matrix, per-class figures and false-priority rates, and touches no database.
    """

    assessments = "assessments"
    harness = "harness"


class _InvalidManifest(ValueError):
    pass


@dataclass(frozen=True)
class GroundTruthSource:
    """Where the labels came from, so the UI can name the standard."""

    name: str
    version: str
    citation: str
    document: str | None = None


@dataclass(frozen=True)
class RunCase:
    """One labelled case, pointing at the stored Assessment it scored."""

    assessment_id: int
    ground_truth: UrgencyLevel
    machine_recommendation: UrgencyLevel | None = None
    fallback_used: bool = False
    unclassified: bool = False


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    mode: FallbackMode
    ground_truth: GroundTruthSource
    cases: tuple[RunCase, ...]
    dataset: str | None = None
    engine_artefact: str | None = None


@dataclass(frozen=True)
class HarnessRun:
    """One run read directly from the offline harness artefact.

    It carries no Assessment ids by design: the harness is database-free, and
    its confusion matrix and per-class figures are the reproducible evidence.
    """

    run_id: str
    run_mode: str
    mode: FallbackMode
    ground_truth: GroundTruthSource
    dataset: str
    engine_artefact: str
    total: int
    correct: int
    accuracy: float
    macro_f1: float
    majority_baseline: "MajorityBaseline"
    confusion_matrix: tuple["ConfusionCell", ...]
    levels: tuple["LevelMetrics", ...]
    false_high_priority: "PriorityErrorRate"
    false_low_priority: "PriorityErrorRate"
    fallback: "FallbackCoverage"
    predictions: int


@dataclass(frozen=True)
class RunBundle:
    schema_version: int
    runs: tuple[EvaluationRun | HarnessRun, ...]


@dataclass(frozen=True)
class ConfusionCell:
    machine_recommendation: UrgencyLevel
    ground_truth: UrgencyLevel
    assessments: int


@dataclass(frozen=True)
class LevelMetrics:
    urgency_level: UrgencyLevel
    ground_truth_count: int
    predicted_count: int
    correct: int
    precision: float | None
    recall: float | None


@dataclass(frozen=True)
class PriorityErrorRate:
    count: int
    denominator: int
    rate: float | None


@dataclass(frozen=True)
class MajorityBaseline:
    """Always predicting the commonest ground-truth level.

    ``model_minus_baseline`` is negative when the model is worse than that
    trivial rule. The report shows the sign, not just the accuracy.
    """

    majority_class: UrgencyLevel
    accuracy: float
    model_minus_baseline: float
    beats_baseline: bool


@dataclass(frozen=True)
class RunSample:
    labelled_cases: int
    resolved_assessments: int
    missing_assessments: tuple[int, ...]
    inconsistent_recommendations: tuple[int, ...]


@dataclass(frozen=True)
class FallbackCoverage:
    enabled: bool
    fallback_used: int
    unclassified: int
    coverage: float | None
    unclassified_rate: float | None


@dataclass(frozen=True)
class RunReport:
    run_id: str
    run_mode: str
    source: RunSource
    primary: bool
    mode: FallbackMode
    dataset: str | None
    engine_artefact: str | None
    ground_truth: GroundTruthSource
    sample: RunSample
    confusion_matrix: tuple[ConfusionCell, ...]
    levels: tuple[LevelMetrics, ...]
    total: int
    correct: int
    accuracy: float | None
    macro_f1: float | None
    majority_baseline: MajorityBaseline | None
    false_high_priority: PriorityErrorRate
    false_low_priority: PriorityErrorRate
    fallback: FallbackCoverage


@dataclass(frozen=True)
class OverrideReasonCount:
    reason: OverrideReason
    overrides: int
    share: float | None


@dataclass(frozen=True)
class OverrideMetrics:
    assessments: int
    overridden_assessments: int
    overrides: int
    rate: float | None
    reasons: tuple[OverrideReasonCount, ...]


@dataclass(frozen=True)
class AccuracyEvaluationReport:
    available: bool
    empty_reason: str | None
    runs: tuple[RunReport, ...]
    overrides: OverrideMetrics


# ---------------------------------------------------------------------------
# Reading the run manifest
# ---------------------------------------------------------------------------


def load_configured_bundle(
    configured_path: str | Path | None,
) -> RunBundle | None:
    """Read the run source under the documented precedence.

    1. An explicit path from ``TRIAGEASSIST_ACCURACY_RUN_PATH``, whose format
       is detected from its shape.
    2. A legacy per-case manifest at ``accuracy-evaluation.json`` if present,
       so live, assessment-derived runs keep working.
    3. The versioned offline harness artefact named by
       ``evaluation.artefact.RESULTS_PATH``.

    A missing file at every step is the normal "no labelled run" state.
    """
    if configured_path is not None and str(configured_path).strip():
        return load_run_bundle(Path(configured_path))
    if LEGACY_MANIFEST_PATH.is_file():
        return load_run_bundle(LEGACY_MANIFEST_PATH)
    return load_run_bundle(RESULTS_PATH)


def load_run_bundle(path: Path | str | None) -> RunBundle | None:
    """Read a labelled run manifest or harness artefact, or return ``None``.

    Both document shapes are accepted: the old per-case manifest (run keys
    ``run_id`` and ``cases``) and the offline harness artefact (run keys ``id``
    and ``metrics``). The shape is detected from the document itself, so an
    explicit override can point at either.

    A missing file is the normal "no labelled run yet" state and is not an
    error. A file that exists but cannot be trusted raises
    :class:`AccuracyRunError`, because silently showing a partial run would be
    worse than showing nothing.
    """
    if path is None:
        return None
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AccuracyRunError(
            f"the evaluation run manifest at {manifest_path} could not be read: "
            f"{error}"
        ) from error
    try:
        return _parse_bundle(raw)
    except _InvalidManifest as error:
        raise AccuracyRunError(
            f"the evaluation run manifest at {manifest_path} is invalid: {error}"
        ) from error


def _parse_bundle(raw: Any) -> RunBundle:
    if not isinstance(raw, dict):
        raise _InvalidManifest("the document must be an object")
    schema_version = raw.get("schema_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise _InvalidManifest(
            f"schema_version must be {MANIFEST_SCHEMA_VERSION}, "
            f"got {schema_version!r}"
        )
    raw_runs = raw.get("runs")
    if not isinstance(raw_runs, list):
        raise _InvalidManifest("runs must be a list")

    if _is_harness_artefact(raw):
        return _parse_harness_bundle(raw, raw_runs)
    return _parse_assessment_bundle(raw_runs)


def _is_harness_artefact(raw: dict[str, Any]) -> bool:
    """Tell the harness artefact from the legacy per-case manifest.

    The producer's document names a ``harness_version``; each of its runs has
    ``id``/``metrics`` and no ``cases``. Either signal is enough, so a trimmed
    fixture without the header is still recognised by its run shape.
    """
    if "harness_version" in raw:
        return True
    raw_runs = raw.get("runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        return False
    first = raw_runs[0]
    return (
        isinstance(first, dict)
        and "metrics" in first
        and "cases" not in first
    )


def _parse_assessment_bundle(raw_runs: list[Any]) -> RunBundle:
    runs: list[EvaluationRun] = []
    seen_ids: set[str] = set()
    for index, raw_run in enumerate(raw_runs):
        run = _parse_run(raw_run, index)
        if run.run_id in seen_ids:
            raise _InvalidManifest(f"duplicate run_id {run.run_id!r}")
        seen_ids.add(run.run_id)
        runs.append(run)

    # The fallback-disabled run is the reproducible primary; show it first.
    runs.sort(key=lambda run: 0 if run.mode is FallbackMode.disabled else 1)
    return RunBundle(schema_version=MANIFEST_SCHEMA_VERSION, runs=tuple(runs))


# ---------------------------------------------------------------------------
# Reading the offline harness artefact
# ---------------------------------------------------------------------------


def _parse_harness_bundle(
    raw: dict[str, Any], raw_runs: list[Any]
) -> RunBundle:
    runs: list[HarnessRun] = []
    seen_ids: set[str] = set()
    for index, raw_run in enumerate(raw_runs):
        run = _parse_harness_run(raw_run, index)
        if run.run_id in seen_ids:
            raise _InvalidManifest(f"duplicate run id {run.run_id!r}")
        seen_ids.add(run.run_id)
        runs.append(run)

    # Cross-validation is the flagship, reproducible score; then the
    # fallback-disabled pipeline; then the fallback-enabled variant. Everything
    # else keeps its artefact order.
    rank = {
        "cross_validated": 0,
        "pipeline": 1,
        "pipeline_fallback_enabled": 2,
    }
    runs.sort(
        key=lambda run: (
            rank.get(run.run_id, 3),
            0 if run.mode is FallbackMode.disabled else 1,
        )
    )
    return RunBundle(schema_version=MANIFEST_SCHEMA_VERSION, runs=tuple(runs))


def _parse_harness_run(raw: Any, index: int) -> HarnessRun:
    where = f"runs[{index}]"
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")

    run_id = _required_text(raw, "id", where)
    run_mode = _required_text(raw, "mode", where)

    try:
        mode = FallbackMode(f"fallback-{_required_text(raw, 'fallback', where)}")
    except _InvalidManifest:
        raise
    except (TypeError, ValueError) as error:
        raise _InvalidManifest(
            f"{where}.fallback must be 'disabled' or 'enabled'"
        ) from error

    raw_dataset = raw.get("dataset")
    if not isinstance(raw_dataset, dict):
        raise _InvalidManifest(f"{where}.dataset must be an object")
    dataset = _harness_dataset_label(raw_dataset, f"{where}.dataset")

    raw_source = raw.get("ground_truth")
    if not isinstance(raw_source, dict):
        raise _InvalidManifest(f"{where}.ground_truth must be an object")
    source = _harness_ground_truth(
        raw_source, raw_dataset, f"{where}.ground_truth"
    )

    raw_engine = raw.get("engine_artefact")
    if not isinstance(raw_engine, dict):
        raise _InvalidManifest(f"{where}.engine_artefact must be an object")
    engine_artefact = _required_text(
        raw_engine, "artefact_version", f"{where}.engine_artefact"
    )

    raw_metrics = raw.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise _InvalidManifest(f"{where}.metrics must be an object")
    metrics = _parse_harness_metrics(raw_metrics, f"{where}.metrics")

    raw_coverage = raw.get("coverage")
    if mode is FallbackMode.enabled:
        if not isinstance(raw_coverage, dict):
            raise _InvalidManifest(
                f"{where}.coverage is required for a fallback-enabled run"
            )
        coverage = _parse_harness_coverage(
            raw_coverage, metrics["total"], f"{where}.coverage"
        )
    else:
        if raw_coverage is not None:
            raise _InvalidManifest(
                f"{where} is fallback-disabled but carries a coverage object"
            )
        coverage = FallbackCoverage(
            enabled=False,
            fallback_used=0,
            unclassified=0,
            coverage=None,
            unclassified_rate=None,
        )

    raw_predictions = raw.get("predictions")
    if raw_predictions is None:
        predictions = metrics["total"]
    else:
        if not isinstance(raw_predictions, list):
            raise _InvalidManifest(f"{where}.predictions must be a list")
        if len(raw_predictions) != metrics["total"]:
            raise _InvalidManifest(
                f"{where}.predictions has {len(raw_predictions)} entries but "
                f"metrics.encounter_count is {metrics['total']}"
            )
        predictions = len(raw_predictions)

    return HarnessRun(
        run_id=run_id,
        run_mode=run_mode,
        mode=mode,
        ground_truth=source,
        dataset=dataset,
        engine_artefact=engine_artefact,
        total=metrics["total"],
        correct=metrics["correct"],
        accuracy=metrics["accuracy"],
        macro_f1=metrics["macro_f1"],
        majority_baseline=metrics["majority_baseline"],
        confusion_matrix=metrics["confusion_matrix"],
        levels=metrics["levels"],
        false_high_priority=metrics["false_high_priority"],
        false_low_priority=metrics["false_low_priority"],
        fallback=coverage,
        predictions=predictions,
    )


def _parse_harness_metrics(
    raw: dict[str, Any], where: str
) -> dict[str, Any]:
    total = _required_int(raw, "encounter_count", where)
    if total <= 0:
        raise _InvalidManifest(f"{where}.encounter_count must be positive")
    accuracy = _required_rate(raw, "accuracy", where)
    macro_f1 = _required_rate(raw, "macro_f1", where)

    matrix, correct = _parse_harness_matrix(
        raw.get("confusion_matrix"), total, f"{where}.confusion_matrix"
    )

    raw_per_class = raw.get("per_class")
    if not isinstance(raw_per_class, dict):
        raise _InvalidManifest(f"{where}.per_class must be an object")
    levels = _parse_harness_levels(
        raw_per_class, matrix, correct, f"{where}.per_class"
    )

    return {
        "total": total,
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "majority_baseline": _parse_harness_baseline(
            raw.get("majority_baseline"), f"{where}.majority_baseline"
        ),
        "confusion_matrix": matrix,
        "correct": correct,
        "levels": levels,
        "false_high_priority": _parse_harness_rate(
            raw.get("false_high_priority"), f"{where}.false_high_priority"
        ),
        "false_low_priority": _parse_harness_rate(
            raw.get("false_low_priority"), f"{where}.false_low_priority"
        ),
    }


def _parse_harness_matrix(
    raw: Any, total: int, where: str
) -> tuple[tuple[ConfusionCell, ...], int]:
    """Transpose the harness's truth-by-prediction rows into report cells.

    The harness writes ``rows`` as ground truth with columns as Machine
    Recommendation; the report's cells are keyed ``(machine, truth)``. Keeping
    the transpose in one place is what stops the two schemas drifting silently.
    """
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")
    labels = raw.get("labels")
    rows = raw.get("rows")
    if not isinstance(labels, list) or not isinstance(rows, list):
        raise _InvalidManifest(f"{where}.labels and .rows must be lists")

    level_values = [level.value for level in LEVELS]
    if not all(isinstance(label, str) for label in labels):
        raise _InvalidManifest(f"{where}.labels must be strings")
    if sorted(labels) != sorted(level_values):
        raise _InvalidManifest(
            f"{where}.labels must be exactly {level_values}, got {labels!r}"
        )
    if len(rows) != len(labels):
        raise _InvalidManifest(
            f"{where}.rows must have one row per label"
        )

    counts: dict[tuple[UrgencyLevel, UrgencyLevel], int] = {}
    total_cells = 0
    for truth_position, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(labels):
            raise _InvalidManifest(
                f"{where}.rows[{truth_position}] must have one cell per label"
            )
        truth = UrgencyLevel(labels[truth_position])
        for machine_position, value in enumerate(row):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise _InvalidManifest(
                    f"{where}.rows[{truth_position}][{machine_position}] "
                    "must be a non-negative integer"
                )
            machine = UrgencyLevel(labels[machine_position])
            counts[(machine, truth)] = value
            total_cells += value

    if total_cells != total:
        raise _InvalidManifest(
            f"{where} sums to {total_cells} but encounter_count is {total}"
        )

    matrix = tuple(
        ConfusionCell(
            machine_recommendation=machine,
            ground_truth=truth,
            assessments=counts[(machine, truth)],
        )
        for machine in LEVELS
        for truth in LEVELS
    )
    correct = sum(counts[(level, level)] for level in LEVELS)
    return matrix, correct


def _parse_harness_levels(
    raw: dict[str, Any],
    matrix: tuple[ConfusionCell, ...],
    correct: int,
    where: str,
) -> tuple[LevelMetrics, ...]:
    predicted_totals = {
        level: sum(
            cell.assessments
            for cell in matrix
            if cell.machine_recommendation is level
        )
        for level in LEVELS
    }
    truth_totals = {
        level: sum(
            cell.assessments for cell in matrix if cell.ground_truth is level
        )
        for level in LEVELS
    }

    levels: list[LevelMetrics] = []
    for level in LEVELS:
        raw_level = raw.get(level.value)
        if not isinstance(raw_level, dict):
            raise _InvalidManifest(f"{where}.{level.value} must be an object")
        support = _required_int(raw_level, "support", f"{where}.{level.value}")
        if support != truth_totals[level]:
            raise _InvalidManifest(
                f"{where}.{level.value}.support is {support} but the matrix "
                f"has {truth_totals[level]} ground-truth cases"
            )
        levels.append(
            LevelMetrics(
                urgency_level=level,
                ground_truth_count=support,
                predicted_count=predicted_totals[level],
                correct=sum(
                    cell.assessments
                    for cell in matrix
                    if cell.machine_recommendation is level
                    and cell.ground_truth is level
                ),
                precision=_required_rate(
                    raw_level, "precision", f"{where}.{level.value}"
                ),
                recall=_required_rate(
                    raw_level, "recall", f"{where}.{level.value}"
                ),
            )
        )

    if sum(level.correct for level in levels) != correct:
        raise _InvalidManifest(
            f"{where} does not agree with the confusion matrix diagonal"
        )
    return tuple(levels)


def _parse_harness_baseline(raw: Any, where: str) -> MajorityBaseline:
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")
    return MajorityBaseline(
        majority_class=_level(raw.get("class"), f"{where}.class"),
        accuracy=_required_rate(raw, "accuracy", where),
        model_minus_baseline=_required_number(
            raw, "model_minus_baseline", where
        ),
        beats_baseline=_required_bool(raw, "beats_baseline", where),
    )


def _parse_harness_rate(raw: Any, where: str) -> PriorityErrorRate:
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")
    count = _required_int(raw, "count", where)
    denominator = _required_int(raw, "denominator", where)
    if count < 0 or denominator < 0 or count > denominator:
        raise _InvalidManifest(
            f"{where}.count must be between 0 and .denominator"
        )
    rate = raw.get("rate")
    return PriorityErrorRate(
        count=count,
        denominator=denominator,
        rate=None if rate is None else _number(rate, f"{where}.rate"),
    )


def _parse_harness_coverage(
    raw: dict[str, Any], total: int, where: str
) -> FallbackCoverage:
    fallback_used = _required_int(raw, "fallback_used", where)
    unclassified = _required_int(raw, "unclassified", where)
    if fallback_used > total or unclassified > fallback_used:
        raise _InvalidManifest(
            f"{where} cannot exceed its encounter count"
        )
    rate = _required_rate(raw, "rate", where)
    unclassified_rate = _required_rate(raw, "unclassified_rate", where)
    if abs(rate - (fallback_used / total)) > 1e-9:
        raise _InvalidManifest(
            f"{where}.rate does not match fallback_used / encounter_count"
        )
    if abs(unclassified_rate - (unclassified / total)) > 1e-9:
        raise _InvalidManifest(
            f"{where}.unclassified_rate does not match "
            "unclassified / encounter_count"
        )
    return FallbackCoverage(
        enabled=True,
        fallback_used=fallback_used,
        unclassified=unclassified,
        coverage=rate,
        unclassified_rate=unclassified_rate,
    )


def _harness_dataset_label(raw: dict[str, Any], where: str) -> str:
    kind = raw.get("kind")
    count = raw.get("encounter_count")
    count_text = f"{count} Encounters" if isinstance(count, int) else "Encounters"
    if kind == "published_triage_dataset":
        source_ids = raw.get("source_ids")
        name = (
            ", ".join(str(item) for item in source_ids)
            if isinstance(source_ids, list) and source_ids
            else "published triage dataset"
        )
        return f"{name} · {count_text}"
    if kind == "rubric_labelled_synthetic_corpus":
        path = raw.get("path") or "rubric-labelled synthetic corpus"
        version = raw.get("rubric_version")
        suffix = f" · {version}" if isinstance(version, str) and version else ""
        return f"{path}{suffix} · {count_text}"
    if isinstance(kind, str) and kind:
        return f"{kind} · {count_text}"
    raise _InvalidManifest(f"{where}.kind must be a non-empty string")


def _harness_ground_truth(
    raw: dict[str, Any], dataset: dict[str, Any], where: str
) -> GroundTruthSource:
    kind = raw.get("kind")
    if kind == "esi_v4_rubric":
        return GroundTruthSource(
            name="ESI v4 rubric",
            version=_required_text(raw, "rubric_version", where),
            citation=_required_text(raw, "rubric_citation", where),
            document=_optional_text(raw, "rubric_document", where),
        )
    if kind == "published_triage_level":
        sources = dataset.get("sources")
        citation = None
        source_id = None
        if isinstance(sources, list) and sources and isinstance(sources[0], dict):
            citation = sources[0].get("citation")
            source_id = sources[0].get("source_id")
        return GroundTruthSource(
            name="Published three-level triage category",
            version=(
                source_id
                if isinstance(source_id, str) and source_id
                else "published source"
            ),
            citation=(
                citation
                if isinstance(citation, str) and citation
                else _required_text(raw, "label_source", where)
            ),
            document=None,
        )
    if isinstance(kind, str) and kind:
        return GroundTruthSource(
            name=kind,
            version=_required_text(raw, "version", where),
            citation=_required_text(raw, "citation", where),
            document=_optional_text(raw, "document", where),
        )
    raise _InvalidManifest(f"{where}.kind must be a non-empty string")


def _parse_run(raw: Any, index: int) -> EvaluationRun:
    where = f"runs[{index}]"
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")

    run_id = raw.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise _InvalidManifest(f"{where}.run_id must be a non-empty string")

    raw_mode = raw.get("mode")
    try:
        mode = FallbackMode(raw_mode)
    except (TypeError, ValueError) as error:
        raise _InvalidManifest(
            f"{where}.mode must be 'fallback-disabled' or 'fallback-enabled'"
        ) from error

    raw_source = raw.get("ground_truth")
    if not isinstance(raw_source, dict):
        raise _InvalidManifest(f"{where}.ground_truth must be an object")
    source = GroundTruthSource(
        name=_required_text(raw_source, "name", f"{where}.ground_truth"),
        version=_required_text(raw_source, "version", f"{where}.ground_truth"),
        citation=_required_text(
            raw_source, "citation", f"{where}.ground_truth"
        ),
        document=_optional_text(raw_source, "document", f"{where}.ground_truth"),
    )

    dataset = _optional_text(raw, "dataset", where)
    engine_artefact = _optional_text(raw, "engine_artefact", where)

    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list):
        raise _InvalidManifest(f"{where}.cases must be a list")

    cases: list[RunCase] = []
    seen_assessments: set[int] = set()
    for case_index, raw_case in enumerate(raw_cases):
        case = _parse_case(raw_case, f"{where}.cases[{case_index}]")
        if case.assessment_id in seen_assessments:
            raise _InvalidManifest(
                f"{where} evaluates Assessment {case.assessment_id} twice"
            )
        seen_assessments.add(case.assessment_id)
        if mode is FallbackMode.disabled and case.fallback_used:
            raise _InvalidManifest(
                f"{where} is fallback-disabled but a case claims the fallback ran"
            )
        if mode is FallbackMode.disabled and case.unclassified:
            raise _InvalidManifest(
                f"{where} is fallback-disabled but a case claims an "
                "unclassified result"
            )
        if case.unclassified and not case.fallback_used:
            raise _InvalidManifest(
                f"{where} marks Assessment {case.assessment_id} unclassified "
                "without the fallback having run"
            )
        cases.append(case)

    return EvaluationRun(
        run_id=run_id,
        mode=mode,
        ground_truth=source,
        cases=tuple(cases),
        dataset=dataset,
        engine_artefact=engine_artefact,
    )


def _parse_case(raw: Any, where: str) -> RunCase:
    if not isinstance(raw, dict):
        raise _InvalidManifest(f"{where} must be an object")

    assessment_id = raw.get("assessment_id")
    if (
        not isinstance(assessment_id, int)
        or isinstance(assessment_id, bool)
        or assessment_id <= 0
    ):
        raise _InvalidManifest(f"{where}.assessment_id must be a positive integer")

    ground_truth = _level(raw.get("ground_truth"), f"{where}.ground_truth")
    machine = raw.get("machine_recommendation")
    machine_level = (
        None if machine is None else _level(machine, f"{where}.machine_recommendation")
    )
    fallback_used = _optional_bool(raw, "fallback_used", where)
    unclassified = _optional_bool(raw, "unclassified", where)

    return RunCase(
        assessment_id=assessment_id,
        ground_truth=ground_truth,
        machine_recommendation=machine_level,
        fallback_used=fallback_used,
        unclassified=unclassified,
    )


def _level(value: Any, where: str) -> UrgencyLevel:
    try:
        return UrgencyLevel(value)
    except (TypeError, ValueError) as error:
        raise _InvalidManifest(
            f"{where} must be one of High, Medium or Low"
        ) from error


def _required_text(raw: dict[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _InvalidManifest(f"{where}.{key} must be a non-empty string")
    return value


def _optional_text(raw: dict[str, Any], key: str, where: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _InvalidManifest(f"{where}.{key} must be a non-empty string or null")
    return value


def _optional_bool(raw: dict[str, Any], key: str, where: str) -> bool:
    value = raw.get(key, False)
    if not isinstance(value, bool):
        raise _InvalidManifest(f"{where}.{key} must be true or false")
    return value


def _number(value: Any, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _InvalidManifest(f"{where} must be a number")
    return float(value)


def _required_number(raw: dict[str, Any], key: str, where: str) -> float:
    return _number(raw.get(key), f"{where}.{key}")


def _required_rate(raw: dict[str, Any], key: str, where: str) -> float:
    value = _required_number(raw, key, where)
    if not 0.0 <= value <= 1.0:
        raise _InvalidManifest(f"{where}.{key} must be between 0 and 1")
    return value


def _required_int(raw: dict[str, Any], key: str, where: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _InvalidManifest(f"{where}.{key} must be a non-negative integer")
    return value


def _required_bool(raw: dict[str, Any], key: str, where: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise _InvalidManifest(f"{where}.{key} must be true or false")
    return value


# ---------------------------------------------------------------------------
# Computing the report
# ---------------------------------------------------------------------------


def build_report(
    session: Session, bundle: RunBundle | None
) -> AccuracyEvaluationReport:
    """Compute the Accuracy Evaluation Report from stored rows and one bundle.

    Assessment-derived runs are scored against the immutable stored rows.
    Harness runs are copied from the artefact as-is: their matrix, per-class
    figures and false-priority rates are reproducible evidence and explicitly
    do not depend on database state. Override figures always come from stored
    Assessments in both cases.
    """
    overrides = override_metrics(session)

    if bundle is None or not bundle.runs:
        return AccuracyEvaluationReport(
            available=False,
            empty_reason=(
                "No evaluation run with ground-truth labels is available. "
                "Accuracy figures are withheld rather than shown as zero."
            ),
            runs=(),
            overrides=overrides,
        )

    evaluated = tuple(_run_report(session, run) for run in bundle.runs)
    available = tuple(run for run in evaluated if run.total > 0)
    if available:
        # The first available run is primary: cross-validated for a harness
        # artefact, the fallback-disabled run for a legacy manifest.
        available = tuple(
            _with_primary(run, position == 0)
            for position, run in enumerate(available)
        )
        return AccuracyEvaluationReport(
            available=True,
            empty_reason=None,
            runs=available,
            overrides=overrides,
        )

    if all(
        isinstance(run, EvaluationRun) and not run.cases for run in bundle.runs
    ):
        reason = (
            "The evaluation run manifest contains no labelled cases. Accuracy "
            "figures are withheld rather than shown as zero."
        )
    elif any(isinstance(run, HarnessRun) for run in bundle.runs):
        reason = (
            "The evaluation artefact contains no scorable run. Accuracy figures "
            "are withheld rather than shown as zero."
        )
    else:
        reason = (
            "The evaluation run references no stored Assessments, so no figure "
            "can be computed. Accuracy figures are withheld rather than shown "
            "as zero."
        )
    return AccuracyEvaluationReport(
        available=False,
        empty_reason=reason,
        runs=(),
        overrides=overrides,
    )


def refused_report(session: Session, reason: str) -> AccuracyEvaluationReport:
    """An explicit refusal state for a malformed or unreadable artefact.

    The Override figures are still honest facts about stored rows, so they stay
    beside the reason. No accuracy figure is invented.
    """
    return AccuracyEvaluationReport(
        available=False,
        empty_reason=reason,
        runs=(),
        overrides=override_metrics(session),
    )


def _with_primary(run: RunReport, primary: bool) -> RunReport:
    if run.primary is primary:
        return run
    return replace(run, primary=primary)


def _run_report(
    session: Session, run: EvaluationRun | HarnessRun
) -> RunReport:
    if isinstance(run, HarnessRun):
        return _harness_report(run)
    return evaluate_run(session, run)


def _harness_report(run: HarnessRun) -> RunReport:
    """Copy one harness run into the report without touching the database."""
    return RunReport(
        run_id=run.run_id,
        run_mode=run.run_mode,
        source=RunSource.harness,
        primary=False,
        mode=run.mode,
        dataset=run.dataset,
        engine_artefact=run.engine_artefact,
        ground_truth=run.ground_truth,
        sample=RunSample(
            labelled_cases=run.predictions,
            resolved_assessments=run.predictions,
            missing_assessments=(),
            inconsistent_recommendations=(),
        ),
        confusion_matrix=run.confusion_matrix,
        levels=run.levels,
        total=run.total,
        correct=run.correct,
        accuracy=run.accuracy,
        macro_f1=run.macro_f1,
        majority_baseline=run.majority_baseline,
        false_high_priority=run.false_high_priority,
        false_low_priority=run.false_low_priority,
        fallback=run.fallback,
    )


def evaluate_run(session: Session, run: EvaluationRun) -> RunReport:
    """Score one labelled run against the stored, immutable recommendations."""
    assessment_ids = [case.assessment_id for case in run.cases]
    stored = {
        assessment.id: assessment
        for assessment in session.scalars(
            select(TriageAssessment).where(
                TriageAssessment.id.in_(assessment_ids)
            )
        ).all()
    }

    matrix = {
        machine: {truth: 0 for truth in LEVELS} for machine in LEVELS
    }
    missing: list[int] = []
    inconsistent: list[int] = []
    resolved: list[RunCase] = []

    for case in run.cases:
        assessment = stored.get(case.assessment_id)
        if assessment is None:
            missing.append(case.assessment_id)
            continue
        machine_level = UrgencyLevel(assessment.machine_recommendation)
        if (
            case.machine_recommendation is not None
            and case.machine_recommendation is not machine_level
        ):
            inconsistent.append(case.assessment_id)
        matrix[machine_level][case.ground_truth] += 1
        resolved.append(case)

    total = len(resolved)
    correct = sum(matrix[level][level] for level in LEVELS)
    accuracy = (correct / total) if total else None

    truth_totals = {
        level: sum(matrix[machine][level] for machine in LEVELS)
        for level in LEVELS
    }
    predicted_totals = {
        level: sum(matrix[level].values()) for level in LEVELS
    }

    levels = tuple(
        LevelMetrics(
            urgency_level=level,
            ground_truth_count=truth_totals[level],
            predicted_count=predicted_totals[level],
            correct=matrix[level][level],
            precision=(
                matrix[level][level] / predicted_totals[level]
                if predicted_totals[level]
                else None
            ),
            recall=(
                matrix[level][level] / truth_totals[level]
                if truth_totals[level]
                else None
            ),
        )
        for level in LEVELS
    )

    confusion_matrix = tuple(
        ConfusionCell(machine, truth, matrix[machine][truth])
        for machine in LEVELS
        for truth in LEVELS
    )

    non_high = total - truth_totals[UrgencyLevel.high]
    non_low = total - truth_totals[UrgencyLevel.low]
    false_high_count = sum(
        matrix[UrgencyLevel.high][truth]
        for truth in LEVELS
        if truth is not UrgencyLevel.high
    )
    false_low_count = sum(
        matrix[UrgencyLevel.low][truth]
        for truth in LEVELS
        if truth is not UrgencyLevel.low
    )

    fallback = _fallback_coverage(run, resolved)

    majority_baseline = None
    if total:
        majority_class = max(LEVELS, key=lambda level: truth_totals[level])
        majority_accuracy = truth_totals[majority_class] / total
        model_accuracy = correct / total
        majority_baseline = MajorityBaseline(
            majority_class=majority_class,
            accuracy=majority_accuracy,
            model_minus_baseline=model_accuracy - majority_accuracy,
            beats_baseline=model_accuracy > majority_accuracy,
        )

    return RunReport(
        run_id=run.run_id,
        run_mode="assessment",
        source=RunSource.assessments,
        primary=False,
        mode=run.mode,
        dataset=run.dataset,
        engine_artefact=run.engine_artefact,
        ground_truth=run.ground_truth,
        sample=RunSample(
            labelled_cases=len(run.cases),
            resolved_assessments=total,
            missing_assessments=tuple(missing),
            inconsistent_recommendations=tuple(inconsistent),
        ),
        confusion_matrix=confusion_matrix,
        levels=levels,
        total=total,
        correct=correct,
        accuracy=accuracy,
        macro_f1=None,
        majority_baseline=majority_baseline,
        false_high_priority=PriorityErrorRate(
            count=false_high_count,
            denominator=non_high,
            rate=(false_high_count / non_high) if non_high else None,
        ),
        false_low_priority=PriorityErrorRate(
            count=false_low_count,
            denominator=non_low,
            rate=(false_low_count / non_low) if non_low else None,
        ),
        fallback=fallback,
    )


def _fallback_coverage(
    run: EvaluationRun, resolved: list[RunCase]
) -> FallbackCoverage:
    enabled = run.mode is FallbackMode.enabled
    fallback_used = sum(1 for case in resolved if case.fallback_used)
    unclassified = sum(1 for case in resolved if case.unclassified)
    total = len(resolved)
    return FallbackCoverage(
        enabled=enabled,
        fallback_used=fallback_used,
        unclassified=unclassified,
        # Coverage is undefined when the fallback was not part of the run,
        # rather than a zero that reads like "the fallback never ran".
        coverage=(fallback_used / total) if enabled and total else None,
        unclassified_rate=(unclassified / total) if enabled and total else None,
    )


def override_metrics(session: Session) -> OverrideMetrics:
    """Override rate and reason distribution over every stored Assessment.

    This is a disagreement measure, not an accuracy measure, so it does not
    need ground truth and is not restricted to the labelled sample.
    """
    assessments = session.scalar(
        select(func.count()).select_from(TriageAssessment)
    ) or 0
    overridden = session.scalar(
        select(func.count(func.distinct(Override.assessment_id)))
    ) or 0
    overrides = session.scalar(select(func.count()).select_from(Override)) or 0

    counts: dict[OverrideReason, int] = {reason: 0 for reason in OVERRIDE_REASONS}
    for reason_value, count in session.execute(
        select(Override.reason, func.count()).group_by(Override.reason)
    ).all():
        try:
            reason = OverrideReason(reason_value)
        except ValueError:  # pragma: no cover - the data layer constrains this
            continue
        counts[reason] = int(count)

    return OverrideMetrics(
        assessments=int(assessments),
        overridden_assessments=int(overridden),
        overrides=int(overrides),
        rate=(overridden / assessments) if assessments else None,
        reasons=tuple(
            OverrideReasonCount(
                reason=reason,
                overrides=counts[reason],
                share=(counts[reason] / overrides) if overrides else None,
            )
            for reason in OVERRIDE_REASONS
        ),
    )


__all__ = [
    "AccuracyEvaluationReport",
    "AccuracyRunError",
    "ConfusionCell",
    "EvaluationRun",
    "FallbackCoverage",
    "FallbackMode",
    "GroundTruthSource",
    "HARNESS_METRIC_FIELDS",
    "HARNESS_OPTIONAL_RUN_FIELDS",
    "HARNESS_RUN_FIELDS",
    "HarnessRun",
    "LevelMetrics",
    "MANIFEST_SCHEMA_VERSION",
    "MajorityBaseline",
    "OverrideMetrics",
    "OverrideReasonCount",
    "PriorityErrorRate",
    "RunBundle",
    "RunCase",
    "RunReport",
    "RunSample",
    "RunSource",
    "build_report",
    "evaluate_run",
    "load_configured_bundle",
    "load_run_bundle",
    "override_metrics",
    "refused_report",
]
