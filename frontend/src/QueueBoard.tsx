import { useCallback, useState } from "react";

import { api, ApiError } from "./api";
import type { QueueEntry, QueueSnapshot } from "./api";
import { formatArrival, formatWaiting, urgencyClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

/*
 * Refresh mechanism: polling. The board re-reads the Queue every five seconds
 * and whenever the window regains focus, so a change to an Encounter's Final
 * Decision appears without a manual refresh. The same hook drives the
 * Administrator dashboard.
 */
const POLL_INTERVAL_MS = 5_000;

function ExpandedDetail({ entry }: { entry: QueueEntry }) {
  const { intake } = entry;
  const symptomGroups = entry.assessment.recognised_symptom_groups;

  return (
    <div className="queue-detail">
      <dl className="facts">
        <div>
          <dt>Temperature</dt>
          <dd>{intake.temperature_c} °C</dd>
        </div>
        <div>
          <dt>Heart rate</dt>
          <dd>{intake.heart_rate_bpm} bpm</dd>
        </div>
        <div>
          <dt>Blood pressure</dt>
          <dd>
            {intake.blood_pressure.systolic}/{intake.blood_pressure.diastolic}
          </dd>
        </div>
        <div>
          <dt>Oxygen saturation</dt>
          <dd>{intake.oxygen_saturation_percent}%</dd>
        </div>
        <div>
          <dt>Pain level</dt>
          <dd>{intake.pain_level} / 10</dd>
        </div>
        <div>
          <dt>Illness duration</dt>
          <dd>{intake.illness_duration_hours} h</dd>
        </div>
        <div>
          <dt>Arrived</dt>
          <dd>{formatArrival(entry.arrived_at)}</dd>
        </div>
        <div>
          <dt>Encounter</dt>
          <dd>#{entry.encounter_id}</dd>
        </div>
      </dl>

      <div>
        <p className="queue-detail-label">Symptom Groups</p>
        {symptomGroups.length > 0 ? (
          <ul className="symptom-groups">
            {symptomGroups.map((group) => (
              <li key={group} className="symptom-group">
                {group}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">None recognised from the complaint text.</p>
        )}
      </div>

      <div>
        <p className="queue-detail-label">Notes</p>
        <p className={intake.notes ? undefined : "muted"}>
          {intake.notes ?? "No notes recorded."}
        </p>
      </div>

      <div>
        <p className="queue-detail-label">Actions</p>
        <p className="muted">No actions are available for this Encounter yet.</p>
      </div>
    </div>
  );
}

export default function QueueBoard() {
  const [snapshot, setSnapshot] = useState<QueueSnapshot | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const next = await api.queue();
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
    <section className="card queue-board">
      <div className="queue-header">
        <div>
          <h2>Queue</h2>
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
        <p className="muted">
          Open an Encounter from the intake screen and it will appear here.
        </p>
      ) : null}

      {entries.length > 0 ? (
        <ul className="queue-list">
          {entries.map((entry) => {
            const expanded = expandedId === entry.encounter_id;
            return (
              <li
                key={entry.encounter_id}
                className={`queue-card ${urgencyClass(entry.urgency_level)}`}
              >
                <div className="queue-card-main">
                  <div className="queue-card-heading">
                    <span
                      className={`urgency-badge ${urgencyClass(entry.urgency_level)}`}
                    >
                      {entry.urgency_level}
                    </span>
                    <span className="queue-name">{entry.patient.full_name}</span>
                    <span
                      className="queue-waiting"
                      title={`Waiting ${formatWaiting(entry.waiting_seconds)}`}
                    >
                      {formatWaiting(entry.waiting_seconds)}
                    </span>
                  </div>
                  <p className="queue-complaint">
                    {entry.intake.presenting_complaint}
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary queue-expand"
                  aria-expanded={expanded}
                  onClick={() =>
                    setExpandedId(expanded ? null : entry.encounter_id)
                  }
                >
                  {expanded ? "Hide details" : "Show details"}
                </button>
                {expanded ? <ExpandedDetail entry={entry} /> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
