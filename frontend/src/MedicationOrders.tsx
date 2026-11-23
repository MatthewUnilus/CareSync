import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import type { ChipColor } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type {
  BoardAdmission,
  MedicationAdministrationGridSlot,
  MedicationAdministrationHistorySlot,
  MedicationAdministrationOutcome,
  MedicationAdministrationPayload,
  MedicationAdministrationReason,
  MedicationDueDose,
  MedicationOrder,
  MedicationOrderPayload,
  MedicationRoundTime,
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
 * Medication orders, round times and the due list (ticket 34, ADR 0011).
 *
 * A Medication Order transcribes a medication instruction a doctor already gave;
 * it is not a prescription. Nothing here calculates a dose, checks a dose against
 * a maximum, or checks an interaction or allergy, because the system holds none
 * of that data. The clinical fields are frozen when the order is written, so a
 * dose change is a stop of the first order and a new order beside it, and both
 * stay in the record. The words are said in the interface too, where a nurse will
 * read them.
 *
 * The round times a frequency maps to are the ward's documented convention,
 * served from one module and shown to the reader rather than assumed, so nobody
 * mistakes the convention for clinical advice. Continuous infusions, variable
 * doses and as-required medication are not covered: the list says so rather than
 * quietly approximating them.
 *
 * The round times are provisional **UTC** clock times (this build carries no
 * ward timezone), so the due list is asked for on a UTC calendar day and its
 * times are shown on the UTC clock and labelled, rather than in the reader's
 * local zone where a dose could appear on a different day than the one asked for.
 *
 * `MedicationDueList` is the cross-patient list — every dose due across the ward
 * in a window, so a nurse does not walk the corridor to find the work. It is
 * mounted once at the board level. `MedicationOrders` is the per-Admission writer
 * and record, mounted from a patient's row. Both are derived from the record on
 * every read and store nothing.
 */

/**
 * The window of one calendar day on the UTC clock, as the due read takes it:
 * `[from, to)` in ISO 8601.
 *
 * The ward's round times are provisional UTC clock times, so a due-list day is a
 * UTC day, not the reader's local day: the bounds are built with `Date.UTC`, so
 * a dose near midnight cannot fall on a different calendar day than the one the
 * reader asked for.
 */
function dayBounds(day: string): { from: string; to: string } {
  const [year, month, date] = day.split("-").map(Number);
  const start = Date.UTC(year, month - 1, date, 0, 0, 0, 0);
  const end = Date.UTC(year, month - 1, date + 1, 0, 0, 0, 0);
  return {
    from: new Date(start).toISOString(),
    to: new Date(end).toISOString(),
  };
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** Today as the day picker's value, `YYYY-MM-DD`, on the UTC clock. */
function utcDayValue(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-${pad(now.getUTCDate())}`;
}

/** The UTC calendar day an instant falls on, `YYYY-MM-DD`. */
function utcDayOf(value: string): string {
  const date = new Date(value);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

/** The UTC clock time an instant falls at, `HH:MM`. */
function utcTimeOf(value: string): string {
  const date = new Date(value);
  return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
}

/** A UTC day shifted by a whole number of days, `YYYY-MM-DD`. */
function shiftDay(day: string, days: number): string {
  const [year, month, date] = day.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, date + days));
  return `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
}

/**
 * Seven UTC calendar days from `weekStart`, as the grid read takes them:
 * `[from, to)` in ISO 8601. A week, like a day, is a UTC week to match the
 * provisional UTC schedule.
 */
function weekBounds(weekStart: string): { from: string; to: string } {
  const [year, month, date] = weekStart.split("-").map(Number);
  const start = Date.UTC(year, month - 1, date, 0, 0, 0, 0);
  const end = Date.UTC(year, month - 1, date + 7, 0, 0, 0, 0);
  return {
    from: new Date(start).toISOString(),
    to: new Date(end).toISOString(),
  };
}

/** A UTC day as a short weekday and date label, for a grid column head. */
function shortDayLabel(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date)).toLocaleDateString(undefined, {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/**
 * An instant as its UTC date and time, with the zone spelled out.
 *
 * The due list is asked for on the UTC clock, so its times are shown on the UTC
 * clock and labelled `UTC`: rendering them in the reader's local zone could put a
 * dose on a different calendar day than the day the list was asked for.
 */
function formatUtcInstant(value: string): string {
  return `${new Date(value).toLocaleString(undefined, {
    timeZone: "UTC",
    dateStyle: "medium",
    timeStyle: "short",
  })} UTC`;
}

/** The current instant as a `datetime-local` value in the reader's timezone. */
function nowValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** A frequency key as its policy label, falling back to the key itself. */
function frequencyLabel(
  roundTimes: MedicationRoundTime[] | null,
  key: string,
): string {
  return roundTimes?.find((frequency) => frequency.key === key)?.label ?? key;
}

/** The round times a frequency maps to, or an empty list when the policy lacks it. */
function frequencyTimes(
  roundTimes: MedicationRoundTime[] | null,
  key: string,
): string[] {
  return roundTimes?.find((frequency) => frequency.key === key)?.times ?? [];
}

/**
 * The fixed outcome set, in the order the record offers them: given first, then
 * the three ways a dose is not given, which are as recordable as giving it.
 */
const OUTCOME_OPTIONS: {
  value: MedicationAdministrationOutcome;
  label: string;
}[] = [
  { value: "given", label: "Given" },
  { value: "withheld", label: "Withheld" },
  { value: "refused", label: "Refused" },
  { value: "unavailable", label: "Unavailable" },
];

/** An outcome as it is shown to a reader. */
function outcomeLabel(outcome: MedicationAdministrationOutcome): string {
  return (
    OUTCOME_OPTIONS.find((option) => option.value === outcome)?.label ?? outcome
  );
}

/**
 * A Chip colour for an outcome or a server state. The server's states are shown
 * as given; this only chooses how they read, and never decides them.
 */
function statusColor(status: string): ChipColor {
  switch (status) {
    case "given":
      return "lime";
    case "withheld":
      return "yellow";
    case "refused":
      return "rose";
    case "overdue":
      return "rose";
    case "due":
      return "yellow";
    case "unavailable":
      return "neutral";
    default:
      return "neutral";
  }
}

/**
 * The ward's frequency-to-round-time convention, shown as a reference so the
 * reader sees the times the due list is derived from. It is the server's policy,
 * not a clinical recommendation.
 */
export function MedicationRoundTimesReference({
  roundTimes,
  roundTimesError,
  onReloadRoundTimes,
}: {
  roundTimes: MedicationRoundTime[] | null;
  roundTimesError: string | null;
  onReloadRoundTimes: () => Promise<void> | void;
}) {
  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">
        Medication round times
      </h3>
      <p className={mutedTextClass}>
        The clock times each frequency maps to, on the UTC clock the provisional
        convention is held on. It is shown so the convention is never mistaken for
        clinical advice; a hospital replaces it in one place.
      </p>
      {roundTimesError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {roundTimesError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void onReloadRoundTimes()}
            >
              Retry loading round times
            </Button>
          </footer>
        </section>
      ) : roundTimes === null ? (
        <p className={mutedTextClass}>Loading round times…</p>
      ) : roundTimes.length === 0 ? (
        <p className={mutedTextClass}>
          No frequency-to-round-time policy is set on this server.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-x-6 gap-y-2">
          {roundTimes.map((frequency) => (
            <li
              key={frequency.key}
              className="flex min-w-0 basis-56 flex-col gap-0.5"
            >
              <p className="text-body-regular text-text-primary">
                {frequency.label}
              </p>
              <p className={cx(sectionLabelClass, figureClass)}>
                {frequency.times.length > 0
                  ? frequency.times.join(" · ")
                  : "no round times set"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Every dose due across the ward in a window, so the work is visible from the
 * board rather than buried in each patient's row.
 *
 * The window is one day, chosen here from client-side date bounds only — no
 * clinical value is interpreted. Doses come from the server already ordered by
 * due time, with the overdue mark made at read time; the client shows the word
 * `overdue` or `due` and never re-derives the boundary. A patient's location on
 * the list is the ward and bed the board already holds, when the patient is on
 * the board.
 */
export function MedicationDueList({
  admissions,
  revision,
  onRecorded,
}: {
  /** The open Admissions, so a due dose can name where its patient is. */
  admissions: BoardAdmission[];
  /** Bumped by the board when an order is written or stopped, to re-read the list. */
  revision: number;
  /** Called after a dose is recorded, so the board's counts and this list refresh. */
  onRecorded: () => Promise<void> | void;
}) {
  const [day, setDay] = useState(utcDayValue);
  const [doses, setDoses] = useState<MedicationDueDose[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // The reason set is the server's and is read, not hard-coded. It is fetched
  // once here and shared by every row's record form.
  const [reasons, setReasons] = useState<MedicationAdministrationReason[] | null>(
    null,
  );
  const [reasonsError, setReasonsError] = useState<string | null>(null);

  // The row whose record form is open, as `orderId:dueAt`, the slot's identity.
  const [recordingKey, setRecordingKey] = useState<string | null>(null);

  const requestRef = useRef(0);
  const reasonsRequestRef = useRef(0);

  const load = useCallback(async (chosenDay: string) => {
    const requestId = ++requestRef.current;
    setLoadError(null);
    try {
      const { from, to } = dayBounds(chosenDay);
      const { doses: loaded } = await api.medicationDue(from, to);
      if (requestRef.current !== requestId) {
        return;
      }
      setDoses(loaded);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, []);

  // Re-read whenever the chosen day or the medication revision changes. The
  // cleanup retires any in-flight read, so a reply for a previous day cannot
  // land under the day now shown.
  useEffect(() => {
    void load(day);
    return () => {
      requestRef.current += 1;
    };
  }, [day, revision, load]);

  const loadReasons = useCallback(async () => {
    const requestId = ++reasonsRequestRef.current;
    setReasonsError(null);
    try {
      const { reasons: loaded } = await api.medicationAdministrationReasons();
      if (reasonsRequestRef.current !== requestId) {
        return;
      }
      setReasons(loaded);
    } catch (caught) {
      if (reasonsRequestRef.current !== requestId) {
        return;
      }
      setReasonsError(errorText(caught));
    }
  }, []);

  // The reason set is a global vocabulary, read once, and again on retry.
  useEffect(() => {
    void loadReasons();
    return () => {
      reasonsRequestRef.current += 1;
    };
  }, [loadReasons]);

  // Where each admission's patient is, as the board holds it.
  const locations = new Map(
    admissions.map((admission) => [admission.id, `${admission.ward} · ${admission.bed}`]),
  );

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">
        Doses due across the ward
      </h3>
      <p className={mutedTextClass}>
        Every dose due across the ward in the chosen UTC day, derived from the
        open orders and the round times each time it is read and stored nowhere.
        It is ordered by due time by the server, and times are shown on the UTC
        clock the round times are held on. An overdue dose is marked and nothing
        else happens: nothing is escalated and no order changes. This list covers
        scheduled orders only — continuous infusions, variable doses and
        as-required medication are not shown here rather than approximated.
      </p>
      <p className="text-body-2-regular text-text-secondary">
        Recording a dose here says what you attest to. There is no barcode or
        wristband verification. A dose given after its due time can still be
        recorded, and the server marks it late; it is never refused.
      </p>

      <Input
        className="w-full sm:w-56"
        label="Day (UTC)"
        type="date"
        value={day}
        onChange={setDay}
      />

      {loadError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void load(day)}
            >
              Retry loading the due list
            </Button>
          </footer>
        </section>
      ) : doses === null ? (
        <p className={mutedTextClass}>Loading the due list…</p>
      ) : doses.length === 0 ? (
        <p className={mutedTextClass}>
          No doses are due in this window. A stopped order produces no further
          doses, and a recorded dose leaves the list.
        </p>
      ) : (
        <section className={tableWrapClass}>
          <table className={tableClass}>
            <caption className={tableCaptionClass}>
              Doses due in the chosen UTC day, ordered by due time; times are
              UTC. A dose is answered on its own row, once per slot.
            </caption>
            <thead>
              <tr>
                <th scope="col" className={tableHeadCellClass}>
                  Due
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Patient
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Location
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Drug
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Dose
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Route
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Status
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {doses.map((dose) => {
                const rowKey = `${dose.order_id}:${dose.due_at}`;
                const open = recordingKey === rowKey;
                return (
                  <Fragment key={rowKey}>
                    <tr className={tableRowClass}>
                      <td className={cx(tableCellClass, figureClass)}>
                        <time dateTime={dose.due_at}>
                          {formatUtcInstant(dose.due_at)}
                        </time>
                      </td>
                      <th
                        scope="row"
                        className={cx(tableCellClass, "text-left")}
                      >
                        {dose.patient.full_name}
                        {dose.patient.hospital_number !== null ? (
                          <>
                            {" · "}
                            <bdi className={figureClass}>
                              {dose.patient.hospital_number}
                            </bdi>
                          </>
                        ) : null}
                      </th>
                      <td className={tableCellClass}>
                        {locations.get(dose.admission_id) ?? "Not on the board"}
                      </td>
                      <td className={tableCellClass}>{dose.drug}</td>
                      <td className={tableCellClass}>{dose.dose}</td>
                      <td className={tableCellClass}>{dose.route}</td>
                      <td className={tableCellClass}>
                        <Chip
                          variant="bold"
                          color={dose.overdue ? "rose" : "yellow"}
                        >
                          {dose.overdue ? "overdue" : "due"}
                        </Chip>
                      </td>
                      <td className={tableCellClass}>
                        <Button
                          variant={open ? "primary" : "secondary"}
                          className="min-h-11"
                          aria-expanded={open}
                          onClick={() => setRecordingKey(open ? null : rowKey)}
                        >
                          {open ? "Cancel" : "Record"}
                        </Button>
                      </td>
                    </tr>
                    {open ? (
                      <tr>
                        <td colSpan={8} className="px-3 pb-4">
                          <RecordAdministrationPanel
                            orderId={dose.order_id}
                            dueAt={dose.due_at}
                            drug={dose.drug}
                            dose={dose.dose}
                            route={dose.route}
                            patientName={dose.patient.full_name}
                            reasons={reasons}
                            reasonsError={reasonsError}
                            onRetryReasons={loadReasons}
                            onRecorded={async () => {
                              setRecordingKey(null);
                              await onRecorded();
                            }}
                            onCancel={() => setRecordingKey(null)}
                          />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </section>
  );
}

/**
 * The form a nurse answers a due dose with: the outcome, the reason where the
 * dose was not given, and a visible confirmation of what will be recorded.
 *
 * The outcome set is fixed: given, withheld, refused or unavailable. No outcome
 * is chosen by default, so a dose is never attested as given by an accidental
 * click; the nurse must pick one, and the confirm cannot proceed until they have.
 * When the outcome is not given a reason is required, chosen from the server's
 * set; free text is offered only for the reason that requires it, so the reason
 * set stays reportable. Nothing is derived here — no clinical judgement is made —
 * and the copy states plainly that the record is what the nurse attests to, with
 * no barcode or wristband verification.
 */
function RecordAdministrationPanel({
  orderId,
  dueAt,
  drug,
  dose,
  route,
  patientName,
  reasons,
  reasonsError,
  onRetryReasons,
  onRecorded,
  onCancel,
}: {
  orderId: number;
  dueAt: string;
  drug: string;
  dose: string;
  route: string;
  patientName: string;
  reasons: MedicationAdministrationReason[] | null;
  reasonsError: string | null;
  onRetryReasons: () => Promise<void> | void;
  onRecorded: () => Promise<void> | void;
  onCancel: () => void;
}) {
  // No outcome is chosen by default: the nurse must pick one explicitly, so a
  // dose is never attested as given by an accidental single click. There is no
  // barcode or wristband verification behind this record, so the choice is the
  // one act that carries the attestation.
  const [outcome, setOutcome] = useState<MedicationAdministrationOutcome | null>(
    null,
  );
  const [reasonKey, setReasonKey] = useState<string | null>(null);
  const [reasonText, setReasonText] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosenReason =
    reasons?.find((reason) => reason.key === reasonKey) ?? null;
  // A reason is needed only once a not-given outcome has been chosen; nothing is
  // needed while no outcome is picked yet.
  const needsReason = outcome !== null && outcome !== "given";
  const chosenOutcomeLabel = outcome === null ? null : outcomeLabel(outcome);

  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (outcome === null) {
      setError("Choose an outcome for this dose.");
      return;
    }
    if (needsReason && chosenReason === null) {
      setError("Choose why the dose was not given.");
      return;
    }
    if (chosenReason?.requires_text && reasonText.trim() === "") {
      setError("Enter the reason text for this reason.");
      return;
    }
    setError(null);
    setConfirming(true);
  }

  async function record() {
    // The confirm step is only reachable once review accepted an outcome; guard
    // here too so the payload can never carry a null outcome.
    if (outcome === null) {
      return;
    }
    const payload: MedicationAdministrationPayload = {
      due_at: dueAt,
      outcome,
      // The reason is recorded only where the dose was not given, and its free
      // text only where the chosen reason requires it.
      reason_key: needsReason && chosenReason !== null ? chosenReason.key : null,
      reason_text:
        needsReason && chosenReason?.requires_text ? reasonText.trim() : null,
    };
    setSaving(true);
    setError(null);
    try {
      await api.recordMedicationAdministration(orderId, payload);
      toast.success(`Dose recorded as ${outcomeLabel(outcome).toLowerCase()}.`);
      await onRecorded();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  if (confirming) {
    return (
      <section className="flex flex-col gap-3 rounded-xl border border-border-button-default bg-background-secondary-default p-4">
        <h5 className="text-body-semibold text-text-primary">
          Confirm this record
        </h5>
        <p className="text-body-2-regular text-text-secondary">
          Record <bdi>{drug}</bdi>{" "}
          <data value={dose} className={figureClass}>
            {dose}
          </data>{" "}
          by {route} for <bdi>{patientName}</bdi>, due{" "}
          <time dateTime={dueAt} className={figureClass}>
            {formatUtcInstant(dueAt)}
          </time>
          , as <strong>{chosenOutcomeLabel?.toLowerCase()}</strong>
          {needsReason && chosenReason !== null ? (
            <>
              {" — "}
              {chosenReason.label}
              {chosenReason.requires_text && reasonText.trim() !== "" ? (
                <>{`: ${reasonText.trim()}`}</>
              ) : null}
            </>
          ) : null}
          .
        </p>
        <p className="text-body-2-regular text-text-secondary">
          This is the record of what you attest to. It is append-only and cannot
          be changed afterwards, and a recorded slot cannot be recorded again.
        </p>

        {error !== null ? (
          <p className={noticeClass.error} role="alert">
            {error}
          </p>
        ) : null}

        <footer className="flex flex-wrap gap-2">
          <Button
            className="min-h-11"
            disabled={saving || outcome === null}
            onClick={() => void record()}
          >
            {saving ? "Recording…" : "Confirm record"}
          </Button>
          <Button
            variant="secondary"
            className="min-h-11"
            disabled={saving}
            onClick={() => setConfirming(false)}
          >
            Back
          </Button>
        </footer>
      </section>
    );
  }

  return (
    <form
      className="flex flex-col gap-3 rounded-xl border border-border-button-default bg-background-secondary-default p-4"
      onSubmit={review}
    >
      <h5 className="text-body-semibold text-text-primary">Record a dose</h5>
      <p className="text-body-2-regular text-text-secondary">
        <bdi>{drug}</bdi>{" "}
        <data value={dose} className={figureClass}>
          {dose}
        </data>{" "}
        by {route} for <bdi>{patientName}</bdi>, due{" "}
        <time dateTime={dueAt} className={figureClass}>
          {formatUtcInstant(dueAt)}
        </time>
        .
      </p>

      <fieldset className="grid min-w-0 gap-3 sm:grid-cols-2">
        <legend className={sectionLabelClass}>Outcome</legend>
        <Select
          label="Outcome"
          className="w-full"
          triggerClassName="min-h-11"
          placeholder="Choose an outcome"
          selectedKey={outcome}
          isDisabled={saving}
          onSelectionChange={(key) => {
            if (typeof key === "string") {
              setOutcome(key as MedicationAdministrationOutcome);
              // A change of outcome resets the reason so a reason for one
              // outcome cannot be carried under another.
              setReasonKey(null);
              setReasonText("");
              setError(null);
            }
          }}
        >
          {OUTCOME_OPTIONS.map((option) => (
            <SelectItem
              key={option.value}
              id={option.value}
              textValue={option.label}
            >
              {option.label}
            </SelectItem>
          ))}
        </Select>

        {needsReason ? (
          <Select
            label="Reason"
            className="w-full"
            triggerClassName="min-h-11"
            placeholder={
              reasonsError !== null
                ? "Reasons unavailable"
                : reasons === null
                  ? "Loading reasons…"
                  : "Choose a reason"
            }
            selectedKey={reasonKey}
            isDisabled={saving || reasons === null}
            onSelectionChange={(key) => {
              if (typeof key === "string") {
                setReasonKey(key);
                setReasonText("");
                setError(null);
              }
            }}
          >
            {(reasons ?? []).map((reason) => (
              <SelectItem
                key={reason.key}
                id={reason.key}
                textValue={reason.label}
              >
                {reason.label}
              </SelectItem>
            ))}
          </Select>
        ) : null}

        {chosenReason?.requires_text ? (
          <Textarea
            rows={2}
            label="Reason text"
            hint="Required for this reason"
            value={reasonText}
            isDisabled={saving}
            onChange={setReasonText}
          />
        ) : null}
      </fieldset>

      {reasonsError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {reasonsError}
          </p>
          <footer>
            <Button
              type="button"
              variant="secondary"
              className="min-h-11"
              onClick={() => void onRetryReasons()}
            >
              Retry loading reasons
            </Button>
          </footer>
        </section>
      ) : null}

      {error !== null ? (
        <p className={noticeClass.error} role="alert">
          {error}
        </p>
      ) : null}

      {outcome === null ? (
        <p className="text-body-2-regular text-text-secondary">
          Choose an outcome to continue. Nothing is recorded as given by
          default.
        </p>
      ) : null}

      <footer className="flex flex-wrap gap-2">
        <Button
          type="submit"
          className="min-h-11"
          disabled={saving || outcome === null}
        >
          Record dose
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="min-h-11"
          disabled={saving}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </footer>
    </form>
  );
}

/**
 * One Admission's administration record in a window: what was due, what
 * happened, when and by whom.
 *
 * This is the patient's own read of the medication record, so a shift can see the
 * doses behind them, not only the ones still outstanding on the board's due list.
 * It is read-only: recording happens on the due list, the nurse's working path.
 * The window is a UTC day to match the schedule, `state` and every time are the
 * server's, and `late` is the server's mark that a dose was recorded after it was
 * due — the client shows the word and derives nothing.
 */
function AdministrationHistory({ admissionId }: { admissionId: number }) {
  const [day, setDay] = useState(utcDayValue);
  const [slots, setSlots] = useState<
    MedicationAdministrationHistorySlot[] | null
  >(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const load = useCallback(
    async (id: number, chosenDay: string) => {
      const requestId = ++requestRef.current;
      setLoadError(null);
      try {
        const { from, to } = dayBounds(chosenDay);
        const { slots: loaded } = await api.admissionMedicationAdministrations(
          id,
          from,
          to,
        );
        if (requestRef.current !== requestId) {
          return;
        }
        setSlots(loaded);
      } catch (caught) {
        if (requestRef.current !== requestId) {
          return;
        }
        setLoadError(errorText(caught));
      }
    },
    [],
  );

  // A change of Admission is a change of patient, so the record is re-read and
  // the previous patient's slots are cleared rather than left under the new one.
  useEffect(() => {
    setSlots(null);
    void load(admissionId, day);
    return () => {
      requestRef.current += 1;
    };
  }, [admissionId, day, load]);

  return (
    <section className="flex flex-col gap-3">
      <h4 className={sectionLabelClass}>Administration record</h4>
      <p className="text-body-2-regular text-text-secondary">
        What was due from this admission&rsquo;s orders, what happened to each
        dose, when and by whom. A dose given after its due time is marked late.
        This is read-only; a dose is answered on the ward&rsquo;s due list. The
        record is what the nurse attested to — there is no barcode or wristband
        verification.
      </p>

      <Input
        className="w-full sm:w-56"
        label="Day (UTC)"
        type="date"
        value={day}
        onChange={setDay}
      />

      {loadError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void load(admissionId, day)}
            >
              Retry loading the record
            </Button>
          </footer>
        </section>
      ) : slots === null ? (
        <p className={mutedTextClass}>Loading the administration record…</p>
      ) : slots.length === 0 ? (
        <p className={mutedTextClass}>
          Nothing was due in this UTC day, or no dose has been recorded yet.
        </p>
      ) : (
        <section className={tableWrapClass}>
          <table className={tableClass}>
            <caption className={tableCaptionClass}>
              Doses due in the chosen UTC day, ordered by due time; times are
              UTC.
            </caption>
            <thead>
              <tr>
                <th scope="col" className={tableHeadCellClass}>
                  Due
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Drug
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Dose
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Route
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  State
                </th>
                <th scope="col" className={tableHeadCellClass}>
                  Recorded
                </th>
              </tr>
            </thead>
            <tbody>
              {slots.map((slot) => (
                <tr key={`${slot.order_id}:${slot.due_at}`} className={tableRowClass}>
                  <td className={cx(tableCellClass, figureClass)}>
                    <time dateTime={slot.due_at}>
                      {formatUtcInstant(slot.due_at)}
                    </time>
                  </td>
                  <td className={tableCellClass}>{slot.drug}</td>
                  <td className={tableCellClass}>{slot.dose}</td>
                  <td className={tableCellClass}>{slot.route}</td>
                  <td className={tableCellClass}>
                    <Chip variant="bold" color={statusColor(slot.state)}>
                      {slot.state}
                    </Chip>
                  </td>
                  <td className={tableCellClass}>
                    {slot.administration !== null ? (
                      <>
                        {slot.administration.outcome === "given" &&
                        slot.administration.late ? (
                          <>
                            <Chip variant="caption" color="soft">
                              late
                            </Chip>
                            {" "}
                          </>
                        ) : null}
                        <time
                          dateTime={slot.administration.recorded_at}
                          className={figureClass}
                        >
                          {formatInstant(slot.administration.recorded_at)}
                        </time>
                        {" by "}
                        <bdi>{slot.administration.actor.display_name}</bdi>
                        {" · "}
                        {outcomeLabel(slot.administration.outcome).toLowerCase()}
                        {slot.administration.reason !== null ? (
                          <>
                            {" · "}
                            {slot.administration.reason.label}
                            {slot.administration.reason.text !== null ? (
                              <>{`: ${slot.administration.reason.text}`}</>
                            ) : null}
                          </>
                        ) : null}
                      </>
                    ) : (
                      "Not recorded"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </section>
  );
}

/**
 * One Admission's medication orders: the writer that transcribes an instruction
 * and the record of what was written.
 *
 * The writer sends the doctor's own words — drug, dose, route, frequency, start
 * time and who instructed it — and the server freezes them. The frequency is
 * chosen from the round-times policy so a due entry can be derived from it. The
 * record shows active and stopped orders alike: a change is a stop and a new
 * order, so both stay visible. Stopping an order asks for confirmation first.
 */
export function MedicationOrders({
  admissionId,
  roundTimes,
  onChanged,
}: {
  admissionId: number;
  /** The ward's frequency-to-round-time policy, or null while it is loading. */
  roundTimes: MedicationRoundTime[] | null;
  onChanged: () => Promise<void> | void;
}) {
  const [orders, setOrders] = useState<MedicationOrder[] | null>(null);
  const [ordersError, setOrdersError] = useState<string | null>(null);

  const [drug, setDrug] = useState("");
  const [dose, setDose] = useState("");
  const [route, setRoute] = useState("");
  const [frequency, setFrequency] = useState<string | null>(null);
  const [startAt, setStartAt] = useState(nowValue);
  const [instructedBy, setInstructedBy] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const load = useCallback(async (id: number) => {
    const requestId = ++requestRef.current;
    setOrdersError(null);
    try {
      const { orders: loaded } = await api.admissionMedicationOrders(id);
      if (requestRef.current !== requestId) {
        return;
      }
      setOrders(loaded);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setOrdersError(errorText(caught));
    }
  }, []);

  // A change of Admission is a change of patient: reset the writer so nothing
  // written for the previous patient survives under the new one, and re-read.
  useEffect(() => {
    setDrug("");
    setDose("");
    setRoute("");
    setFrequency(null);
    setStartAt(nowValue());
    setInstructedBy("");
    setSaveError(null);
    void load(admissionId);
    return () => {
      requestRef.current += 1;
    };
  }, [admissionId, load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = {
      drug: drug.trim(),
      dose: dose.trim(),
      route: route.trim(),
      instructed_by: instructedBy.trim(),
    };
    if (
      !trimmed.drug ||
      !trimmed.dose ||
      !trimmed.route ||
      !trimmed.instructed_by
    ) {
      setSaveError(
        "Enter the drug, dose, route and who instructed the order.",
      );
      return;
    }
    if (frequency === null) {
      setSaveError("Choose the frequency the instruction was given at.");
      return;
    }
    const started = new Date(startAt);
    if (Number.isNaN(started.getTime())) {
      setSaveError("Enter the time the order starts.");
      return;
    }

    const payload: MedicationOrderPayload = {
      ...trimmed,
      frequency,
      start_at: started.toISOString(),
    };
    setSaving(true);
    setSaveError(null);
    try {
      await api.writeMedicationOrder(admissionId, payload);
      toast.success("Medication order transcribed.");
      setDrug("");
      setDose("");
      setRoute("");
      setFrequency(null);
      setStartAt(nowValue());
      setInstructedBy("");
      await load(admissionId);
      // The board's counts and the due list both change with a new order.
      await onChanged();
    } catch (caught) {
      setSaveError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  const selectedTimes = frequency !== null ? frequencyTimes(roundTimes, frequency) : [];

  return (
    <section className={cardClass}>
      <h4 className="text-title-3-medium text-text-primary">
        Medication orders
      </h4>
      <p className={mutedTextClass}>
        Transcribe the doctor&rsquo;s instruction as given. This is a
        transcription, not a prescription: the system does not calculate a dose,
        does not check a dose against a maximum, and does not check interactions
        or allergies. A dose change is a stop and a new order, so both stay in
        the record and the schedule is never rewritten. Continuous infusions,
        variable doses and as-required medication are not covered here.
      </p>

      <form className="flex flex-col gap-4" onSubmit={save}>
        <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2">
          <legend className={sectionLabelClass}>New order</legend>
          <Input
            label="Drug"
            value={drug}
            isDisabled={saving}
            onChange={setDrug}
          />
          <Input
            label="Dose"
            hint="As instructed, e.g. 500 mg"
            value={dose}
            isDisabled={saving}
            onChange={setDose}
          />
          <Input
            label="Route"
            hint="As instructed, e.g. oral"
            value={route}
            isDisabled={saving}
            onChange={setRoute}
          />
          <Select
            label="Frequency"
            className="w-full"
            triggerClassName="min-h-11"
            placeholder={
              roundTimes === null ? "Loading frequencies…" : "Choose a frequency"
            }
            selectedKey={frequency}
            isDisabled={saving || roundTimes === null}
            onSelectionChange={(key) => {
              if (typeof key === "string") {
                setFrequency(key);
              }
            }}
          >
            {(roundTimes ?? []).map((option) => (
              <SelectItem
                key={option.key}
                id={option.key}
                textValue={option.label}
              >
                {option.label} ·{" "}
                {option.times.length > 0
                  ? option.times.join(", ")
                  : "no round times"}
              </SelectItem>
            ))}
          </Select>
          <Input
            label="Starts"
            type="datetime-local"
            value={startAt}
            isDisabled={saving}
            onChange={setStartAt}
          />
          <Input
            label="Instructed by"
            hint="Who gave the instruction, e.g. Dr Okafor"
            value={instructedBy}
            isDisabled={saving}
            onChange={setInstructedBy}
          />
        </fieldset>

        <p className="text-body-2-regular text-text-secondary">
          {frequency !== null ? (
            <>
              {frequencyLabel(roundTimes, frequency)} — round times{" "}
              <data
                value={
                  selectedTimes.length > 0
                    ? selectedTimes.join(" · ")
                    : "none"
                }
                className={figureClass}
              >
                {selectedTimes.length > 0
                  ? selectedTimes.join(" · ")
                  : "none set for this frequency"}
              </data>
              . These are the ward&rsquo;s provisional convention on the UTC
              clock, not clinical advice.
            </>
          ) : roundTimes === null ? (
            "Round times are loading; the frequency can be chosen once they arrive."
          ) : (
            "Choose a frequency to see the round times it maps to."
          )}
        </p>

        {saveError !== null ? (
          <p className={noticeClass.error} role="alert">
            {saveError}
          </p>
        ) : null}

        <footer className="flex flex-wrap gap-2">
          <Button
            type="submit"
            className="min-h-11"
            disabled={saving || roundTimes === null}
          >
            {saving ? "Saving…" : "Transcribe order"}
          </Button>
        </footer>
      </form>

      <section className="flex flex-col gap-3">
        <h4 className={sectionLabelClass}>Recorded orders</h4>
        <p className="text-body-2-regular text-text-secondary">
          Active and stopped orders together, so a change is visible as a stop and
          a new order rather than an edit. A stopped order produces no further
          doses.
        </p>

        {ordersError !== null ? (
          <p className={noticeClass.error} role="alert">
            {ordersError}
          </p>
        ) : null}

        {orders === null ? (
          ordersError !== null ? null : (
            <p className={mutedTextClass}>Loading medication orders…</p>
          )
        ) : orders.length === 0 ? (
          <p className={mutedTextClass}>
            No medication orders recorded for this admission yet.
          </p>
        ) : (
          <ol className="flex flex-col gap-4">
            {orders.map((order) => (
              <OrderRow
                key={order.id}
                order={order}
                roundTimes={roundTimes}
                onStopped={async () => {
                  await load(admissionId);
                  await onChanged();
                }}
              />
            ))}
          </ol>
        )}
      </section>

      <AdministrationHistory admissionId={admissionId} />
    </section>
  );
}

/**
 * A week of one order's doses as a grid: rows are the round times the order's
 * frequency produces, columns are the seven UTC days of the week, and each cell
 * is the state the server gives that slot. It is the shape a medication chart
 * takes on paper and the read ticket 37 prints.
 *
 * The week is a UTC week, like the day the due list is asked for, because the
 * round times are provisional UTC clock times. The rows and columns are grouped
 * from the server's own slot times for display only; `state` and every time are
 * the server's, and `late` is its mark, so no clinical judgement is made here.
 */
function MedicationWeekGrid({ order }: { order: MedicationOrder }) {
  // The week shown, as its first UTC day. It opens on the order's own start week
  // so the chart reads the schedule that was written, and steps a week at a time.
  const [weekStart, setWeekStart] = useState(() => utcDayOf(order.start_at));
  const [slots, setSlots] = useState<MedicationAdministrationGridSlot[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const load = useCallback(async (orderId: number, start: string) => {
    const requestId = ++requestRef.current;
    setLoadError(null);
    try {
      const { from, to } = weekBounds(start);
      const { slots: loaded } = await api.medicationAdministrationGrid(
        orderId,
        from,
        to,
      );
      if (requestRef.current !== requestId) {
        return;
      }
      setSlots(loaded);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    setSlots(null);
    void load(order.id, weekStart);
    return () => {
      requestRef.current += 1;
    };
  }, [order.id, weekStart, load]);

  const days = Array.from({ length: 7 }, (_, index) =>
    shiftDay(weekStart, index),
  );
  const timeKeys =
    slots === null
      ? []
      : [...new Set(slots.map((slot) => utcTimeOf(slot.due_at)))].sort();

  return (
    <section className="flex flex-col gap-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h5 className="text-body-semibold text-text-primary">
          Week grid
        </h5>
        <footer className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            className="min-h-11"
            onClick={() => setWeekStart((current) => shiftDay(current, -7))}
          >
            Previous week
          </Button>
          <Button
            variant="secondary"
            className="min-h-11"
            onClick={() => setWeekStart((current) => shiftDay(current, 7))}
          >
            Next week
          </Button>
        </footer>
      </header>
      <p className="text-body-2-regular text-text-secondary">
        {shortDayLabel(days[0])} to {shortDayLabel(days[6])}, on the UTC clock.
        One cell per round time and day, holding what was due and what happened.
        A dose given after its due time is shown with its state and marked late.
      </p>

      {loadError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void load(order.id, weekStart)}
            >
              Retry loading the week
            </Button>
          </footer>
        </section>
      ) : slots === null ? (
        <p className={mutedTextClass}>Loading the week grid…</p>
      ) : timeKeys.length === 0 ? (
        <p className={mutedTextClass}>
          No doses are scheduled in this week. A stopped order produces no
          further doses.
        </p>
      ) : (
        <section className={tableWrapClass}>
          <table className={tableClass}>
            <caption className={tableCaptionClass}>
              A week of doses for <bdi>{order.drug}</bdi> {order.dose}, one cell
              per round time and UTC day; times are UTC. Each cell holds the
              server&rsquo;s state for that slot.
            </caption>
            <thead>
              <tr>
                <th scope="col" className={tableHeadCellClass}>
                  Time (UTC)
                </th>
                {days.map((day) => (
                  <th key={day} scope="col" className={tableHeadCellClass}>
                    {shortDayLabel(day)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {timeKeys.map((time) => (
                <tr key={time} className={tableRowClass}>
                  <th
                    scope="row"
                    className={cx(tableHeadCellClass, "border-b-0")}
                  >
                    {time}
                  </th>
                  {days.map((day) => {
                    const slot =
                      slots.find(
                        (candidate) =>
                          utcDayOf(candidate.due_at) === day &&
                          utcTimeOf(candidate.due_at) === time,
                      ) ?? null;
                    return (
                      <td
                        key={day}
                        className={cx(
                          tableCellClass,
                          slot === null && "text-text-tertiary",
                        )}
                      >
                        {slot === null ? (
                          "·"
                        ) : (
                          <Chip variant="bold" color={statusColor(slot.state)}>
                            {slot.administration?.outcome === "given" &&
                            slot.administration.late
                              ? `${slot.state} · late`
                              : slot.state}
                          </Chip>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </section>
  );
}

/** One order in the record, with the stop action for an active order. */
function OrderRow({
  order,
  roundTimes,
  onStopped,
}: {
  order: MedicationOrder;
  roundTimes: MedicationRoundTime[] | null;
  onStopped: () => Promise<void> | void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [gridOpen, setGridOpen] = useState(false);

  const active = order.status === "active";

  async function stop() {
    setSaving(true);
    try {
      await api.stopMedicationOrder(order.id);
      toast.success("Medication order stopped.");
      setConfirming(false);
      await onStopped();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className={cx(cardClass, "gap-2")}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h5 className="text-body-semibold text-text-primary">
          {order.drug} ·{" "}
          <data value={order.dose} className={figureClass}>
            {order.dose}
          </data>
        </h5>
        <Chip variant="bold" color={active ? "lime" : "neutral"}>
          {active ? "active" : "stopped"}
        </Chip>
        <Chip variant="caption" color="soft">
          {frequencyLabel(roundTimes, order.frequency)}
        </Chip>
      </header>

      <p className="text-body-2-regular text-text-secondary">
        Route {order.route} · starts{" "}
        <time dateTime={order.start_at} className={figureClass}>
          {formatInstant(order.start_at)}
        </time>
        {order.stopped_at !== null ? (
          <>
            {" · stopped "}
            <time dateTime={order.stopped_at} className={figureClass}>
              {formatInstant(order.stopped_at)}
            </time>
          </>
        ) : null}
      </p>
      <p className="text-body-2-regular text-text-secondary">
        Instructed by <bdi>{order.instructed_by}</bdi>
      </p>

      <footer className="flex flex-wrap gap-2">
        <Button
          variant={gridOpen ? "primary" : "secondary"}
          className="min-h-11"
          aria-expanded={gridOpen}
          onClick={() => setGridOpen((current) => !current)}
        >
          {gridOpen ? "Hide week grid" : "Week grid"}
        </Button>
      </footer>

      {gridOpen ? <MedicationWeekGrid order={order} /> : null}

      {active ? (
        confirming ? (
          <section className="flex flex-wrap items-center gap-2 rounded-3xl border border-border-error-default p-4">
            <p className="text-body-2-regular text-text-secondary">
              Stop <bdi>{order.drug}</bdi>{" "}
              <data value={order.dose} className={figureClass}>
                {order.dose}
              </data>
              ? The order stays in the record and produces no further doses.
            </p>
            <Button
              variant="danger"
              className="min-h-11"
              disabled={saving}
              onClick={() => void stop()}
            >
              {saving ? "Stopping…" : "Confirm stop"}
            </Button>
            <Button
              variant="secondary"
              className="min-h-11"
              disabled={saving}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </Button>
          </section>
        ) : (
          <footer className="flex flex-wrap gap-2">
            <Button
              variant="danger"
              className="min-h-11"
              onClick={() => setConfirming(true)}
            >
              Stop order
            </Button>
          </footer>
        )
      ) : null}
    </li>
  );
}
