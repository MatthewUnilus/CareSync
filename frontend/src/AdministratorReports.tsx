import { useCallback, useState } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { cx } from "@/utils/cx";

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
import {
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
  tableCaptionClass,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableRowClass,
  tableWrapClass,
} from "./design";
import { formatWaiting, urgencyTextClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

const REPORT_POLL_INTERVAL_MS = 30_000;

const LEVELS: UrgencyLevel[] = ["High", "Medium", "Low"];

/*
 * Report section rhythm: hairline-topped blocks inside the Reports card. The
 * Accuracy Evaluation is the flagship view: first in the section, framed with
 * the accent ramp and a heavier top edge, but the same tokens and table
 * shapes as the other Reports. Nothing here softens a number.
 */
const reportsClass = "flex flex-col gap-5";
const reportBlockClass =
  "flex flex-col gap-3 border-t border-separator-border pt-4";
const reportBlockFeaturedClass =
  "flex flex-col gap-4 rounded-3xl border border-border-button-default bg-background-primary-default p-6";
const reportHeaderClass = "flex flex-wrap items-baseline gap-x-4 gap-y-1";
const reportStatsClass = "flex flex-wrap gap-6";
const reportStatClass = "flex min-w-32 flex-col gap-0.5";
const reportStatLabelClass = sectionLabelClass;
const reportStatFigureClass = cx(
  "text-title-1-medium text-text-primary",
  figureClass,
);
const reportStatNoteClass = "text-caption-1-regular text-text-secondary";
const reportNoteClass = "max-w-2xl text-body-2-regular text-text-secondary";
const matrixCorrectCellClass =
  "bg-status-lime-background text-center font-medium tabular-nums text-status-lime-text";
const matrixMissCellClass =
  "text-center tabular-nums text-text-tertiary";
const matrixTotalCellClass = "text-center font-medium tabular-nums";
const matrixRowHeaderClass =
  "px-3 py-2 text-left align-middle font-medium whitespace-nowrap text-text-primary";

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
    return `${run.sample.labelled_cases} encounters scored offline · no database involved`;
  }
  if (run.source === "evaluation") {
    return `${run.sample.resolved_assessments} stored evaluation-run assessments · ground truth held in its own column`;
  }
  return `${run.sample.resolved_assessments} of ${run.sample.labelled_cases} labelled cases resolved against stored assessments`;
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
  const mode = run.run_mode === "cross_validated" ? "cross-validated" : run.run_mode;
  const fallback = run.fallback.enabled ? "fallback enabled" : "fallback disabled";
  return `${mode} · ${fallback}`;
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
    <div className={reportStatClass}>
      <dt className={reportStatLabelClass}>{label}</dt>
      <dd className={reportStatFigureClass}>{percent(figure.rate)}</dd>
      <span className={reportStatNoteClass}>
        {figure.count} of {figure.denominator} · {note}
      </span>
    </div>
  );
}

