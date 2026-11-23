import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type { AuditEntry } from "./api";
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
import WardOperationsDashboard from "./WardOperationsDashboard";
import { formatInstant } from "./queueDisplay";

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
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [auditFilter, setAuditFilter] = useState("");
  const [auditAppliedFilter, setAuditAppliedFilter] = useState<number | null>(
    null,
  );
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);

  /*
   * Each load claims the next request id as it starts. A resolution writes
   * only if it still owns the latest id, so an earlier request that lands late
   * (the mount load racing a filter load, or a React StrictMode effect replay)
   * cannot overwrite fresher state. Unmounting bumps the id too, invalidating
   * any in-flight request so it drops its writes on a dead tree.
   */
  const auditRequestId = useRef(0);

  const loadAudit = useCallback(async (encounterId: number | null) => {
    const requestId = (auditRequestId.current += 1);
    setAuditLoading(true);
    try {
      const { entries: next } = await api.auditLog(
        encounterId === null ? undefined : encounterId,
      );
      if (auditRequestId.current !== requestId) return;
      setAuditEntries(next);
      setAuditError(null);
    } catch (caught) {
      if (auditRequestId.current !== requestId) return;
      setAuditEntries([]);
      setAuditError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      if (auditRequestId.current === requestId) setAuditLoading(false);
    }
  }, []);

  // Populate the unfiltered log on mount so the card does not sit on its
  // placeholder until the operator submits a filter. The audit log is not
  // polled; later refreshes come only from the filter actions.
  useEffect(() => {
    void loadAudit(null);
    return () => {
      // Invalidate whatever is in flight so it cannot write after unmount or
      // after a StrictMode remount supersedes it.
      auditRequestId.current += 1;
    };
  }, [loadAudit]);

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

  return (
    <>
      <section
        className={cardClass}
        id="reports"
        data-reports-mount="administrator"
      >
        <h2 className="text-title-3-medium text-text-primary">Reports</h2>
        <AdministratorReports />
      </section>

      <WardOperationsDashboard />

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
