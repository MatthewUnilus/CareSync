import { useCallback, useState } from "react";

import { api, ApiError } from "./api";
import type {
  AccuracyConfusionCell,
  AccuracyEvaluationReport,
  AccuracyOverrideMetrics,
  AccuracyPriorityErrorRate,
  AccuracyRun,
  DailyQueueReport,
  PerformanceReport,
  UrgencyDistributionReport,
  UrgencyLevel,
} from "./api";
import { formatWaiting, urgencyClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

const REPORT_POLL_INTERVAL_MS = 30_000;

const LEVELS: UrgencyLevel[] = ["High", "Medium", "Low"];

interface ReportSet {
  dailyQueue: DailyQueueReport;
  priorityDistribution: UrgencyDistributionReport;
  performance: PerformanceReport;
  accuracyEvaluation: AccuracyEvaluationReport;
}

function percent(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${Math.round(value * 1000) / 10}%`;
}

function points(value: number): string {
  const rounded = Math.round(value * 1000) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded} pts`;
}

function runTitle(run: AccuracyRun): string {
  if (run.run_mode === "cross_validated") {
    return "Cross-validated composed engine";
  }
  if (run.run_mode === "pipeline") {
    return run.fallback.enabled
      ? "Whole pipeline · fallback enabled"
      : "Whole pipeline · fallback disabled";
  }
  if (run.run_mode === "evaluation") {
    return "Stored evaluation run · rubric-labelled corpus";
  }
  return run.run_id;
}

function sampleLabel(run: AccuracyRun): string {
  if (run.source === "harness") {
    return `${run.sample.labelled_cases} Encounters scored offline · no database involved`;
  }
  if (run.source === "evaluation") {
    return `${run.sample.resolved_assessments} stored evaluation-run Assessments · ground truth held in its own column`;
  }
  return `${run.sample.resolved_assessments} of ${run.sample.labelled_cases} labelled cases resolved against stored Assessments`;
}

function matrixCell(
  run: AccuracyRun,
  machine: UrgencyLevel,
  truth: UrgencyLevel,
): number {
  return (
    run.confusion_matrix.find(
      (cell: AccuracyConfusionCell) =>
        cell.machine_recommendation === machine && cell.ground_truth === truth,
    )?.assessments ?? 0
  );
}

function matrixTotal(
  run: AccuracyRun,
  field: "machine_recommendation" | "ground_truth",
  level: UrgencyLevel,
): number {
  return run.confusion_matrix
    .filter((cell) => cell[field] === level)
    .reduce((sum, cell) => sum + cell.assessments, 0);
}

function modeLabel(run: AccuracyRun): string {
  const fallback = run.fallback.enabled ? "fallback enabled" : "fallback disabled";
  return `${run.run_mode} · ${fallback}`;
}

function RateFigure({
  label,
  note,
  figure,
}: {
  label: string;
  note: string;
  figure: AccuracyPriorityErrorRate;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{percent(figure.rate)}</dd>
      <span className="muted">
        {figure.count} of {figure.denominator} · {note}
      </span>
    </div>
  );
}

function AccuracyRunView({ run }: { run: AccuracyRun }) {
  return (
    <article className="accuracy-run">
      <div className="accuracy-run-header">
        <div>
          <h4>
            {runTitle(run)}
            {run.primary ? (
              <span className="accuracy-primary">Primary</span>
            ) : null}
          </h4>
          <p className="muted">
            {run.run_id} · {sampleLabel(run)}
          </p>
        </div>
        <span
          className={`accuracy-mode ${
            run.fallback.enabled
              ? "accuracy-mode-enabled"
              : "accuracy-mode-disabled"
          }`}
        >
          {modeLabel(run)}
        </span>
      </div>

      <dl className="report-stats accuracy-stats">
        <div>
          <dt>Accuracy</dt>
          <dd>{percent(run.accuracy)}</dd>
          <span className="muted">
            {run.correct} of {run.total} correct
          </span>
        </div>
        {run.majority_baseline ? (
          <div>
            <dt>Majority baseline</dt>
            <dd>{percent(run.majority_baseline.accuracy)}</dd>
            <span
              className={
                run.majority_baseline.beats_baseline
                  ? "accuracy-baseline-above"
                  : "accuracy-baseline-below"
              }
            >
              Model {points(run.majority_baseline.model_minus_baseline)} vs
              always-{run.majority_baseline.majority_class} ·{" "}
              {run.majority_baseline.beats_baseline
                ? "above baseline"
                : "BELOW baseline"}
            </span>
          </div>
        ) : null}
        {run.macro_f1 !== null ? (
          <div>
            <dt>Macro F1</dt>
            <dd>{percent(run.macro_f1)}</dd>
            <span className="muted">unweighted across all three levels</span>
          </div>
        ) : null}
        <RateFigure
          label="False High-Priority"
          note="recommended High with a non-High truth, over every non-High truth"
          figure={run.false_high_priority}
        />
        <RateFigure
          label="False Low-Priority"
          note="recommended Low with a non-Low truth, over every non-Low truth"
          figure={run.false_low_priority}
        />
        <RateFigure
          label="High-class recall"
          note="truth-High cases called High; the complement is the missed-urgent share"
          figure={run.high_class_recall}
        />
        <div>
          <dt>Fallback coverage</dt>
          <dd>
            {run.fallback.enabled ? percent(run.fallback.coverage) : "—"}
          </dd>
          <span className="muted">
            {run.fallback.enabled
              ? `${run.fallback.fallback_used} of ${run.total} cases took the fallback path`
              : "not exercised in this run"}
          </span>
        </div>
      </dl>

      <div className="admin-table-wrap">
        <table className="admin-queue-table report-table accuracy-matrix">
          <caption className="admin-table-caption">
            Rows are the Machine Recommendation; columns are the ground-truth
            Urgency Level. The diagonal is correct. Counted per Assessment, so a
            Re-assessment adds a row of its own.
          </caption>
          <thead>
            <tr>
              <th scope="col">Machine Recommendation</th>
              {LEVELS.map((truth) => (
                <th scope="col" key={truth}>
                  Truth: {truth}
                </th>
              ))}
              <th scope="col">Predicted</th>
            </tr>
          </thead>
          <tbody>
            {LEVELS.map((machine) => (
              <tr key={machine}>
                <th scope="row">
                  <span className={`urgency-badge ${urgencyClass(machine)}`}>
                    {machine}
                  </span>
                </th>
                {LEVELS.map((truth) => (
                  <td
                    key={truth}
                    className={
                      machine === truth
                        ? "accuracy-matrix-correct"
                        : "accuracy-matrix-miss"
                    }
                  >
                    {matrixCell(run, machine, truth)}
                  </td>
                ))}
                <td className="accuracy-matrix-total">
                  {matrixTotal(run, "machine_recommendation", machine)}
                </td>
              </tr>
            ))}
            <tr>
              <th scope="row" className="accuracy-matrix-total">
                Actually
              </th>
              {LEVELS.map((truth) => (
                <td key={truth} className="accuracy-matrix-total">
                  {matrixTotal(run, "ground_truth", truth)}
                </td>
              ))}
              <td className="accuracy-matrix-total">{run.total}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="admin-table-wrap">
        <table className="admin-queue-table report-table">
          <caption className="admin-table-caption">
            Precision and recall for each Urgency Level separately. A dash means
            the level had no denominator in this run.
          </caption>
          <thead>
            <tr>
              <th scope="col">Urgency Level</th>
              <th scope="col">Precision</th>
              <th scope="col">Recall</th>
              <th scope="col">Correct</th>
              <th scope="col">Ground truth</th>
              <th scope="col">Predicted</th>
            </tr>
          </thead>
          <tbody>
            {run.levels.map((level) => (
              <tr key={level.urgency_level}>
                <th scope="row">
                  <span
                    className={`urgency-badge ${urgencyClass(level.urgency_level)}`}
                  >
                    {level.urgency_level}
                  </span>
                </th>
                <td className="accuracy-matrix-total">
                  {percent(level.precision)}
                </td>
                <td className="accuracy-matrix-total">
                  {percent(level.recall)}
                </td>
                <td className="accuracy-matrix-total">{level.correct}</td>
                <td className="accuracy-matrix-total">
                  {level.ground_truth_count}
                </td>
                <td className="accuracy-matrix-total">
                  {level.predicted_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {run.classifier_only ? (
        <div className="accuracy-variant">
          <h5>Classifier only · secondary, not a Machine Recommendation</h5>
          <p className="muted report-note">
            The learned classifier without the red-flag safety layer. Shown for
            diagnosis only: the figures above are the engine&rsquo;s actual
            Machine Recommendations.
          </p>
          <dl className="report-stats accuracy-stats">
            <div>
              <dt>Classifier accuracy</dt>
              <dd>{percent(run.classifier_only.accuracy)}</dd>
              <span className="muted">
                {run.classifier_only.correct} of {run.classifier_only.total}{" "}
                correct
              </span>
            </div>
            <div>
              <dt>Classifier macro F1</dt>
              <dd>{percent(run.classifier_only.macro_f1)}</dd>
              <span className="muted">without the safety layer</span>
            </div>
            <RateFigure
              label="Classifier False Low-Priority"
              note="recommended Low with a non-Low truth"
              figure={run.classifier_only.false_low_priority}
            />
            <RateFigure
              label="Classifier High-class recall"
              note="truth-High cases the classifier itself called High"
              figure={run.classifier_only.high_class_recall}
            />
          </dl>
        </div>
      ) : null}

      <p className="muted report-note accuracy-provenance">
        Ground truth: <strong>{run.ground_truth.name}</strong> (
        {run.ground_truth.version}) · {run.ground_truth.citation}
        {run.dataset ? ` · Dataset: ${run.dataset}` : null}
        {run.engine_artefact ? ` · Engine: ${run.engine_artefact}` : null}
        {run.fallback.enabled && run.fallback.unclassified > 0
          ? ` · Unclassified by the fallback: ${percent(
              run.fallback.unclassified_rate,
            )}`
          : null}
      </p>

      {run.sample.missing_assessments.length > 0 ? (
        <p className="notice notice-warning">
          {run.sample.missing_assessments.length} labelled case(s) reference an
          Assessment that is not stored and are excluded:{" "}
          {run.sample.missing_assessments.join(", ")}.
        </p>
      ) : null}

      {run.sample.inconsistent_recommendations.length > 0 ? (
        <p className="notice notice-warning">
          {run.sample.inconsistent_recommendations.length} case(s) record a
          recommendation that differs from the stored Assessment. The stored,
          immutable recommendation was used:{" "}
          {run.sample.inconsistent_recommendations.join(", ")}.
        </p>
      ) : null}
    </article>
  );
}

function OverrideFigures({ overrides }: { overrides: AccuracyOverrideMetrics }) {
  return (
    <div className="accuracy-overrides">
      <div className="report-header">
        <h4>Overrides</h4>
        <p className="muted">
          Across all {overrides.assessments} stored Assessments · where staff
          disagreed with the engine
        </p>
      </div>
      <dl className="report-stats accuracy-stats">
        <div>
          <dt>Override rate</dt>
          <dd>{percent(overrides.rate)}</dd>
          <span className="muted">
            {overrides.overridden_assessments} of {overrides.assessments}{" "}
            Assessments carry an Override
          </span>
        </div>
        <div>
          <dt>Override records</dt>
          <dd>{overrides.overrides}</dd>
          <span className="muted">one row per human act</span>
        </div>
      </dl>
      <div className="admin-table-wrap">
        <table className="admin-queue-table report-table">
          <caption className="admin-table-caption">
            Every Override Reason in the fixed glossary set, including reasons
            with no occurrences in this period.
          </caption>
          <thead>
            <tr>
              <th scope="col">Override Reason</th>
              <th scope="col">Overrides</th>
              <th scope="col">Share</th>
            </tr>
          </thead>
          <tbody>
            {overrides.reasons.map((reason) => (
              <tr key={reason.reason}>
                <th scope="row">{reason.reason}</th>
                <td className="accuracy-matrix-total">{reason.overrides}</td>
                <td className="accuracy-matrix-total">
                  {percent(reason.share)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AccuracyEvaluation({
  report,
}: {
  report: AccuracyEvaluationReport;
}) {
  return (
    <section
      className="report-block report-block-featured"
      aria-labelledby="accuracy-evaluation-report"
    >
      <div className="report-header">
        <h3 id="accuracy-evaluation-report">Accuracy Evaluation</h3>
        <p className="muted">
          Machine Recommendation against independent ground truth · the
          project's central evidence
        </p>
      </div>

      {report.available ? (
        report.runs.map((run) => <AccuracyRunView key={run.run_id} run={run} />)
      ) : (
        <div className="accuracy-empty">
          <p className="notice notice-warning">
            {report.empty_reason ??
              "No labelled evaluation run is available."}
          </p>
          <p className="muted report-note">
            Accuracy is shown only when a run supplies independent ground-truth
            Urgency Levels. Zero would be a claim, not a measurement, so no
            score is displayed.
          </p>
        </div>
      )}

      <OverrideFigures overrides={report.overrides} />
    </section>
  );
}

/**
 * The Reports. Every figure is returned by the server, which derives it on
 * demand from stored records; this component only renders it, so there is
 * nothing to invalidate and no client-side aggregate to drift.
 *
 * The Accuracy Evaluation is first and visually featured because it is the
 * project's central evidence. It is never flattered: the raw figures are shown
 * with the ground-truth source named, and an unlabelled database shows an
 * explicit empty state.
 */
export default function AdministratorReports() {
  const [reports, setReports] = useState<ReportSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [
        dailyQueue,
        priorityDistribution,
        performance,
        accuracyEvaluation,
      ] = await Promise.all([
        api.dailyQueueReport(),
        api.priorityDistributionReport(),
        api.performanceReport(),
        api.accuracyEvaluationReport(),
      ]);
      setReports({
        dailyQueue,
        priorityDistribution,
        performance,
        accuracyEvaluation,
      });
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(load, REPORT_POLL_INTERVAL_MS);

  return (
    <div className="reports">
      <div className="queue-header">
        <p className="muted">
          Read-only views derived on demand from stored records · updates every
          30 seconds
        </p>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            void load();
          }}
        >
          Refresh reports
        </button>
      </div>

      {error ? (
        <p className="notice notice-error" role="status">
          {error}
        </p>
      ) : null}

      {loading && reports === null ? (
        <p className="muted">Loading the reports…</p>
      ) : null}

      {reports === null ? null : (
        <>
          <AccuracyEvaluation report={reports.accuracyEvaluation} />

          <section
            className="report-block"
            aria-labelledby="daily-queue-report"
          >
            <div className="report-header">
              <h3 id="daily-queue-report">Daily Queue</h3>
              <p className="muted">
                UTC day {reports.dailyQueue.day} · arrivals, departures and
                backlog
              </p>
            </div>
            <dl className="report-stats">
              <div>
                <dt>Volume</dt>
                <dd>{reports.dailyQueue.volume}</dd>
                <span className="muted">arrived</span>
              </div>
              <div>
                <dt>Throughput</dt>
                <dd>{reports.dailyQueue.throughput}</dd>
                <span className="muted">departed</span>
              </div>
              <div>
                <dt>Awaiting</dt>
                <dd>{reports.dailyQueue.awaiting}</dd>
                <span className="muted">of the day's arrivals</span>
              </div>
            </dl>
            <p className="muted report-note">
              Volume counts Encounters that arrived on the day; throughput
              counts those that departed on it, even if they arrived earlier.
            </p>
          </section>

          <section
            className="report-block"
            aria-labelledby="priority-distribution-report"
          >
            <div className="report-header">
              <h3 id="priority-distribution-report">Priority Distribution</h3>
              <p className="muted">
                One Urgency Level per Encounter · {reports.priorityDistribution.total}{" "}
                Encounters
              </p>
            </div>
            <div className="admin-table-wrap">
              <table className="admin-queue-table report-table">
                <caption className="admin-table-caption">
                  The governing Final Decision of each Encounter, including
                  departed Encounters and re-assessed ones
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Urgency</th>
                    <th scope="col">Encounters</th>
                    <th scope="col">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.priorityDistribution.levels.map((level) => (
                    <tr key={level.urgency_level}>
                      <td>
                        <span
                          className={`urgency-badge ${urgencyClass(level.urgency_level)}`}
                        >
                          {level.urgency_level}
                        </span>
                      </td>
                      <td className="admin-waiting">{level.encounters}</td>
                      <td className="admin-waiting">
                        {reports.priorityDistribution.total === 0
                          ? "—"
                          : `${Math.round(
                              (level.encounters /
                                reports.priorityDistribution.total) *
                                100,
                            )}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section
            className="report-block"
            aria-labelledby="performance-report"
          >
            <div className="report-header">
              <h3 id="performance-report">Performance</h3>
              <p className="muted">
                Departed Encounters only · {reports.performance.completed}{" "}
                completed
              </p>
            </div>
            <dl className="report-stats">
              <div>
                <dt>Average waiting</dt>
                <dd>
                  {formatWaiting(
                    Math.round(reports.performance.average_waiting_seconds),
                  )}
                </dd>
                <span className="muted">arrival to departure</span>
              </div>
              <div>
                <dt>Average processing</dt>
                <dd>
                  {formatWaiting(
                    Math.round(reports.performance.average_processing_seconds),
                  )}
                </dd>
                <span className="muted">assessment to departure</span>
              </div>
            </dl>
            {reports.performance.entries.length > 0 ? (
              <div className="admin-table-wrap report-table-wrap">
                <table className="admin-queue-table report-table">
                  <caption className="admin-table-caption">
                    Time waiting and processing for each departed Encounter
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Encounter</th>
                      <th scope="col">Waiting</th>
                      <th scope="col">Processing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reports.performance.entries.map((entry) => (
                      <tr key={entry.encounter_id}>
                        <td>#{entry.encounter_id}</td>
                        <td className="admin-waiting">
                          {formatWaiting(entry.waiting_seconds)}
                        </td>
                        <td className="admin-waiting">
                          {formatWaiting(entry.processing_seconds)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">
                No Encounter has departed yet, so there is no waiting or
                processing time to show.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