function AccuracyRunView({ run }: { run: AccuracyRun }) {
  return (
    <article className="flex flex-col gap-4 border-t border-separator-border pt-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-2 gap-x-4">
        <div>
          <h4 className="text-title-3-medium text-text-primary">
            {runTitle(run)}
            {run.primary ? (
              <span
                className={cx(
                  "ml-2 align-middle text-caption-1-medium text-text-tertiary",
                  figureClass,
                )}
              >
                primary
              </span>
            ) : null}
          </h4>
          <p className={reportStatNoteClass}>
            {run.run_id} · {sampleLabel(run)}
          </p>
        </div>
        <span className={cx(reportStatNoteClass, figureClass)}>
          {modeLabel(run)}
        </span>
      </div>

      <dl className={reportStatsClass}>
        <div className={reportStatClass}>
          <dt className={reportStatLabelClass}>Accuracy</dt>
          <dd className={reportStatFigureClass}>{percent(run.accuracy)}</dd>
          <span className={reportStatNoteClass}>
            {run.correct} of {run.total} correct
          </span>
        </div>
        {run.majority_baseline ? (
          <div className={reportStatClass}>
            <dt className={reportStatLabelClass}>Majority baseline</dt>
            <dd className={reportStatFigureClass}>
              {percent(run.majority_baseline.accuracy)}
            </dd>
            <span
              className={cx(
                reportStatNoteClass,
                run.majority_baseline.beats_baseline
                  ? "text-status-lime-text"
                  : "font-medium text-text-error-primary",
              )}
            >
              Model {points(run.majority_baseline.model_minus_baseline)} vs
              always-{run.majority_baseline.majority_class} ·{" "}
              {run.majority_baseline.beats_baseline
                ? "above baseline"
                : "below baseline"}
            </span>
          </div>
        ) : null}
        {run.macro_f1 !== null ? (
          <div className={reportStatClass}>
            <dt className={reportStatLabelClass}>Macro F1</dt>
            <dd className={reportStatFigureClass}>{percent(run.macro_f1)}</dd>
            <span className={reportStatNoteClass}>
              unweighted across all three levels
            </span>
          </div>
        ) : null}
        <RateFigure
          label="False high priority"
          note="recommended High with a non-High truth, over every non-High truth"
          figure={run.false_high_priority}
        />
        <RateFigure
          label="False low priority"
          note="recommended Low with a non-Low truth, over every non-Low truth"
          figure={run.false_low_priority}
        />
        <RateFigure
          label="High-class recall"
          note="truth-High cases called High; the complement is the missed-urgent share"
          figure={run.high_class_recall}
        />
        <div className={reportStatClass}>
          <dt className={reportStatLabelClass}>Fallback coverage</dt>
          <dd className={reportStatFigureClass}>
            {run.fallback.enabled ? percent(run.fallback.coverage) : "—"}
          </dd>
          <span className={reportStatNoteClass}>
            {run.fallback.enabled
              ? `${run.fallback.fallback_used} of ${run.total} cases took the fallback path`
              : "not exercised in this run"}
          </span>
        </div>
      </dl>

      <div className={tableWrapClass}>
        <table className={tableClass}>
          <caption className={tableCaptionClass}>
            Rows are the machine recommendation; columns are the ground-truth
            urgency level. The diagonal is correct. Counted per assessment, so a
            re-assessment adds a row of its own.
          </caption>
          <thead>
            <tr>
              <th scope="col" className={tableHeadCellClass}>
                Machine recommendation
              </th>
              {LEVELS.map((truth) => (
                <th scope="col" className={tableHeadCellClass} key={truth}>
                  Truth: {truth}
                </th>
              ))}
              <th scope="col" className={tableHeadCellClass}>
                Predicted
              </th>
            </tr>
          </thead>
          <tbody>
            {LEVELS.map((machine) => (
              <tr key={machine} className={tableRowClass}>
                <th
                  scope="row"
                  className={cx(
                    matrixRowHeaderClass,
                    urgencyTextClass(machine),
                  )}
                >
                  {machine}
                </th>
                {LEVELS.map((truth) => (
                  <td
                    key={truth}
                    className={
                      machine === truth
                        ? matrixCorrectCellClass
                        : matrixMissCellClass
                    }
                  >
                    {matrixCell(run, machine, truth)}
                  </td>
                ))}
                <td className={matrixTotalCellClass}>
                  {matrixTotal(run, "machine_recommendation", machine)}
                </td>
              </tr>
            ))}
            <tr className={tableRowClass}>
              <th scope="row" className={matrixRowHeaderClass}>
                Actually
              </th>
              {LEVELS.map((truth) => (
                <td key={truth} className={matrixTotalCellClass}>
                  {matrixTotal(run, "ground_truth", truth)}
                </td>
              ))}
              <td className={matrixTotalCellClass}>{run.total}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className={tableWrapClass}>
        <table className={tableClass}>
          <caption className={tableCaptionClass}>
            Precision and recall for each urgency level separately. A dash means
            the level had no denominator in this run.
          </caption>
          <thead>
            <tr>
              <th scope="col" className={tableHeadCellClass}>
                Urgency level
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Precision
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Recall
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Correct
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Ground truth
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Predicted
              </th>
            </tr>
          </thead>
          <tbody>
            {run.levels.map((level) => (
              <tr key={level.urgency_level} className={tableRowClass}>
                <th
                  scope="row"
                  className={cx(
                    matrixRowHeaderClass,
                    urgencyTextClass(level.urgency_level),
                  )}
                >
                  {level.urgency_level}
                </th>
                <td className={matrixTotalCellClass}>
                  {percent(level.precision)}
                </td>
                <td className={matrixTotalCellClass}>
                  {percent(level.recall)}
                </td>
                <td className={matrixTotalCellClass}>{level.correct}</td>
                <td className={matrixTotalCellClass}>
                  {level.ground_truth_count}
                </td>
                <td className={matrixTotalCellClass}>
                  {level.predicted_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {run.classifier_only ? (
        <div className="flex flex-col gap-2 border-t border-dashed border-separator-border pt-3">
          <h5 className="text-caption-1-medium text-text-secondary">
            Classifier only — secondary, not a machine recommendation
          </h5>
          <p className={reportNoteClass}>
            The learned classifier without the red-flag safety layer. Shown for
            diagnosis only: the figures above are the engine&rsquo;s actual
            machine recommendations.
          </p>
          <dl className={reportStatsClass}>
            <div className={reportStatClass}>
              <dt className={reportStatLabelClass}>Classifier accuracy</dt>
              <dd className={reportStatFigureClass}>
                {percent(run.classifier_only.accuracy)}
              </dd>
              <span className={reportStatNoteClass}>
                {run.classifier_only.correct} of {run.classifier_only.total}{" "}
                correct
              </span>
            </div>
            <div className={reportStatClass}>
              <dt className={reportStatLabelClass}>Classifier macro F1</dt>
              <dd className={reportStatFigureClass}>
                {percent(run.classifier_only.macro_f1)}
              </dd>
              <span className={reportStatNoteClass}>
                without the safety layer
              </span>
            </div>
            <RateFigure
              label="Classifier false low priority"
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

      <p className={reportNoteClass}>
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
        <p className={noticeClass.warning}>
          {run.sample.missing_assessments.length} labelled case(s) reference an
          assessment that is not stored and are excluded:{" "}
          {run.sample.missing_assessments.join(", ")}.
        </p>
      ) : null}

      {run.sample.inconsistent_recommendations.length > 0 ? (
        <p className={noticeClass.warning}>
          {run.sample.inconsistent_recommendations.length} case(s) record a
          recommendation that differs from the stored assessment. The stored,
          immutable recommendation was used:{" "}
          {run.sample.inconsistent_recommendations.join(", ")}.
        </p>
      ) : null}
    </article>
  );
}

function OverrideFigures({ overrides }: { overrides: AccuracyOverrideMetrics }) {
  return (
    <div className="flex flex-col gap-3 border-t border-separator-border pt-4">
      <div className={reportHeaderClass}>
        <h4 className="text-title-3-medium text-text-primary">Overrides</h4>
        <p className={reportStatNoteClass}>
          Across all {overrides.assessments} stored assessments · where staff
          disagreed with the engine
        </p>
      </div>
      <dl className={reportStatsClass}>
        <div className={reportStatClass}>
          <dt className={reportStatLabelClass}>Override rate</dt>
          <dd className={reportStatFigureClass}>{percent(overrides.rate)}</dd>
          <span className={reportStatNoteClass}>
            {overrides.overridden_assessments} of {overrides.assessments}{" "}
            assessments carry an override
          </span>
        </div>
        <div className={reportStatClass}>
          <dt className={reportStatLabelClass}>Override records</dt>
          <dd className={reportStatFigureClass}>{overrides.overrides}</dd>
          <span className={reportStatNoteClass}>one row per human act</span>
        </div>
      </dl>
      <div className={tableWrapClass}>
        <table className={tableClass}>
          <caption className={tableCaptionClass}>
            Every override reason in the fixed glossary set, including reasons
            with no occurrences in this period.
          </caption>
          <thead>
            <tr>
              <th scope="col" className={tableHeadCellClass}>
                Override reason
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Overrides
              </th>
              <th scope="col" className={tableHeadCellClass}>
                Share
              </th>
            </tr>
          </thead>
          <tbody>
            {overrides.reasons.map((reason) => (
              <tr key={reason.reason} className={tableRowClass}>
                <th scope="row" className={matrixRowHeaderClass}>
                  {reason.reason}
                </th>
                <td className={matrixTotalCellClass}>{reason.overrides}</td>
                <td className={matrixTotalCellClass}>
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
      className={reportBlockFeaturedClass}
      aria-labelledby="accuracy-evaluation-report"
    >
      <div className={reportHeaderClass}>
        <h3 id="accuracy-evaluation-report" className="text-title-2-medium text-text-primary">
          Accuracy Evaluation
        </h3>
        <p className={reportStatNoteClass}>
          Machine recommendation against independent ground truth · the
          project's central evidence
        </p>
      </div>

      {report.available ? (
        report.runs.map((run) => <AccuracyRunView key={run.run_id} run={run} />)
      ) : (
        <div className="flex flex-col gap-2">
          <p className={noticeClass.warning}>
            {report.empty_reason ??
              "No labelled evaluation run is available."}
          </p>
          <p className={reportNoteClass}>
            Accuracy is shown only when a run supplies independent ground-truth
            urgency levels. Zero would be a claim, not a measurement, so no
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
    <div className={reportsClass}>
      <div className={reportHeaderClass}>
        <p className={mutedTextClass}>
          Read-only views derived on demand from stored records · updates every
          30 seconds
        </p>
        <Button
          variant="secondary"
          size="small"
          leadingIcon={RiRefreshLine}
          onClick={() => {
            void load();
          }}
        >
          Refresh reports
        </Button>
      </div>

      {error ? (
        <p className={noticeClass.error} role="status">
          {error}
        </p>
      ) : null}

      {loading && reports === null ? (
        <p className={mutedTextClass}>Loading the reports…</p>
      ) : null}

      {reports === null ? null : (
        <>
          <AccuracyEvaluation report={reports.accuracyEvaluation} />

          <section
            className={reportBlockClass}
            aria-labelledby="daily-queue-report"
          >
            <div className={reportHeaderClass}>
              <h3 id="daily-queue-report" className="text-title-3-medium text-text-primary">
                Daily Queue
              </h3>
              <p className={reportStatNoteClass}>
                UTC day {reports.dailyQueue.day} · arrivals, departures and
                backlog
              </p>
            </div>
            <dl className={reportStatsClass}>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Volume</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyQueue.volume}
                </dd>
                <span className={reportStatNoteClass}>arrived</span>
              </div>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Throughput</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyQueue.throughput}
                </dd>
                <span className={reportStatNoteClass}>departed</span>
              </div>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Awaiting</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyQueue.awaiting}
                </dd>
                <span className={reportStatNoteClass}>
                  of the day's arrivals
                </span>
              </div>
            </dl>
            <p className={reportNoteClass}>
              Volume counts encounters that arrived on the day; throughput
              counts those that departed on it, even if they arrived earlier.
            </p>
          </section>

          <section
            className={reportBlockClass}
            aria-labelledby="priority-distribution-report"
          >
            <div className={reportHeaderClass}>
              <h3
                id="priority-distribution-report"
                className="text-title-3-medium text-text-primary"
              >
                Priority Distribution
              </h3>
              <p className={reportStatNoteClass}>
                One urgency level per encounter ·{" "}
                {reports.priorityDistribution.total} encounters
              </p>
            </div>
            <div className={tableWrapClass}>
              <table className={tableClass}>
                <caption className={tableCaptionClass}>
                  The governing final decision of each encounter, including
                  departed encounters and re-assessed ones
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className={tableHeadCellClass}>
                      Urgency
                    </th>
                    <th scope="col" className={tableHeadCellClass}>
                      Encounters
                    </th>
                    <th scope="col" className={tableHeadCellClass}>
                      Share
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {reports.priorityDistribution.levels.map((level) => (
                    <tr key={level.urgency_level} className={tableRowClass}>
                      <td
                        className={cx(
                          tableCellClass,
                          "font-medium",
                          urgencyTextClass(level.urgency_level),
                        )}
                      >
                        {level.urgency_level}
                      </td>
                      <td
                        className={cx(
                          tableCellClass,
                          "whitespace-nowrap tabular-nums",
                        )}
                      >
                        {level.encounters}
                      </td>
                      <td
                        className={cx(
                          tableCellClass,
                          "whitespace-nowrap tabular-nums",
                        )}
                      >
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
            className={reportBlockClass}
            aria-labelledby="performance-report"
          >
            <div className={reportHeaderClass}>
              <h3 id="performance-report" className="text-title-3-medium text-text-primary">
                Performance
              </h3>
              <p className={reportStatNoteClass}>
                Departed encounters only · {reports.performance.completed}{" "}
                completed
              </p>
            </div>
            <dl className={reportStatsClass}>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Average waiting</dt>
                <dd className={reportStatFigureClass}>
                  {formatWaiting(
                    Math.round(reports.performance.average_waiting_seconds),
                  )}
                </dd>
                <span className={reportStatNoteClass}>arrival to departure</span>
              </div>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Average processing</dt>
                <dd className={reportStatFigureClass}>
                  {formatWaiting(
                    Math.round(reports.performance.average_processing_seconds),
                  )}
                </dd>
                <span className={reportStatNoteClass}>
                  assessment to departure
                </span>
              </div>
            </dl>
            {reports.performance.entries.length > 0 ? (
              <div className={cx(tableWrapClass, "max-h-72 overflow-y-auto")}>
                <table className={tableClass}>
                  <caption className={tableCaptionClass}>
                    Time waiting and processing for each departed encounter
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className={tableHeadCellClass}>
                        Encounter
                      </th>
                      <th scope="col" className={tableHeadCellClass}>
                        Waiting
                      </th>
                      <th scope="col" className={tableHeadCellClass}>
                        Processing
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {reports.performance.entries.map((entry) => (
                      <tr key={entry.encounter_id} className={tableRowClass}>
                        <td className={tableCellClass}>
                          #{entry.encounter_id}
                        </td>
                        <td
                          className={cx(
                            tableCellClass,
                            "whitespace-nowrap tabular-nums",
                          )}
                        >
                          {formatWaiting(entry.waiting_seconds)}
                        </td>
                        <td
                          className={cx(
                            tableCellClass,
                            "whitespace-nowrap tabular-nums",
                          )}
                        >
                          {formatWaiting(entry.processing_seconds)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className={mutedTextClass}>
                No encounter has departed yet, so there is no waiting or
                processing time to show
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
