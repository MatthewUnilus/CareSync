import { useCallback, useState } from "react";
import type { FormEvent } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { TappableInfo } from "@/components/base/utils/tappable-info";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type { AdministratorQueueSnapshot, AuditEntry } from "./api";
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
import { formatInstant, formatWaiting, urgencyTextClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 5_000;

/**
 * The action's human label is served from beside the enum
 * (`backend/app/audit_actions.py`), so the client holds no action-value map of
 * its own: the set grows for the ward work and a second copy here would drift.
 * The log renders `entry.action_label`; `entry.action` stays the machine key.
 */
function actionLabel(entry: AuditEntry): string {
  // The server labels every known action and answers "Unknown action" for an
  // unrecognised value, so this fallback covers only an older server or a
  // missing field. It stands in for the value rather than showing raw
  // snake_case to an administrator.
  return entry.action_label || "Unlabelled action";
}

export default function AdministratorDashboard() {
  const [snapshot, setSnapshot] = useState<AdministratorQueueSnapshot | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [auditFilter, setAuditFilter] = useState("");
  const [auditAppliedFilter, setAuditAppliedFilter] = useState<number | null>(
    null,
  );
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);

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

  const loadAudit = useCallback(async (encounterId: number | null) => {
    setAuditLoading(true);
    try {
      const { entries: next } = await api.auditLog(
        encounterId === null ? undefined : encounterId,
      );
      setAuditEntries(next);
      setAuditError(null);
    } catch (caught) {
      setAuditEntries([]);
      setAuditError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setAuditLoading(false);
    }
  }, []);

  usePolling(load, POLL_INTERVAL_MS);

  function applyAuditFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = auditFilter.trim();
    const parsed = Number(trimmed);
    const valid =
      trimmed !== "" && Number.isInteger(parsed) && parsed > 0
        ? parsed
        : null;
    setAuditAppliedFilter(valid);
    void loadAudit(valid);
  }

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
                        <TappableInfo
                          summary={
                            <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-caption-1-semibold text-status-orange-text bg-status-orange-background">
                              Differs: {entry.machine_recommendation} →{" "}
                              {entry.final_decision}
                            </span>
                          }
                          detail={`Machine recommendation ${entry.machine_recommendation}; final decision ${entry.final_decision}`}
                        />
                      ) : (
                        <TappableInfo
                          summary={
                            <span className="text-caption-1-regular text-text-secondary">
                              Same
                            </span>
                          }
                          detail={`Machine recommendation and final decision are both ${entry.final_decision}`}
                        />
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

      <AuditLogCard
        entries={auditEntries}
        error={auditError}
        loading={auditLoading}
        filter={auditFilter}
        onFilterChange={setAuditFilter}
        onApplyFilter={applyAuditFilter}
        appliedFilter={auditAppliedFilter}
        onClearFilter={() => {
          setAuditFilter("");
          setAuditAppliedFilter(null);
          void loadAudit(null);
        }}
      />
    </>
  );
}

interface AuditLogCardProps {
  entries: AuditEntry[];
  error: string | null;
  loading: boolean;
  filter: string;
  onFilterChange: (value: string) => void;
  onApplyFilter: (event: FormEvent<HTMLFormElement>) => void;
  appliedFilter: number | null;
  onClearFilter: () => void;
}

function AuditLogCard({
  entries,
  error,
  loading,
  filter,
  onFilterChange,
  onApplyFilter,
  appliedFilter,
  onClearFilter,
}: AuditLogCardProps) {
  return (
    <section className={cardClass}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title-3-medium text-text-primary">Audit log</h2>
          <p className={mutedTextClass}>
            Append-only; recorded in the same transaction as the act.
          </p>
        </div>
        <form className="flex items-end gap-2" onSubmit={onApplyFilter}>
          <Input
            label="Encounter #"
            type="text"
            inputMode="numeric"
            className="w-40"
            value={filter}
            onChange={onFilterChange}
            placeholder="All encounters"
          />
          <Button type="submit" variant="secondary" className="min-h-11">
            Filter
          </Button>
          {appliedFilter !== null ? (
            <Button variant="secondary" className="min-h-11" onClick={onClearFilter}>
              Clear
            </Button>
          ) : null}
        </form>
      </div>

      {error ? (
        <p className={noticeClass.error} role="status">
          {error}
        </p>
      ) : null}

      {loading && entries.length === 0 ? (
        <p className={mutedTextClass}>Loading the audit log…</p>
      ) : null}

      {!loading && entries.length === 0 && !error ? (
        <p className={mutedTextClass}>
          {appliedFilter !== null
            ? `No audit entries for encounter #${appliedFilter}`
            : "No audit entries yet"}
        </p>
      ) : null}

      {entries.length > 0 ? (
        <div className={tableWrapClass}>
          <table className={tableClass}>
            <caption className={tableCaptionClass}>
              Clinical mutations, oldest first
              {appliedFilter !== null
                ? `, narrowed to encounter #${appliedFilter}`
                : ""}
            </caption>
            <thead>
              <tr>
                <th scope="col" className={tableHeadCellClass}>
                  Action
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Performed by
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Recorded at
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Encounter
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Detail
                </th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className={tableRowClass}>
                  <td
                    className={cx(
                      tableCellClass,
                      "text-body-medium font-medium whitespace-nowrap text-text-primary",
                    )}
                  >
                    {actionLabel(entry)}
                  </td>
                  <td
                    className={cx(
                      tableCellClass,
                      "whitespace-nowrap text-text-secondary",
                    )}
                  >
                    {entry.actor.display_name}
                  </td>
                  <td
                    className={cx(
                      tableCellClass,
                      "whitespace-nowrap text-text-secondary",
                      figureClass,
                    )}
                  >
                    {formatInstant(entry.recorded_at)}
                  </td>
                  <td className={cx(tableCellClass, "text-text-secondary")}>
                    {entry.encounter_id === null
                      ? "—"
                      : `#${entry.encounter_id}`}
                  </td>
                  <td
                    className={cx(
                      tableCellClass,
                      "max-w-md whitespace-normal text-text-secondary",
                    )}
                  >
                    {entry.detail ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
