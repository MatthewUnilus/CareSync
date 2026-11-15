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
  Intake,
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
  abnormalVitalFields,
  formatArrival,
  formatArrivalFull,
  formatWaiting,
  formatWaitingLong,
  urgencyBadgeClass,
  urgencyBorderClass,
  waitBand,
  waitBandLabel,
  waitTextClass,
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
          triggerClassName="min-h-11"
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
          triggerClassName="min-h-11"
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
          <Button
            type="submit"
            className="min-h-11"
            disabled={saving || reason === "" || unchanged}
          >
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
          className="min-h-11"
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
          <Button type="submit" className="min-h-11" disabled={saving}>
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
  const redFlags = entry.assessment.red_flags ?? [];
  const abnormal = abnormalVitalFields(redFlags);

  /*
   * A vital is rendered as an ordinary reading, or as a marked one when a red
   * flag keyed on it. The marking is derived from the server's rules, so the
   * value highlighted is exactly the value the recommendation turned on.
   */
  const Vital = ({
    label,
    field,
    value,
  }: {
    label: string;
    field: keyof Intake | "blood_pressure";
    value: string;
  }) => {
    const flagged = abnormal.has(field);
    return (
      <div>
        <dt className={sectionLabelClass}>{label}</dt>
        <dd
          className={cx(
            "text-body-medium",
            figureClass,
            flagged
              ? "text-body-semibold text-status-rose-text"
              : "text-text-primary",
          )}
        >
          {value}
          {flagged ? (
            <span className="ms-1 text-caption-1-semibold">abnormal</span>
          ) : null}
        </dd>
      </div>
    );
  };

  return (
    <div className="col-span-full flex flex-col gap-5 border-t border-separator-border pt-5">
      {redFlags.length > 0 ? (
        <div className="flex flex-col gap-2 rounded-2xl border border-status-rose-text/30 p-4">
          <p className={cx(sectionLabelClass, "text-status-rose-text")}>
            Why this is {entry.urgency_level}
          </p>
          <ul className="flex flex-col gap-2">
            {redFlags.map((flag) => (
              <li key={flag.id} className="flex flex-col gap-0.5">
                <span className="text-body-medium text-text-primary">
                  {flag.finding}
                </span>
                {/* The citation is the evidence, so it must stay readable
                    rather than fading into the surface. */}
                <span className="text-caption-1-regular text-text-secondary">
                  {flag.citation}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <dl className="grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-x-4 gap-y-3">
        <Vital
          label="Temperature"
          field="temperature_c"
          value={`${intake.temperature_c} °C`}
        />
        <Vital
          label="Heart rate"
          field="heart_rate_bpm"
          value={`${intake.heart_rate_bpm} bpm`}
        />
        <Vital
          label="Blood pressure"
          field="blood_pressure"
          value={`${intake.blood_pressure.systolic}/${intake.blood_pressure.diastolic}`}
        />
        <Vital
          label="Oxygen saturation"
          field="oxygen_saturation_percent"
          value={`${intake.oxygen_saturation_percent}%`}
        />
        <Vital label="Pain level" field="pain_level" value={`${intake.pain_level} / 10`} />
        <Vital
          label="Illness duration"
          field="illness_duration_hours"
          value={`${intake.illness_duration_hours} h`}
        />
        <div>
          <dt className={sectionLabelClass}>Arrived</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {formatArrivalFull(entry.arrived_at)}
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Waiting</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            {formatWaitingLong(entry.waiting_seconds)}
          </dd>
        </div>
        <div>
          <dt className={sectionLabelClass}>Patient</dt>
          <dd className={cx("text-body-medium text-text-primary", figureClass)}>
            age {entry.patient.age} ·{" "}
            {entry.patient.sex === "unspecified"
              ? "sex not recorded"
              : entry.patient.sex}
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
          {/*
           * The ordering rule is stated because it is not self-evident from the
           * board: a long-waiting Low can sit below a shorter-waiting Medium,
           * which reads as a bug unless the rule is spelled out. The board
           * escalates the *display* of a long wait without ever reordering on
           * it — the spec puts time-based escalation of the decision out of
           * scope, so the honest thing is to show the rule and the overdue wait
           * side by side.
           */}
          {entries.length > 1 ? (
            <p className="mt-1 max-w-2xl text-body-2-regular text-text-secondary">
              Ordered by urgency, then arrival within a level. Long waits are
              highlighted but do not change this order.
            </p>
          ) : null}
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
        <p className={mutedTextClass}>
          Open an encounter from the intake screen and it will appear here
        </p>
      ) : null}

      {entries.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {entries.map((entry) => {
            const expanded = expandedId === entry.encounter_id;
            const band = waitBand(entry.waiting_seconds);
            const bandLabel = waitBandLabel(band, entry.waiting_seconds);
            const redFlags = entry.assessment.red_flags ?? [];
            const urgentWait = band === "breach" || band === "critical";
            return (
              <li
                key={entry.encounter_id}
                className={cx(
                  "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-3 rounded-2xl border border-l-4 bg-background-primary-default p-4 max-sm:grid-cols-1",
                  urgencyBorderClass(entry.urgency_level),
                  /*
                   * An escalated wait is carried by the 4px urgency band, the
                   * enlarged rose figure and its "escalate" label. The card
                   * surface deliberately stays white: tinting it measurably
                   * lowers the contrast of every other word on the card, and
                   * the wait is already the loudest thing here.
                   */
                  urgentWait
                    ? "border-status-rose-text"
                    : "border-border-button-default",
                )}
              >
                <div className="flex min-w-0 flex-col gap-2">
                  {/*
                   * Row one is the scan line: urgency badge, patient, then the
                   * flags. The waiting figure is deliberately NOT here — it
                   * moves to its own block so it can grow when it escalates
                   * without reflowing the identity of the patient.
                   */}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span
                      className={cx(
                        "rounded-md px-2 py-0.5 text-body-semibold",
                        urgencyBadgeClass(entry.urgency_level),
                      )}
                    >
                      {entry.urgency_level}
                    </span>
                    <span className="text-headline-semibold text-text-primary">
                      {entry.patient.full_name}
                    </span>
                    <span
                      className={cx(
                        "text-body-2-regular text-text-secondary",
                        figureClass,
                      )}
                    >
                      {entry.patient.age}
                      {entry.patient.sex === "female"
                        ? "F"
                        : entry.patient.sex === "male"
                          ? "M"
                          : ""}
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
                    {redFlags.length > 0 ? (
                      <Chip
                        variant="caption"
                        color="rose"
                        title={redFlags
                          .map((flag) => flag.finding)
                          .join(" · ")}
                      >
                        {redFlags.length} red flag
                        {redFlags.length === 1 ? "" : "s"}
                      </Chip>
                    ) : null}
                  </div>

                  {/*
                   * The waiting figure is the loudest thing on the card once it
                   * leaves the routine band. It is the fact that changes while
                   * nobody is watching, and the reason a board exists.
                   */}
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span
                      className={cx("tabular-nums", waitTextClass(band))}
                      title={`Waiting ${formatWaiting(entry.waiting_seconds)}`}
                    >
                      {formatWaitingLong(entry.waiting_seconds)}
                    </span>
                    {bandLabel ? (
                      <span
                        className={cx(
                          "text-body-2-semibold",
                          urgentWait
                            ? "text-status-rose-text"
                            : "text-status-yellow-text",
                        )}
                      >
                        {bandLabel}
                      </span>
                    ) : (
                      <span className="text-body-2-regular text-text-secondary">
                        waiting · arrived {formatArrival(entry.arrived_at)}
                      </span>
                    )}
                  </div>

                  <p className="line-clamp-2 wrap-anywhere text-body-regular text-text-primary">
                    {entry.intake.presenting_complaint}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  className="min-h-11 max-sm:justify-self-start"
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
