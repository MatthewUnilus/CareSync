import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type {
  OverrideReason,
  QueueEntry,
  QueueSnapshot,
  UrgencyLevel,
} from "./api";
import { buildIntake, intakeFormValues } from "./intakeForm";
import type { IntakeFormValues } from "./intakeForm";
import { formatArrival, formatWaiting, urgencyClass } from "./queueDisplay";
import { usePolling } from "./usePolling";

/*
 * Refresh mechanism: polling. The board re-reads the Queue every five seconds
 * and whenever the window regains focus, so a change to an Encounter's Final
 * Decision appears without a manual refresh. The same hook drives the
 * Administrator dashboard.
 */
const POLL_INTERVAL_MS = 5_000;

const URGENCY_LEVELS: UrgencyLevel[] = ["High", "Medium", "Low"];

/*
 * The Override form reads the fixed reason list from the API rather than
 * embedding a second copy here. Free text is shown only for "other", matching
 * the server-side rule; the server rejects it for every other reason.
 */
function OverrideAction({
  entry,
  onOverridden,
}: {
  entry: QueueEntry;
  onOverridden: () => void;
}) {
  const [reasons, setReasons] = useState<OverrideReason[]>([]);
  const [finalDecision, setFinalDecision] = useState<UrgencyLevel>(
    entry.urgency_level,
  );
  const [reason, setReason] = useState("");
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .overrideReasons()
      .then((response) => {
        if (active) {
          setReasons(response.reasons);
        }
      })
      .catch(() => {
        if (active) {
          setError("Unable to load the Override reasons.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const machineRecommendation = entry.assessment.machine_recommendation;
  const unchanged = finalDecision === machineRecommendation;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.overrideFinalDecision(entry.encounter_id, {
        assessment_id: entry.assessment.id,
        final_decision: finalDecision,
        reason,
        free_text: reason === "other" ? freeText : null,
      });
      onOverridden();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="queue-override">
      <p className="queue-detail-label">Override</p>
      <p className="muted">
        Machine Recommendation: <strong>{machineRecommendation}</strong>. An
        Override changes the Final Decision and keeps the recommendation on
        record.
      </p>
      {entry.assessment.override ? (
        <p className="muted">
          Final Decision set by{" "}
          {entry.assessment.override.performed_by.display_name} —{" "}
          {entry.assessment.override.reason}
          {entry.assessment.override.free_text
            ? `: ${entry.assessment.override.free_text}`
            : "."}
        </p>
      ) : null}
      <form className="queue-override-form" onSubmit={submit}>
        <label>
          Final Decision
          <select
            value={finalDecision}
            onChange={(event) =>
              setFinalDecision(event.target.value as UrgencyLevel)
            }
          >
            {URGENCY_LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reason
          <select
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
          >
            <option value="">Select a reason</option>
            {reasons.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        {reason === "other" ? (
          <label>
            Other reason
            <textarea
              value={freeText}
              onChange={(event) => setFreeText(event.target.value)}
              rows={3}
              maxLength={2000}
            />
          </label>
        ) : null}
        {unchanged ? (
          <p className="muted">
            Choose a decision different from the Machine Recommendation.
          </p>
        ) : null}
        {error ? (
          <p className="notice notice-error" role="status">
            {error}
          </p>
        ) : null}
        <div className="row">
          <button
            type="submit"
            disabled={saving || reason === "" || unchanged}
          >
            {saving ? "Saving…" : "Override"}
          </button>
        </div>
      </form>
    </div>
  );
}

/*
 * The Departure action is its own component and handler, self-contained so
 * that another action (the Re-assessment ticket) can sit beside it without
 * touching it. It sends no body: the server records the departure instant.
 */
function DepartureAction({
  entry,
  onDeparted,
}: {
  entry: QueueEntry;
  onDeparted: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function depart() {
    setSaving(true);
    setError(null);
    try {
      await api.departEncounter(entry.encounter_id);
      onDeparted();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="queue-departure">
      <p className="muted">
        Departing records the departure instant and removes this Encounter from
        the awaiting board. The Patient, Assessments and Overrides stay on
        record.
      </p>
      {error ? (
        <p className="notice notice-error" role="status">
          {error}
        </p>
      ) : null}
      <div className="row">
        <button
          type="button"
          className="secondary"
          onClick={() => {
            void depart();
          }}
          disabled={saving}
        >
          {saving ? "Departing…" : "Depart"}
        </button>
      </div>
    </div>
  );
}

/*
 * Re-assessment is its own component, beside Override and Departure and
 * touching neither. It sends the Encounter's current intake, prefilled from
 * what the card already shows, and the server appends a new Triage Assessment.
 * The form resets when a new Assessment arrives, so the next one starts from
 * the condition that now governs.
 */
function ReassessmentAction({
  entry,
  onReassessed,
}: {
  entry: QueueEntry;
  onReassessed: () => void;
}) {
  const [form, setForm] = useState<IntakeFormValues>(() =>
    intakeFormValues(entry.intake),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const assessmentId = entry.assessment.id;
  useEffect(() => {
    setForm(intakeFormValues(entry.intake));
    // Only a new governing Assessment resets the form; polling the same card
    // must not overwrite what the user is typing.
  }, [assessmentId]);

  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.reassessEncounter(entry.encounter_id, buildIntake(form));
      onReassessed();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="queue-reassessment">
      <p className="queue-detail-label">Re-assessment</p>
      <p className="muted">
        Capture the Encounter&rsquo;s current condition and run the engine
        again. This appends a new Triage Assessment; the earlier ones, with
        their Overrides, stay on record, and the newest Final Decision governs
        the Queue.
      </p>
      <form className="stack" onSubmit={submit}>
        <fieldset className="intake-fieldset">
          <legend>Current intake</legend>
          <div className="intake-grid">
            <label className="span-all">
              Presenting complaint <span className="required-mark">*</span>
              <textarea
                required
                rows={2}
                value={form.complaint}
                onChange={(event) => update("complaint", event.target.value)}
              />
            </label>
            <label>
              Pain level (1–10) <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={1}
                max={10}
                step={1}
                value={form.painLevel}
                onChange={(event) => update("painLevel", event.target.value)}
              />
            </label>
            <label>
              Illness duration (hours) <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={0}
                max={8760}
                step={0.5}
                inputMode="decimal"
                value={form.durationHours}
                onChange={(event) => update("durationHours", event.target.value)}
              />
            </label>
            <label>
              Temperature (°C) <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={30}
                max={45}
                step={0.1}
                inputMode="decimal"
                value={form.temperatureC}
                onChange={(event) => update("temperatureC", event.target.value)}
              />
            </label>
            <label>
              Heart rate (bpm) <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={20}
                max={300}
                step={1}
                inputMode="numeric"
                value={form.heartRate}
                onChange={(event) => update("heartRate", event.target.value)}
              />
            </label>
            <label>
              Blood pressure systolic <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={50}
                max={300}
                step={1}
                inputMode="numeric"
                value={form.systolic}
                onChange={(event) => update("systolic", event.target.value)}
              />
            </label>
            <label>
              Blood pressure diastolic <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={20}
                max={200}
                step={1}
                inputMode="numeric"
                value={form.diastolic}
                onChange={(event) => update("diastolic", event.target.value)}
              />
            </label>
            <label>
              Oxygen saturation (%) <span className="required-mark">*</span>
              <input
                type="number"
                required
                min={50}
                max={100}
                step={1}
                inputMode="numeric"
                value={form.oxygenSaturation}
                onChange={(event) =>
                  update("oxygenSaturation", event.target.value)
                }
              />
            </label>
            <label className="span-all">
              Notes (optional)
              <textarea
                rows={2}
                value={form.notes}
                onChange={(event) => update("notes", event.target.value)}
              />
            </label>
          </div>
        </fieldset>
        {error ? (
          <p className="notice notice-error" role="status">
            {error}
          </p>
        ) : null}
        <div className="row">
          <button type="submit" disabled={saving}>
            {saving ? "Re-assessing…" : "Re-assess"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ExpandedDetail({
  entry,
  onOverridden,
  onDeparted,
  onReassessed,
}: {
  entry: QueueEntry;
  onOverridden: () => void;
  onDeparted: () => void;
  onReassessed: () => void;
}) {
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
        {entry.assessment.unclassified ? (
          <p className="notice notice-warning">
            This complaint matched no Symptom Group and the fallback provider
            was unavailable or timed out. The recommendation came from the
            safety layer&rsquo;s default level. Review it before relying on it.
          </p>
        ) : null}
      </div>

      <div>
        <p className="queue-detail-label">Notes</p>
        <p className={intake.notes ? undefined : "muted"}>
          {intake.notes ?? "No notes recorded."}
        </p>
      </div>

      <div>
        <p className="queue-detail-label">Actions</p>
        <OverrideAction entry={entry} onOverridden={onOverridden} />
        <ReassessmentAction entry={entry} onReassessed={onReassessed} />
        <DepartureAction entry={entry} onDeparted={onDeparted} />
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
                    {entry.override_flag ? (
                      <span
                        className="queue-flag queue-flag-override"
                        title={`Final Decision ${entry.assessment.final_decision} differs from Machine Recommendation ${entry.assessment.machine_recommendation}`}
                      >
                        Override
                      </span>
                    ) : null}
                    {entry.unclassified_flag ? (
                      <span
                        className="queue-flag queue-flag-unclassified"
                        title="No Symptom Group matched and the fallback provider was unavailable or timed out; this recommendation came from the safety layer's default and needs review."
                      >
                        Unclassified
                      </span>
                    ) : null}
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
                {expanded ? (
                  <ExpandedDetail
                    entry={entry}
                    onOverridden={() => {
                      void load();
                    }}
                    onDeparted={() => {
                      void load();
                    }}
                    onReassessed={() => {
                      void load();
                    }}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
