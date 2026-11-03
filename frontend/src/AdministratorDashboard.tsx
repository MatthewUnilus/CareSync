import { useCallback, useState } from "react";

import { api, ApiError } from "./api";
import type { AdministratorQueueSnapshot } from "./api";
import AdministratorReports from "./AdministratorReports";
import { formatWaiting, urgencyClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 5_000;

export default function AdministratorDashboard() {
  const [snapshot, setSnapshot] = useState<AdministratorQueueSnapshot | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const next = await api.administratorQueue();
      setSnapshot(next);
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

  usePolling(load, POLL_INTERVAL_MS);

  const entries = snapshot?.entries ?? [];

  return (
    <>
      <section className="card admin-queue">
        <div className="queue-header">
          <div>
            <h2>Queue overview</h2>
            <p className="muted">
              {entries.length === 0
                ? "No Encounters awaiting"
                : `${entries.length} awaiting`}{" "}
              · updates every 5 seconds
            </p>
          </div>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              void load();
            }}
          >
            Refresh now
          </button>
        </div>

        {error ? (
          <p className="notice notice-error" role="status">
            {error}
          </p>
        ) : null}

        {loading && snapshot === null ? (
          <p className="muted">Loading the Queue…</p>
        ) : null}

        {!loading && entries.length === 0 ? (
          <p className="muted">No Encounters are awaiting.</p>
        ) : null}

        {entries.length > 0 ? (
          <div className="admin-table-wrap">
            <table className="admin-queue-table">
              <caption className="admin-table-caption">
                Awaiting Encounters in Queue order: Urgency Level, then arrival
              </caption>
              <thead>
                <tr>
                  <th scope="col">Urgency</th>
                  <th scope="col">Patient</th>
                  <th scope="col">Complaint</th>
                  <th scope="col">Waiting</th>
                  <th scope="col">Decision vs recommendation</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.encounter_id}>
                    <td>
                      <span
                        className={`urgency-badge ${urgencyClass(entry.urgency_level)}`}
                      >
                        {entry.urgency_level}
                      </span>
                    </td>
                    <td
                      className="admin-patient"
                      title={`Encounter #${entry.encounter_id}`}
                    >
                      {entry.patient_name}
                    </td>
                    <td className="admin-complaint">
                      <span title={entry.presenting_complaint}>
                        {entry.presenting_complaint}
                      </span>
                    </td>
                    <td className="admin-waiting">
                      {formatWaiting(entry.waiting_seconds)}
                    </td>
                    <td>
                      {entry.final_decision_differs ? (
                        <span
                          className="decision-flag decision-differs"
                          title={`Machine Recommendation ${entry.machine_recommendation}; Final Decision ${entry.final_decision}`}
                        >
                          Differs: {entry.machine_recommendation} →{" "}
                          {entry.final_decision}
                        </span>
                      ) : (
                        <span
                          className="decision-flag decision-same"
                          title={`Machine Recommendation and Final Decision are both ${entry.final_decision}`}
                        >
                          Same
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section
        className="card admin-reports"
        id="reports"
        data-reports-mount="administrator"
      >
        <h2>Reports</h2>
        <AdministratorReports />
      </section>
    </>
  );
}
