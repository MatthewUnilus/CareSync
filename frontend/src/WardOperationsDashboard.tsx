import { useCallback, useEffect, useState } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type {
  InvestigationReviewReport,
  LengthOfStayReport,
  MedicationTimelinessReport,
  TaskCompletionReport,
  WardCensusReport,
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
import { formatWaiting } from "./queueDisplay";

/**
 * Ward Operations Dashboard (ticket 39).
 *
 * Read-only oversight for the administrator role. Every figure is derived on
 * demand from stored records and never cached. The dashboard sits alongside
 * the existing Reports and Audit Log in the Administrator view.
 */
export default function WardOperationsDashboard() {
  const [census, setCensus] = useState<WardCensusReport | null>(null);
  const [lengthOfStay, setLengthOfStay] = useState<LengthOfStayReport | null>(null);
  const [medTimeliness, setMedTimeliness] = useState<MedicationTimelinessReport | null>(null);
  const [invReview, setInvReview] = useState<InvestigationReviewReport | null>(null);
  const [taskCompletion, setTaskCompletion] = useState<TaskCompletionReport | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [periodDays, setPeriodDays] = useState(7);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, los, mt, ir, tc] = await Promise.all([
        api.wardCensusReport(),
        api.lengthOfStayReport(),
        api.medicationTimelinessReport(periodDays),
        api.investigationReviewReport(),
        api.taskCompletionReport(periodDays),
      ]);
      setCensus(c);
      setLengthOfStay(los);
      setMedTimeliness(mt);
      setInvReview(ir);
      setTaskCompletion(tc);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoading(false);
    }
  }, [periodDays]);

  useEffect(() => {
    void load();
  }, [load]);

  const handlePeriodChange = (days: number) => {
    setPeriodDays(days);
    void load();
  };

  return (
    <>
      <section
        className="flex flex-col gap-5"
        id="ward-operations"
        data-reports-mount="administrator"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-title-3-medium text-text-primary">Ward Operations</h2>
            <p className={mutedTextClass}>
              Read-only views derived on demand from stored records · updates every
              30 seconds
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={mutedTextClass}>Period:</span>
            {[7, 14, 30].map((d) => (
              <Button
                key={d}
                variant={periodDays === d ? "primary" : "secondary"}
                className="min-h-11 px-3"
                onClick={() => handlePeriodChange(d)}
              >
                {d}d
              </Button>
            ))}
            <Button
              variant="secondary"
              className="min-h-11"
              leadingIcon={RiRefreshLine}
              onClick={() => void load()}
            >
              Refresh
            </Button>
          </div>
        </div>

        {error ? (
          <p className={noticeClass.error} role="status">
            {error}
          </p>
        ) : null}

        {loading && census === null ? (
          <p className={mutedTextClass}>Loading the dashboard…</p>
        ) : null}

        {census !== null && (
          <>
            {/* Ward Census */}
            <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h3 className="text-title-3-medium text-text-primary">Ward Census</h3>
                <p className="text-caption-1-regular text-text-secondary">
                  {census.total_patients} patient{plural(census.total_patients, "", "s")} currently admitted
                </p>
              </div>
              <div className="flex flex-wrap gap-6">
                <div className="flex min-w-32 flex-col gap-0.5">
                  <dt className={sectionLabelClass}>Total</dt>
                  <dd className={cx("text-title-1-medium text-text-primary", figureClass)}>
                    {census.total_patients}
                  </dd>
                </div>
                {Object.entries(census.by_ward).map(([ward, count]) => (
                  <div key={ward} className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Ward {ward}</dt>
                    <dd className={cx("text-title-1-medium text-text-primary", figureClass)}>
                      {count}
                    </dd>
                  </div>
                ))}
              </div>
              <p className="max-w-2xl text-body-2-regular text-text-secondary">
                Current inpatients grouped by ward and bed. A patient is counted once
                in their current location.
              </p>
            </section>

            {/* Length of Stay */}
            {lengthOfStay && (
              <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h3 className="text-title-3-medium text-text-primary">Length of Stay</h3>
                  <p className="text-caption-1-regular text-text-secondary">
                    Average {formatWaiting(Math.round(lengthOfStay.average_seconds))} across{" "}
                    {lengthOfStay.distribution.length} patient{plural(lengthOfStay.distribution.length, "", "s")}
                  </p>
                </div>
                <dl className="flex flex-wrap gap-6">
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Average</dt>
                    <dd className={cx("text-title-1-medium text-text-primary", figureClass)}>
                      {formatWaiting(Math.round(lengthOfStay.average_seconds))}
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">arrival to now</span>
                  </div>
                </dl>
                {lengthOfStay.distribution.length > 0 ? (
                  <div className="relative min-h-0">
                    <div className={cx(tableWrapClass, "max-h-72 overflow-y-auto")}>
                      <table className={tableClass}>
                        <caption className={tableCaptionClass}>
                          Current inpatients ordered by length of stay (longest first)
                        </caption>
                        <thead>
                          <tr>
                            <th scope="col" className={tableHeadCellClass}>Patient</th>
                            <th scope="col" className={tableHeadCellClass}>Location</th>
                            <th scope="col" className={tableHeadCellClass}>Stay</th>
                          </tr>
                        </thead>
                        <tbody>
                          {lengthOfStay.distribution.map((item) => (
                            <tr key={item.admission_id} className={tableRowClass}>
                              <td className={tableCellClass}>{item.patient}</td>
                              <td className={tableCellClass}>{item.ward} · {item.bed}</td>
                              <td className={cx(tableCellClass, "whitespace-nowrap", figureClass)}>
                                {item.days} day{plural(item.days, "", "s")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <p className={mutedTextClass}>No current inpatients.</p>
                )}
                <p className="max-w-2xl text-body-2-regular text-text-secondary">
                  Time from admission to now for each current inpatient. The average
                  is a mean across all open admissions.
                </p>
              </section>
            )}

            {/* Medication Timeliness */}
            {medTimeliness && (
              <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h3 className="text-title-3-medium text-text-primary">Medication Timeliness</h3>
                  <p className="text-caption-1-regular text-text-secondary">
                    {medTimeliness.total} dose{plural(medTimeliness.total, "", "s")} in the last{" "}
                    {periodDays} day{plural(periodDays, "", "s")}
                  </p>
                </div>
                <dl className="flex flex-wrap gap-6">
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>On time</dt>
                    <dd className={cx("text-title-1-medium text-status-lime-text", figureClass)}>
                      {medTimeliness.on_time} ({medTimeliness.on_time_pct}%)
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">recorded at or before due time</span>
                  </div>
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Late</dt>
                    <dd className={cx("text-title-1-medium text-status-purple-text", figureClass)}>
                      {medTimeliness.late} ({medTimeliness.total > 0 ? Math.round((medTimeliness.late / medTimeliness.total) * 100) : 0}%)
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">recorded after due time</span>
                  </div>
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Not given</dt>
                    <dd className={cx("text-title-1-medium text-text-error-primary", figureClass)}>
                      {medTimeliness.not_given} ({medTimeliness.total > 0 ? Math.round((medTimeliness.not_given / medTimeliness.total) * 100) : 0}%)
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">withheld, refused or unavailable</span>
                  </div>
                </dl>
                <p className="max-w-2xl text-body-2-regular text-text-secondary">
                  A dose is on time when recorded at or before its scheduled round time.
                  Late means recorded after the round time. Not given covers withheld,
                  refused and unavailable — each requires a reason. The proportion on
                  time answers whether the ward is keeping to its medication schedule.
                </p>
              </section>
            )}

            {/* Investigation Review */}
            {invReview && (
              <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h3 className="text-title-3-medium text-text-primary">Results Awaiting Review</h3>
                  <p className="text-caption-1-regular text-text-secondary">
                    {invReview.awaiting_review_count} result{plural(invReview.awaiting_review_count, "", "s")} awaiting review
                  </p>
                </div>
                <dl className="flex flex-wrap gap-6">
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Awaiting review</dt>
                    <dd className={cx("text-title-1-medium text-status-purple-text", figureClass)}>
                      {invReview.awaiting_review_count}
                    </dd>
                  </div>
                  {invReview.oldest_wait_seconds !== null && (
                    <div className="flex min-w-32 flex-col gap-0.5">
                      <dt className={sectionLabelClass}>Oldest wait</dt>
                      <dd className={cx("text-title-1-medium text-text-primary", figureClass)}>
                        {formatWaiting(invReview.oldest_wait_seconds)}
                        <span className="text-caption-1-regular text-text-secondary">since result available</span>
                      </dd>
                    </div>
                  )}
                </dl>
                <p className="max-w-2xl text-body-2-regular text-text-secondary">
                  Every result that has come back from the laboratory and not yet been
                  marked reviewed. The oldest wait shows how long the longest-unread
                  result has been sitting. Marking a result reviewed is the accountable
                  act (ADR 0012).
                </p>
              </section>
            )}

            {/* Task Completion */}
            {taskCompletion && (
              <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h3 className="text-title-3-medium text-text-primary">Task Completion</h3>
                  <p className="text-caption-1-regular text-text-secondary">
                    {taskCompletion.raised} task{plural(taskCompletion.raised, "", "s")} raised in the last{" "}
                    {periodDays} day{plural(periodDays, "", "s")}
                  </p>
                </div>
                <dl className="flex flex-wrap gap-6">
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Raised</dt>
                    <dd className={cx("text-title-1-medium text-text-primary", figureClass)}>
                      {taskCompletion.raised}
                    </dd>
                  </div>
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Completed</dt>
                    <dd className={cx("text-title-1-medium text-status-lime-text", figureClass)}>
                      {taskCompletion.completed} ({taskCompletion.completion_pct}%)
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">marked done</span>
                  </div>
                  <div className="flex min-w-32 flex-col gap-0.5">
                    <dt className={sectionLabelClass}>Outstanding</dt>
                    <dd className={cx("text-title-1-medium text-status-purple-text", figureClass)}>
                      {taskCompletion.raised - taskCompletion.completed}
                    </dd>
                    <span className="text-caption-1-regular text-text-secondary">still open</span>
                  </div>
                </dl>
                <p className="max-w-2xl text-body-2-regular text-text-secondary">
                  Tasks raised by hand or from ward round entries, and those marked
                  done. The completion proportion answers whether the ward is closing
                  the loop on its outstanding work. Overdue tasks are not escalated
                  (ADR 0010).
                </p>
              </section>
            )}
          </>
        )}
      </section>
    </>
  );
}

/** A count with its noun, so "1 dose" never reads as "1 doses". */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}