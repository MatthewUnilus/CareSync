"""The Accuracy Evaluation Report: the project's central evidence.

What this module does
---------------------
It joins two things that are deliberately kept apart:

* the **stored Triage Assessments** — specifically their immutable
  ``machine_recommendation``, which is never rewritten by an Override; and
* a **labelled evaluation run**, written by the offline harness, which supplies
  the independent ground-truth Urgency Level and the run's mode.

The join is by Assessment id. Reading the Machine Recommendation from the row
rather than from the run is what makes the report's central property true: an
Override moves ``final_decision`` and appends an Override row, but the matrix,
precision, recall and both false-priority rates do not move by one cell. The
``final_decision`` column is never read by this module.

Ground truth is not inferable from the engine, so it cannot live on the
Assessment. It lives in the run manifest, under an explicit ``ground_truth``
object naming its source and version; the UI displays that source. No labels
means no score: :func:`build_report` returns an explicit empty state rather
than a zero that could be mistaken for a measurement.

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
The run manifest records the mode explicitly: ``fallback-disabled`` or
``fallback-enabled``. Mode is never inferred from the Assessments (ticket 08's
handoff), and a disabled run is rejected if any case claims the fallback ran.
Coverage is its own statistic and is only defined for an enabled run:

* **Coverage** = resolved cases whose recommendation came from the fallback
  path / all resolved cases.
* **Unclassified rate** = resolved cases the fallback could not classify /
  all resolved cases.

Coverage never enters the accuracy figure. The primary reproducible run is the
disabled one; the enabled run sits beside it.

Manifest contract
-----------------
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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Override, TriageAssessment
from app.override_reasons import OVERRIDE_REASONS, OverrideReason
from app.prioritisation import URGENCY_RANK, UrgencyLevel

MANIFEST_SCHEMA_VERSION = 1

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
class RunBundle:
    schema_version: int
    runs: tuple[EvaluationRun, ...]


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


def load_run_bundle(path: Path | str | None) -> RunBundle | None:
    """Read the harness's labelled run manifest, or return ``None`` if absent.

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
    except (OSError, json.JSONDecodeError) as error:
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


# ---------------------------------------------------------------------------
# Computing the report
# ---------------------------------------------------------------------------


def build_report(
    session: Session, bundle: RunBundle | None
) -> AccuracyEvaluationReport:
    """Compute the Accuracy Evaluation Report from stored rows and one bundle."""
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

    evaluated = tuple(evaluate_run(session, run) for run in bundle.runs)
    available = tuple(run for run in evaluated if run.total > 0)
    if available:
        return AccuracyEvaluationReport(
            available=True,
            empty_reason=None,
            runs=available,
            overrides=overrides,
        )

    if all(not run.cases for run in bundle.runs):
        reason = (
            "The evaluation run manifest contains no labelled cases. Accuracy "
            "figures are withheld rather than shown as zero."
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

    return RunReport(
        run_id=run.run_id,
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
    "LevelMetrics",
    "MANIFEST_SCHEMA_VERSION",
    "OverrideMetrics",
    "OverrideReasonCount",
    "PriorityErrorRate",
    "RunBundle",
    "RunCase",
    "RunReport",
    "RunSample",
    "build_report",
    "evaluate_run",
    "load_run_bundle",
    "override_metrics",
]
