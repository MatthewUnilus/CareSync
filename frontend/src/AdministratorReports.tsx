import { useCallback, useState } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { ScrollFade, useScrollFade } from "@/components/foundations/scroll-fade/scroll-fade";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type { DailyVisitsReport, PerformanceReport } from "./api";
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
import { usePolling } from "./usePolling";

const REPORT_POLL_INTERVAL_MS = 30_000;

/*
 * Report section rhythm: hairline-topped blocks inside the Reports card, the
 * same tokens and table shapes throughout. Nothing here softens a number.
 */
const reportsClass = "flex flex-col gap-5";
const reportBlockClass =
  "flex flex-col gap-3 border-t border-separator-border pt-4";
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

interface ReportSet {
  dailyVisits: DailyVisitsReport;
  performance: PerformanceReport;
}

/**
 * The Reports. Every figure is returned by the server, which derives it on
 * demand from stored records; this component only renders it, so there is
 * nothing to invalidate and no client-side aggregate to drift.
 */
export default function AdministratorReports() {
  const [reports, setReports] = useState<ReportSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const performanceFade = useScrollFade();

  const load = useCallback(async () => {
    try {
      const [dailyVisits, performance] = await Promise.all([
        api.dailyVisitsReport(),
        api.performanceReport(),
      ]);
      setReports({ dailyVisits, performance });
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
          className="min-h-11"
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
          <section
            className={reportBlockClass}
            aria-labelledby="daily-visits-report"
          >
            <div className={reportHeaderClass}>
              <h3 id="daily-visits-report" className="text-title-3-medium text-text-primary">
                Daily Visits
              </h3>
              <p className={reportStatNoteClass}>
                UTC day {reports.dailyVisits.day} · arrivals, departures and
                backlog
              </p>
            </div>
            <dl className={reportStatsClass}>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Volume</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyVisits.volume}
                </dd>
                <span className={reportStatNoteClass}>arrived</span>
              </div>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Throughput</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyVisits.throughput}
                </dd>
                <span className={reportStatNoteClass}>departed</span>
              </div>
              <div className={reportStatClass}>
                <dt className={reportStatLabelClass}>Awaiting</dt>
                <dd className={reportStatFigureClass}>
                  {reports.dailyVisits.awaiting}
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
            </dl>
            {reports.performance.entries.length > 0 ? (
              <div className="relative min-h-0">
                <div
                  className={cx(tableWrapClass, "max-h-72 overflow-y-auto")}
                  onScroll={performanceFade.onScroll}
                >
                  <table className={tableClass}>
                    <caption className={tableCaptionClass}>
                      Time waiting for each departed encounter
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col" className={tableHeadCellClass}>
                          Encounter
                        </th>
                        <th scope="col" className={tableHeadCellClass}>
                          Waiting
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
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <ScrollFade progress={performanceFade.progress} surfaceClassName="from-background-primary-default" />
              </div>
            ) : (
              <p className={mutedTextClass}>
                No encounter has departed yet, so there is no waiting time to
                show
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
