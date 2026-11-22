import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type {
  BoardAdmission,
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
}: {
  /** The open Admissions, so a due dose can name where its patient is. */
  admissions: BoardAdmission[];
  /** Bumped by the board when an order is written or stopped, to re-read the list. */
  revision: number;
}) {
  const [day, setDay] = useState(utcDayValue);
  const [doses, setDoses] = useState<MedicationDueDose[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const requestRef = useRef(0);

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
          doses.
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
              </tr>
            </thead>
            <tbody>
              {doses.map((dose) => (
                <tr
                  key={`${dose.order_id}:${dose.due_at}`}
                  className={tableRowClass}
                >
                  <td className={cx(tableCellClass, figureClass)}>
                    <time dateTime={dose.due_at}>
                      {formatUtcInstant(dose.due_at)}
                    </time>
                  </td>
                  <th scope="row" className={cx(tableCellClass, "text-left")}>
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
