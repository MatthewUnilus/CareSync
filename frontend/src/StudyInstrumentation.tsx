import { useEffect, useState } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText, ApiError } from "./api";
import type {
  StudyTaskRunResponse,
} from "./api";
import {
  cardClass,
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
import { formatInstant } from "./queueDisplay";

/**
 * Study Instrumentation (ticket 40).
 *
 * Explicit begin/end/abandon actions for timed study tasks. Only available
 * when the `study_instrumentation_enabled` setting is on. Records an
 * anonymised participant id and task label — never the nurse's identity.
 * Measures the system, not the nurse.
 */
export default function StudyInstrumentation() {
  // null until the first read resolves, so an enabled deployment does not
  // flash the "disabled" panel before the list request returns.
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [runs, setRuns] = useState<StudyTaskRunResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Active run state
  const [activeRun, setActiveRun] = useState<StudyTaskRunResponse | null>(null);
  const [taskLabel, setTaskLabel] = useState("");
  const [participantId, setParticipantId] = useState("");

  const [starting, setStarting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [abandoning, setAbandoning] = useState(false);

  // Read the runs once on mount: a 403 means the instrumentation is off, any
  // other failure is shown as a load error.
  useEffect(() => {
    void loadRuns();
  }, []);

  async function loadRuns() {
    try {
      const { runs: loaded } = await api.listStudyTaskRuns();
      setRuns(loaded);
      setEnabled(true);
      setLoadError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        setEnabled(false);
      } else {
        setLoadError(errorText(caught));
      }
    }
  }

  async function handleStart(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const label = taskLabel.trim();
    const pid = participantId.trim();
    if (!label) {
      toast.error("Enter a task label (e.g. handover_sheet)");
      return;
    }
    if (!pid) {
      toast.error("Enter a participant id (e.g. P01)");
      return;
    }

    setStarting(true);
    try {
      const run = await api.startStudyTaskRun({
        task_label: label,
        participant_id: pid,
      });
      toast.success(`Started run for ${label}`);
      setActiveRun(run);
      setTaskLabel("");
      setParticipantId("");
      await loadRuns();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setStarting(false);
    }
  }

  async function handleEnd() {
    if (!activeRun) return;
    setEnding(true);
    try {
      const run = await api.endStudyTaskRun(activeRun.id, {
        participant_id: activeRun.participant_id,
      });
      toast.success(`Ended run for ${run.task_label}`);
      setActiveRun(null);
      await loadRuns();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setEnding(false);
    }
  }

  async function handleAbandon() {
    if (!activeRun) return;
    setAbandoning(true);
    try {
      const run = await api.abandonStudyTaskRun(activeRun.id, {
        participant_id: activeRun.participant_id,
      });
      toast.success(`Abandoned run for ${run.task_label}`);
      setActiveRun(null);
      await loadRuns();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setAbandoning(false);
    }
  }

  if (enabled === null) {
    return (
      <section className={cardClass}>
        <h3 className="text-title-3-medium text-text-primary">Study Instrumentation</h3>
        <p className={mutedTextClass}>Loading…</p>
      </section>
    );
  }

  if (!enabled) {
    return (
      <section className={cardClass}>
        <h3 className="text-title-3-medium text-text-primary">Study Instrumentation</h3>
        <p className={mutedTextClass}>
          Study instrumentation is <strong>disabled</strong>. Enable it via the
          <code>CARESYNC_STUDY_INSTRUMENTATION_ENABLED=true</code> environment
          variable to surface the timing controls below.
        </p>
        <p className="text-body-2-regular text-text-secondary">
          When enabled, this panel lets a study participant explicitly begin,
          end, or abandon a timed task run. The system records an anonymised
          participant id (e.g. <code>P01</code>) and the task label — never the
          nurse's name or user id. The instrumented figure supports the
          observer's stopwatch; it does not replace it.
        </p>
      </section>
    );
  }

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">Study Instrumentation</h3>
      <p className={mutedTextClass}>
        Explicit timing for study tasks. Records an anonymised participant id and
        task label — never the nurse's identity. Measures the system, not the
        nurse. The instrumented figure supports the observer's stopwatch; it does
        not replace it.
      </p>

      {/* Active run or start form */}
      {activeRun ? (
        <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h4 className="text-body-semibold text-text-primary">Active run</h4>
            <span className={cx("text-title-1-medium", figureClass)}>
              {activeRun.task_label}
            </span>
          </div>
          <dl className="flex flex-wrap gap-6 text-body-2-regular text-text-secondary">
            <div className="flex min-w-32 flex-col gap-0.5">
              <dt className={sectionLabelClass}>Participant</dt>
              <dd className={cx(figureClass, "text-text-primary")}>
                {activeRun.participant_id}
              </dd>
            </div>
            <div className="flex min-w-32 flex-col gap-0.5">
              <dt className={sectionLabelClass}>Started</dt>
              <dd className={cx(figureClass, "text-text-primary")}>
                {formatInstant(activeRun.started_at)}
              </dd>
            </div>
            <div className="flex min-w-32 flex-col gap-0.5">
              <dt className={sectionLabelClass}>Status</dt>
              <dd className={cx(figureClass, "text-text-primary")}>
                {activeRun.status}
              </dd>
            </div>
          </dl>
          <footer className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              className="min-h-11"
              disabled={ending}
              onClick={handleEnd}
            >
              {ending ? "Ending…" : "End run"}
            </Button>
            <Button
              variant="danger"
              className="min-h-11"
              disabled={abandoning}
              onClick={handleAbandon}
            >
              {abandoning ? "Abandoning…" : "Abandon run"}
            </Button>
          </footer>
          <p className="text-body-2-regular text-text-secondary">
            Ending records the completion time. Abandoning marks the run as
            abandoned (e.g. participant interrupted) rather than a very long run.
          </p>
        </section>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={handleStart}>
          <h4 className="text-body-semibold text-text-primary">Start a run</h4>
          <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2">
            <legend className={sectionLabelClass}>New timed task</legend>
            <Input
              label="Task label"
              placeholder="handover_sheet"
              value={taskLabel}
              onChange={setTaskLabel}
              isDisabled={starting}
            />
            <Input
              label="Participant id"
              placeholder="P01"
              value={participantId}
              onChange={setParticipantId}
              isDisabled={starting}
            />
          </fieldset>
          <footer>
            <Button type="submit" className="min-h-11" disabled={starting}>
              {starting ? "Starting…" : "Start run"}
            </Button>
          </footer>
        </form>
      )}

      {/* Runs list / export */}
      {loadError ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void loadRuns()}
            >
              Retry loading runs
            </Button>
          </footer>
        </section>
      ) : runs === null ? (
        <p className={mutedTextClass}>Loading runs…</p>
      ) : runs.length === 0 ? (
        <p className={mutedTextClass}>No study task runs recorded yet.</p>
      ) : (
        <section className="flex flex-col gap-3 border-t border-separator-border pt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h4 className="text-body-semibold text-text-primary">Recorded runs</h4>
            <p className="text-caption-1-regular text-text-secondary">
              {runs.length} run{plural(runs.length, "", "s")} · export for write-up
            </p>
          </div>
          <div className={tableWrapClass}>
            <table className={tableClass}>
              <caption className={tableCaptionClass}>
                Study task runs — measures the system, not the nurse. Interruption
                not accounted for; no participant identity recorded.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className={tableHeadCellClass}>Task</th>
                  <th scope="col" className={tableHeadCellClass}>Participant</th>
                  <th scope="col" className={tableHeadCellClass}>Started</th>
                  <th scope="col" className={tableHeadCellClass}>Ended</th>
                  <th scope="col" className={tableHeadCellClass}>Status</th>
                  <th scope="col" className={tableHeadCellClass}>Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className={tableRowClass}>
                    <td className={cx(tableCellClass, "font-medium text-text-primary")}>
                      {run.task_label}
                    </td>
                    <td className={cx(tableCellClass, "text-text-secondary", figureClass)}>
                      {run.participant_id}
                    </td>
                    <td className={cx(tableCellClass, "text-text-secondary", figureClass)}>
                      {formatInstant(run.started_at)}
                    </td>
                    <td className={cx(tableCellClass, "text-text-secondary", figureClass)}>
                      {run.ended_at ? formatInstant(run.ended_at) : "—"}
                    </td>
                    <td className={tableCellClass}>
                      <span
                        className={cx(
                          "text-caption-1-medium",
                          run.status === "completed"
                            ? "text-status-lime-text"
                            : run.status === "abandoned"
                              ? "text-text-error-primary"
                              : "text-text-secondary",
                        )}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className={cx(tableCellClass, "text-text-secondary", figureClass)}>
                      {run.ended_at
                        ? formatDuration(run.started_at, run.ended_at)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}

/** A count with its noun, so "1 run" never reads as "1 runs". */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}