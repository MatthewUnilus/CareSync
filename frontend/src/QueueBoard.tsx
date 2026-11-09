import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { RiRefreshLine } from "@remixicon/react";
import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type {
  OverrideReason,
  QueueEntry,
  QueueSnapshot,
  UrgencyLevel,
} from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
} from "./design";
import IntakeFields from "./IntakeFields";
import { buildIntake, intakeFormValues } from "./intakeForm";
import type { IntakeFormValues } from "./intakeForm";
import {
  formatArrival,
  formatWaiting,
  urgencyBorderClass,
  urgencyTextClass,
} from "./queueDisplay";
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
          setError("Unable to load the override reasons.");
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
    <div className="flex flex-col gap-3">
      <p className={sectionLabelClass}>Override</p>
      <p className={mutedTextClass}>
        Machine recommendation:{" "}
        <span className="font-medium text-text-primary">
          {machineRecommendation}
        </span>
        . An override changes the final decision and keeps the recommendation on
        record.
      </p>
      {entry.assessment.override ? (
        <p className={mutedTextClass}>
          Final decision set by{" "}
          {entry.assessment.override.performed_by.display_name} —{" "}
          {entry.assessment.override.reason}
          {entry.assessment.override.free_text
            ? `: ${entry.assessment.override.free_text}`
            : "."}
        </p>
      ) : null}
      <form
        className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] items-end gap-3"
        onSubmit={submit}
      >
        <Select
          label="Final decision"
          selectedKey={finalDecision}
          onSelectionChange={(key) => setFinalDecision(key as UrgencyLevel)}
        >
          {URGENCY_LEVELS.map((level) => (
            <SelectItem key={level} id={level} textValue={level}>
              {level}
            </SelectItem>
          ))}
        </Select>
        <Select
          label="Reason"
          isRequired
          placeholder="Select a reason"
          selectedKey={reason === "" ? null : reason}
          onSelectionChange={(key) => setReason(key === null ? "" : String(key))}
        >
          {reasons.map((value) => (
            <SelectItem key={value} id={value} textValue={value}>
              {value}
            </SelectItem>
          ))}
        </Select>
        {reason === "other" ? (
          <Textarea
            className="col-span-full"
            label="Other reason"
            value={freeText}
            onChange={setFreeText}
            rows={3}
            maxLength={2000}
          />
        ) : null}
        {unchanged ? (
          <p className={`col-span-full ${mutedTextClass}`}>
            Choose a decision different from the machine recommendation
          </p>
        ) : null}
        {error ? (
          <p className={`col-span-full ${noticeClass.error}`} role="status">
            {error}
          </p>
        ) : null}
        <div className="col-span-full">
          <Button type="submit" disabled={saving || reason === "" || unchanged}>
            {saving ? "Saving…" : "Override"}
          </Button>
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
    <div className="flex flex-col gap-3">
      <p className={sectionLabelClass}>Departure</p>
      <p className={mutedTextClass}>
        Departing records the departure instant and removes this encounter from
        the awaiting board. The patient, assessments and overrides stay on
        record.
      </p>
      {error ? (
        <p className={noticeClass.error} role="status">
          {error}
        </p>
      ) : null}
      <div>
        <Button
          variant="secondary"
          disabled={saving}
          onClick={() => {
            void depart();
          }}
        >
          {saving ? "Departing…" : "Depart"}
        </Button>
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
    <div className="flex flex-col gap-3">
      <p className={sectionLabelClass}>Re-assessment</p>
      <p className={mutedTextClass}>
        Capture the encounter&rsquo;s current condition and run the engine
        again. This appends a new triage assessment; the earlier ones, with
        their overrides, stay on record, and the newest final decision governs
        the queue.
      </p>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <IntakeFields
          legend="Current intake"
          form={form}
          onChange={setForm}
        />
        {error ? (
          <p className={noticeClass.error} role="status">
            {error}
          </p>
        ) : null}
        <div>
          <Button type="submit" disabled={saving}>
            {saving ? "Re-assessing…" : "Re-assess"}
          </Button>
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
    <div className="col-span-full flex flex-col gap-5 border-t border-separator-border pt-5">
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-x-4 gap-y-3">
        <div>
          <dt className={sectionLabelClass}>Temperature</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.temperature_c} °C
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Heart rate</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.heart_rate_bpm} bpm
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Blood pressure</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.blood_pressure.systolic}/{intake.blood_pressure.diastolic}
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Oxygen saturation</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.oxygen_saturation_percent}%
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Pain level</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.pain_level} / 10
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Illness duration</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {intake.illness_duration_hours} h
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Arrived</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {formatArrival(entry.arrived_at)}
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Encounter</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            #{entry.encounter_id}
          </dd>
        </div>
      </dl>

      <div className="flex flex-col gap-1">
        <p className={sectionLabelClass}>Symptom groups</p>
        {symptomGroups.length > 0 ? (
          <p className="text-body-regular text-text-primary">
            {symptomGroups.join(" · ")}
          </p>
        ) : (
          <p className={mutedTextClass}>
            None recognised from the complaint text
          </p>
        )}
        {entry.assessment.unclassified ? (
          <p className={noticeClass.warning}>
            This complaint matched no symptom group and the fallback provider
            was unavailable or timed out. The recommendation came from the
            safety layer&rsquo;s default level. Review it before relying on it.
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1">
        <p className={sectionLabelClass}>Notes</p>
        <p
          className={
            intake.notes
              ? "text-body-regular wrap-anywhere text-text-primary"
              : mutedTextClass
          }
        >
          {intake.notes ?? "No notes recorded"}
        </p>
      </div>

      <div className="flex flex-col gap-5 border-t border-separator-border pt-5">
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
    <section className={cardClass}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title-3-medium text-text-primary">Queue</h2>
          <p className={mutedTextClass}>
            {entries.length === 0
              ? "No encounters waiting"
              : `${entries.length} waiting`}{" "}
            · updates every 5 seconds
          </p>
        </div>
        <Button
          variant="secondary"
          size="small"
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
        <p className={mutedTextClass}>
          Open an encounter from the intake screen and it will appear here
        </p>
      ) : null}

      {entries.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {entries.map((entry) => {
            const expanded = expandedId === entry.encounter_id;
            return (
              <li
                key={entry.encounter_id}
                className={cx(
                  "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-3 rounded-2xl border border-l-4 border-border-button-default bg-background-primary-default p-4 max-sm:grid-cols-1",
                  urgencyBorderClass(entry.urgency_level),
                )}
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span
                      className={cx(
                        "text-body-medium font-medium",
                        urgencyTextClass(entry.urgency_level),
                      )}
                    >
                      {entry.urgency_level}
                    </span>
                    <span className="text-body-medium font-medium text-text-primary">
                      {entry.patient.full_name}
                    </span>
                    {entry.override_flag ? (
                      <Chip
                        variant="caption"
                        color="orange"
                        title={`Final decision ${entry.assessment.final_decision} differs from machine recommendation ${entry.assessment.machine_recommendation}`}
                      >
                        Override
                      </Chip>
                    ) : null}
                    {entry.unclassified_flag ? (
                      <Chip
                        variant="caption"
                        color="purple"
                        title="No symptom group matched and the fallback provider was unavailable or timed out; this recommendation came from the safety layer's default and needs review."
                      >
                        Unclassified
                      </Chip>
                    ) : null}
                    <span
                      className={cx(
                        "ml-auto text-body-medium text-text-secondary",
                        figureClass,
                      )}
                      title={`Waiting ${formatWaiting(entry.waiting_seconds)}`}
                    >
                      {formatWaiting(entry.waiting_seconds)}
                    </span>
                  </div>
                  <p className="line-clamp-2 wrap-anywhere text-body-regular text-text-primary">
                    {entry.intake.presenting_complaint}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="small"
                  className="max-sm:justify-self-start"
                  aria-expanded={expanded}
                  onClick={() =>
                    setExpandedId(expanded ? null : entry.encounter_id)
                  }
                >
                  {expanded ? "Hide details" : "Show details"}
                </Button>
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
