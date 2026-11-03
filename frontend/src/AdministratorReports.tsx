import { useCallback, useState } from "react";

import { api, ApiError } from "./api";
import type {
  DailyQueueReport,
  PerformanceReport,
  PriorityDistributionReport,
} from "./api";
import { formatWaiting, urgencyClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

const REPORT_POLL_INTERVAL_MS = 30_000;

interface ReportSet {
  dailyQueue: DailyQueueReport;
  priorityDistribution: PriorityDistributionReport;
  performance: PerformanceReport;
}

function seconds(value: number): string {
  return formatWaiting(Math.round(value));
}

/**
 * The three Activity Reports. Every figure is returned by the server, which
 * derives it on demand from stored records; this component only renders it,
 * so there is nothing to invalidate and no client-side aggregate to drift.
 */
export default function AdministratorReports() {
  const [reports, setReports] = useState<ReportSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [dailyQueue, priorityDistribution, performance] = await Promise.all([
        api.dailyQueueReport(),
        api.priorityDistributionReport(),
        api.performanceReport(),
      ]);
      setReports({ dailyQueue, priorityDistribution, performance });
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
                <dd>{seconds(reports.performance.average_waiting_seconds)}</dd>
                <span className="muted">arrival to departure</span>
              </div>
              <div>
                <dt>Average processing</dt>
                <dd>{seconds(reports.performance.average_processing_seconds)}</dd>
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
