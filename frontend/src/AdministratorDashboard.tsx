import { useCallback, useState } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type { AdministratorQueueSnapshot } from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  tableCaptionClass,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableRowClass,
  tableWrapClass,
} from "./design";
import AdministratorReports from "./AdministratorReports";
import { formatWaiting, urgencyTextClass } from "./queueDisplay";
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
      <section className={cardClass}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-title-3-medium text-text-primary">
              Queue overview
            </h2>
            <p className={mutedTextClass}>
              {entries.length === 0
                ? "No encounters waiting"
                : `${entries.length} waiting`}{" "}
              · updates every 5 seconds
            </p>
          </div>
          <Button
            variant="secondary"
            className="min-h-11"
            leadingIcon={RiRefreshLine}
            onClick={() => {
              void load();
            }}
          >
            Refresh now
          </Button>
        </div>

        {error ? (
          <p className={noticeClass.error} role="status">
            {error}
          </p>
        ) : null}

        {loading && snapshot === null ? (
          <p className={mutedTextClass}>Loading the queue…</p>
        ) : null}

        {!loading && entries.length === 0 ? (
          <p className={mutedTextClass}>No encounters are waiting</p>
        ) : null}

        {entries.length > 0 ? (
          <div className={tableWrapClass}>
            <table className={tableClass}>
              <caption className={tableCaptionClass}>
                Awaiting encounters in queue order: urgency level, then arrival
              </caption>
              <thead>
                <tr>
                  <th scope="col" className={tableHeadCellClass}>
                    Urgency
                  </th>
                  <th scope="col" className={tableHeadCellClass}>
                    Patient
                  </th>
                  <th scope="col" className={tableHeadCellClass}>
                    Complaint
                  </th>
                  <th scope="col" className={tableHeadCellClass}>
                    Waiting
                  </th>
                  <th scope="col" className={tableHeadCellClass}>
                    Decision vs recommendation
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.encounter_id} className={tableRowClass}>
                    <td
                      className={cx(
                        tableCellClass,
                        "text-body-medium font-medium whitespace-nowrap",
                        urgencyTextClass(entry.urgency_level),
                      )}
                    >
                      {entry.urgency_level}
                    </td>
                    <td
                      className={cx(
                        tableCellClass,
                        "font-medium whitespace-nowrap text-text-primary",
                      )}
                      title={`Encounter #${entry.encounter_id}`}
                    >
                      {entry.patient_name}
                    </td>
                    <td
                      className={cx(tableCellClass, "max-w-md truncate")}
                      title={entry.presenting_complaint}
                    >
                      {entry.presenting_complaint}
                    </td>
                    <td
                      className={cx(
                        tableCellClass,
                        "whitespace-nowrap text-text-secondary",
                        figureClass,
                      )}
                    >
                      {formatWaiting(entry.waiting_seconds)}
                    </td>
                    <td className={cx(tableCellClass, "whitespace-nowrap")}>
                      {entry.final_decision_differs ? (
                        <span
                          className="text-caption-1-medium text-status-orange-text"
                          title={`Machine recommendation ${entry.machine_recommendation}; final decision ${entry.final_decision}`}
                        >
                          Differs: {entry.machine_recommendation} →{" "}
                          {entry.final_decision}
                        </span>
                      ) : (
                        <span
                          className="text-caption-1-regular text-text-secondary"
                          title={`Machine recommendation and final decision are both ${entry.final_decision}`}
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
        className={cardClass}
        id="reports"
        data-reports-mount="administrator"
      >
        <h2 className="text-title-3-medium text-text-primary">Reports</h2>
        <AdministratorReports />
      </section>
    </>
  );
}
