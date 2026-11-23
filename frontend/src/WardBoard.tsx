import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import type { ChipColor } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type {
  BoardAdmission,
  Encounter,
  Investigation,
  MedicationRoundTime,
  Observation,
  Patient,
  Task,
} from "./api";
import { PrintSheetLauncher } from "./PrintSheets";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
} from "./design";
import ObservationChart from "./ObservationChart";
import NursingNotes from "./NursingNotes";
import InvestigationWorklists, {
  AdmissionInvestigations,
} from "./Investigations";
import TaskList, { AdmissionTasks } from "./TaskList";
import {
  MedicationDueList,
  MedicationOrders,
  MedicationRoundTimesReference,
} from "./MedicationOrders";
import { formatInstant, sexLabel } from "./queueDisplay";

/**
 * The Ward Board: the ward's working view and the front door for bedside work.
 *
 * Every open Admission is shown with where the patient is, the latest
 * Observation charted for them, and the counts of outstanding work — all
 * tallied from the record. The order is the server's (ADR 0008, the ordering
 * rule in the spec): overdue doses first, then doses due now, then results
 * awaiting review, then open tasks, with bed order breaking ties. The client
 * renders that order and those counts as given and never computes a score, a
 * priority or a re-order of its own.
 *
 * Nothing here is stored: the board is derived on every read, so a figure can
 * never drift from the rows behind it. Each patient's chart is reachable without
 * a search — "View chart" embeds the Observation chart against this Admission,
 * which is the screen the nurse described walking back to the ward for (ticket
 * 30). Admitting, moving a location and discharging all live here, and a
 * discharged stay leaves the board and keeps its history in patient history.
 */
export default function WardBoard() {
  // Null until the first read lands, so a reload after a move or discharge keeps
  // the rows already on screen rather than blanking the board to a spinner.
  const [board, setBoard] = useState<BoardAdmission[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // The ward's frequency-to-round-time policy, read once and shown to the
  // reader. It lives above the rows so every order writer and the due list
  // share the one definition of the convention.
  const [roundTimes, setRoundTimes] = useState<MedicationRoundTime[] | null>(
    null,
  );
  const [roundTimesError, setRoundTimesError] = useState<string | null>(null);
  // Bumped when an order is written or stopped, so the cross-patient due list
  // re-reads rather than showing a schedule from before the change.
  const [medicationRevision, setMedicationRevision] = useState(0);
  // The Admission whose chart is open. One at a time keeps the board a list at
  // a glance rather than a stack of open charts.
  const [openChartId, setOpenChartId] = useState<number | null>(null);
  // The Admission whose nursing notes are open, tracked separately from the
  // chart so a nurse can read the notes beside the vitals or on their own.
  const [openNotesId, setOpenNotesId] = useState<number | null>(null);
  // All investigations across the ward, for the print sheets.
  const [allInvestigations, setAllInvestigations] = useState<Investigation[] | null>(null);
  // All tasks across the ward, for the print sheets.
  const [allTasks, setAllTasks] = useState<Task[] | null>(null);

  // The board the view is allowed to show. Every fetch takes the next token and,
  // once it resolves, writes nothing unless it is still the newest — so a slow
  // reply can never land stale rows after a move or discharge reloaded the board.
  const requestIdRef = useRef(0);
  const roundTimesRequestRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setRefreshing(true);
    try {
      const { admissions } = await api.wardBoard();
      if (requestIdRef.current !== requestId) {
        return;
      }
      setBoard(admissions);
      setLoadError(null);
    } catch (caught) {
      if (requestIdRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    } finally {
      if (requestIdRef.current === requestId) {
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
    };
  }, [load]);

  const loadRoundTimes = useCallback(async () => {
    const requestId = ++roundTimesRequestRef.current;
    setRoundTimesError(null);
    try {
      const { frequencies } = await api.medicationRoundTimes();
      if (roundTimesRequestRef.current !== requestId) {
        return;
      }
      setRoundTimes(frequencies);
    } catch (caught) {
      if (roundTimesRequestRef.current !== requestId) {
        return;
      }
      setRoundTimesError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    void loadRoundTimes();
    return () => {
      roundTimesRequestRef.current += 1;
    };
  }, [loadRoundTimes]);

  // Fetch all investigations across the ward for print sheets.
  const investigationsRequestRef = useRef(0);
  const loadAllInvestigations = useCallback(async () => {
    const requestId = ++investigationsRequestRef.current;
    try {
      const [awaitingReview, awaitingResult] = await Promise.all([
        api.investigationsAwaitingReview(),
        api.investigationsAwaitingResult(),
      ]);
      if (investigationsRequestRef.current !== requestId) {
        return;
      }
      setAllInvestigations([
        ...awaitingReview.investigations,
        ...awaitingResult.investigations,
      ]);
    } catch {
      if (investigationsRequestRef.current !== requestId) {
        return;
      }
      // Error is silently ignored; the print buttons will be disabled until data loads.
    }
  }, []);

  useEffect(() => {
    void loadAllInvestigations();
    return () => {
      investigationsRequestRef.current += 1;
    };
  }, [loadAllInvestigations]);

  // Fetch all tasks across the ward for print sheets.
  const tasksRequestRef = useRef(0);
  const loadAllTasks = useCallback(async () => {
    const requestId = ++tasksRequestRef.current;
    try {
      const { tasks } = await api.wardTasks(false, true); // mine=false, includeDone=true
      if (tasksRequestRef.current !== requestId) {
        return;
      }
      setAllTasks(tasks);
    } catch {
      if (tasksRequestRef.current !== requestId) {
        return;
      }
      // Error is silently ignored; the print buttons will be disabled until data loads.
    }
  }, []);

  useEffect(() => {
    void loadAllTasks();
    return () => {
      tasksRequestRef.current += 1;
    };
  }, [loadAllTasks]);

  // A written or stopped order changes both the board's counts and the due list,
  // so the board is re-read and the list is told the medication view moved on.
  const handleMedicationChanged = useCallback(async () => {
    setMedicationRevision((current) => current + 1);
    await load();
  }, [load]);

  return (
    <>
      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">Ward board</h2>
        <p className={mutedTextClass}>
          Every open Admission on the ward, ordered by outstanding work: overdue
          doses first, then doses due now, then results awaiting review, then
          open tasks, with bed order breaking ties. The order and the counts are
          counted from the record each time this board is read and stored
          nowhere. The board does not score or rank patients clinically.
        </p>

        {board === null ? (
          loadError !== null ? (
            <p className={noticeClass.error} role="alert">
              {loadError}
            </p>
          ) : (
            <p className={mutedTextClass}>Loading the ward board…</p>
          )
        ) : (
          <>
            {/*
             * A reload after a move, discharge or admit keeps the rows on screen
             * and says so, rather than flashing a spinner over the whole board.
             */}
            {refreshing ? (
              <p className={mutedTextClass} role="status">
                Refreshing the board…
              </p>
            ) : null}
            {loadError !== null ? (
              <p className={noticeClass.error} role="alert">
                {loadError}
              </p>
            ) : null}
            {board.length === 0 ? (
              <p className={mutedTextClass}>
                No patients are on the ward board. Admit a patient below to start
                a stay.
              </p>
            ) : (
              <ul className="flex flex-col gap-4">
                {board.map((admission) => (
                  <BoardAdmissionRow
                    key={admission.id}
                    admission={admission}
                    chartOpen={openChartId === admission.id}
                    onToggleChart={() =>
                      setOpenChartId((current) =>
                        current === admission.id ? null : admission.id,
                      )
                    }
                    notesOpen={openNotesId === admission.id}
                    onToggleNotes={() =>
                      setOpenNotesId((current) =>
                        current === admission.id ? null : admission.id,
                      )
                    }
                    roundTimes={roundTimes}
                    onMedicationChanged={handleMedicationChanged}
                    onChanged={load}
                  />
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <MedicationRoundTimesReference
        roundTimes={roundTimes}
        roundTimesError={roundTimesError}
        onReloadRoundTimes={loadRoundTimes}
      />

      <MedicationDueList
        admissions={board ?? []}
        revision={medicationRevision}
        onRecorded={handleMedicationChanged}
      />

      <InvestigationWorklists admissions={board ?? []} onChanged={load} />

      <TaskList admissions={board ?? []} onTasksChanged={load} />

      {board !== null && allInvestigations !== null && allTasks !== null && (
        <PrintSheetLauncher
          admissions={board}
          allInvestigations={allInvestigations}
          allTasks={allTasks}
        />
      )}

      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Admit a patient
        </h2>
        <p className={mutedTextClass}>
          A patient is registered at intake and admitted here. Admitting records
          where they are; linking the visit they were seen in first keeps the
          visit and the stay one history. Leaving the visit unlinked admits them
          directly.
        </p>
        <AdmitSection onAdmitted={load} />
      </section>
    </>
  );
}

/**
 * One open Admission on the board: who and where, the latest Observation for the
 * patient, the outstanding-work counts, and the actions — chart, move and
 * discharge.
 */
function BoardAdmissionRow({
  admission,
  chartOpen,
  onToggleChart,
  notesOpen,
  onToggleNotes,
  roundTimes,
  onMedicationChanged,
  onChanged,
}: {
  admission: BoardAdmission;
  chartOpen: boolean;
  onToggleChart: () => void;
  notesOpen: boolean;
  onToggleNotes: () => void;
  roundTimes: MedicationRoundTime[] | null;
  onMedicationChanged: () => Promise<void> | void;
  onChanged: () => Promise<void> | void;
}) {
  const { patient } = admission;
  // The medication orders are a third disclosure beside the chart and the
  // notes, opened from the row and kept local so the board stays a list.
  const [medicationOpen, setMedicationOpen] = useState(false);
  // The patient's Tasks are a fourth disclosure: raised by hand from their own
  // page, and read back as the record of open and done work.
  const [tasksOpen, setTasksOpen] = useState(false);
  // The patient's Investigations are a fifth disclosure: requested from their
  // own page and followed to their results and review.
  const [investigationsOpen, setInvestigationsOpen] = useState(false);

  // The server's counts, shown as given, in the board's own order: overdue
  // doses, then doses due now, then results awaiting review, then open tasks.
  // A count above zero is tinted so it reads at a glance on a tablet; the
  // number is the record's, not a score.
  const counts: { key: string; label: string; color: ChipColor }[] = [
    {
      key: "overdue",
      label: plural(
        admission.overdue_medication_count,
        "overdue dose",
        "overdue doses",
      ),
      color: admission.overdue_medication_count > 0 ? "rose" : "neutral",
    },
    {
      key: "due",
      label: plural(
        admission.due_medication_count,
        "dose due now",
        "doses due now",
      ),
      color: admission.due_medication_count > 0 ? "yellow" : "neutral",
    },
    {
      key: "outstanding",
      label: plural(
        admission.outstanding_medication_count,
        "outstanding dose",
        "outstanding doses",
      ),
      color: "neutral",
    },
    {
      key: "results",
      label: plural(
        admission.unreviewed_result_count,
        "result to review",
        "results to review",
      ),
      color: admission.unreviewed_result_count > 0 ? "purple" : "neutral",
    },
    {
      key: "tasks",
      label: plural(admission.open_task_count, "open task", "open tasks"),
      color: "neutral",
    },
  ];

  return (
    <li className={cardClass}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-title-3-medium text-text-primary">
          {patient.full_name}
        </h3>
        <p className="text-body-medium text-text-primary">
          Ward{" "}
          <data value={admission.ward} className={figureClass}>
            {admission.ward}
          </data>
          {" · Bed "}
          <data value={admission.bed} className={figureClass}>
            {admission.bed}
          </data>
        </p>
        <p className="basis-full text-body-2-regular text-text-secondary">
          {patient.hospital_number !== null ? (
            <>
              hospital number{" "}
              <data value={patient.hospital_number} className={figureClass}>
                {patient.hospital_number}
              </data>
              {" · "}
            </>
          ) : null}
          age {patient.age} · {sexLabel(patient.sex)}
        </p>
      </header>

      <p className="text-body-2-regular text-text-secondary">
        Admitted{" "}
        <time dateTime={admission.admitted_at} className={figureClass}>
          {formatInstant(admission.admitted_at)}
        </time>
        {admission.encounter_id != null
          ? ` · linked to encounter #${admission.encounter_id}`
          : " · no linked visit"}
      </p>

      <section className="flex flex-col gap-2">
        <h4 className={sectionLabelClass}>Outstanding work</h4>
        <ul className="flex flex-wrap gap-2" aria-label="Outstanding work">
          {counts.map((count) => (
            <li key={count.key}>
              <Chip variant="bold" color={count.color}>
                {count.label}
              </Chip>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h4 className={sectionLabelClass}>Latest observation for this patient</h4>
        {admission.latest_observation !== null ? (
          <LatestObservation observation={admission.latest_observation} />
        ) : (
          <p className={mutedTextClass}>
            No observations charted for this patient yet.
          </p>
        )}
      </section>

      <footer className="flex flex-wrap gap-2">
        <Button
          variant={chartOpen ? "primary" : "secondary"}
          className="min-h-11"
          onClick={onToggleChart}
        >
          {chartOpen ? "Hide chart" : "View chart"}
        </Button>
        <Button
          variant={notesOpen ? "primary" : "secondary"}
          className="min-h-11"
          onClick={onToggleNotes}
        >
          {notesOpen ? "Hide notes" : "Nursing notes"}
        </Button>
        <Button
          variant={medicationOpen ? "primary" : "secondary"}
          className="min-h-11"
          onClick={() => setMedicationOpen((current) => !current)}
        >
          {medicationOpen ? "Hide medication orders" : "Medication orders"}
        </Button>
        <Button
          variant={tasksOpen ? "primary" : "secondary"}
          className="min-h-11"
          onClick={() => setTasksOpen((current) => !current)}
        >
          {tasksOpen ? "Hide tasks" : "Tasks"}
        </Button>
        <Button
          variant={investigationsOpen ? "primary" : "secondary"}
          className="min-h-11"
          onClick={() => setInvestigationsOpen((current) => !current)}
        >
          {investigationsOpen ? "Hide investigations" : "Investigations"}
        </Button>
        <MoveAction admission={admission} onMoved={onChanged} />
        <DischargeAction admission={admission} onDischarged={onChanged} />
      </footer>

      {chartOpen ? (
        <ObservationChart
          patientId={patient.id}
          admissionId={admission.id}
          title={`Vitals for ${patient.full_name}`}
        />
      ) : null}

      {notesOpen ? (
        <NursingNotes admissionId={admission.id} onTasksRaised={onChanged} />
      ) : null}

      {tasksOpen ? (
        <AdmissionTasks admissionId={admission.id} onTasksChanged={onChanged} />
      ) : null}

      {investigationsOpen ? (
        <AdmissionInvestigations
          admissionId={admission.id}
          onInvestigationsChanged={onChanged}
        />
      ) : null}

      {medicationOpen ? (
        <MedicationOrders
          admissionId={admission.id}
          roundTimes={roundTimes}
          onChanged={onMedicationChanged}
        />
      ) : null}
    </li>
  );
}

/**
 * The latest Observation for the patient, wherever it was charted, with the time
 * and actor. The readings are shown as recorded; nothing is scored or escalated
 * (ADR 0010), and the abnormal mark is read from the server's own
 * `abnormal_fields`.
 */
function LatestObservation({ observation }: { observation: Observation }) {
  return (
    <>
      <p className="text-body-2-regular text-text-secondary">
        Charted{" "}
        <time dateTime={observation.taken_at} className={figureClass}>
          {formatInstant(observation.taken_at)}
        </time>{" "}
        by <bdi>{observation.actor.display_name}</bdi>
      </p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Latest readings">
        {readingsFor(observation).map((reading) => (
          <li key={reading.label} className={sectionLabelClass}>
            {reading.label}{" "}
            <data
              value={reading.value}
              className={cx("text-body-regular text-text-primary", figureClass)}
            >
              {reading.value}
            </data>
          </li>
        ))}
      </ul>
      {observation.reference_range_applies === false ? (
        <p className={sectionLabelClass}>
          The adult reference ranges do not apply to this patient.
        </p>
      ) : observation.abnormal_fields.length > 0 ? (
        <p className="text-body-2-regular text-text-secondary">
          {plural(observation.abnormal_fields.length, "reading", "readings")}{" "}
          outside the reference range, marked for display only.
        </p>
      ) : null}
    </>
  );
}

/**
 * Move an Admission's location.
 *
 * The action reads as a plain record until chosen, then opens a small inline
 * form seeded from the current location. The server records the move and the
 * board is re-read, so the location on screen is always the stored one.
 */
function MoveAction({
  admission,
  onMoved,
}: {
  admission: BoardAdmission;
  onMoved: () => Promise<void> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [ward, setWard] = useState(admission.ward);
  const [bed, setBed] = useState(admission.bed);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedWard = ward.trim();
    const trimmedBed = bed.trim();
    if (!trimmedWard || !trimmedBed) {
      toast.error("Enter the ward and the bed or location.");
      return;
    }
    setSaving(true);
    try {
      await api.moveAdmission(admission.id, trimmedWard, trimmedBed);
      toast.success(
        `${admission.patient.full_name} moved to ${trimmedWard} · ${trimmedBed}.`,
      );
      setEditing(false);
      await onMoved();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <Button
        variant="secondary"
        className="min-h-11"
        onClick={() => setEditing(true)}
      >
        Move location
      </Button>
    );
  }

  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={submit}>
      <Input
        className="min-w-0 flex-1 basis-40"
        label="Ward"
        value={ward}
        onChange={setWard}
        isDisabled={saving}
      />
      <Input
        className="min-w-0 flex-1 basis-32"
        label="Bed or location"
        value={bed}
        onChange={setBed}
        isDisabled={saving}
      />
      <Button type="submit" className="min-h-11" disabled={saving}>
        {saving ? "Moving…" : "Save location"}
      </Button>
      <Button
        type="button"
        variant="secondary"
        className="min-h-11"
        disabled={saving}
        onClick={() => {
          setEditing(false);
          setWard(admission.ward);
          setBed(admission.bed);
        }}
      >
        Cancel
      </Button>
    </form>
  );
}

/**
 * Discharge an Admission from the board.
 *
 * Discharging ends the stay: the patient leaves the board and keeps their full
 * history. The action confirms first, naming the patient and the location, then
 * posts the discharge and re-reads the board. The confirm sits inside the row
 * rather than the browser's own dialog, so the decision reads with the patient
 * it concerns.
 */
function DischargeAction({
  admission,
  onDischarged,
}: {
  admission: BoardAdmission;
  onDischarged: () => Promise<void> | void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);

  async function discharge() {
    setSaving(true);
    try {
      await api.dischargeAdmission(admission.id);
      toast.success(`${admission.patient.full_name} discharged.`);
      setConfirming(false);
      await onDischarged();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  if (!confirming) {
    return (
      <Button
        variant="danger"
        className="min-h-11"
        onClick={() => setConfirming(true)}
      >
        Discharge
      </Button>
    );
  }

  return (
    <section className="flex flex-wrap items-center gap-2 rounded-3xl border border-border-error-default bg-background-primary-default p-6">
      <p className="text-body-2-regular text-text-secondary">
        Discharge <bdi>{admission.patient.full_name}</bdi> from{" "}
        {admission.ward} · {admission.bed}? The stay closes and keeps its
        history.
      </p>
      <Button
        variant="danger"
        className="min-h-11"
        disabled={saving}
        onClick={() => void discharge()}
      >
        {saving ? "Discharging…" : "Confirm discharge"}
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
  );
}

/**
 * Find a registered patient and admit them.
 *
 * Search here is discovery, not identity: it offers candidates and a human
 * chooses, the same discipline patient history uses. Once a patient is chosen
 * their visits load, so the stay can be linked to the visit it came from.
 */
function AdmitSection({
  onAdmitted,
}: {
  onAdmitted: () => Promise<void> | void;
}) {
  const [query, setQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState<string | null>(null);
  const [results, setResults] = useState<Patient[]>([]);
  const [searching, setSearching] = useState(false);

  const [selected, setSelected] = useState<Patient | null>(null);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [loadingEncounters, setLoadingEncounters] = useState(false);
  // The patient whose visits the view is allowed to show, so a slow reply for
  // the previous candidate cannot land under a new selection.
  const selectedIdRef = useRef<number | null>(null);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      // An empty query must not become a listing of the whole Patient table.
      setSearchedQuery(null);
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const { patients } = await api.searchPatients(trimmed);
      setResults(patients);
      setSearchedQuery(trimmed);
      selectedIdRef.current = null;
      setSelected(null);
      setEncounters([]);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSearching(false);
    }
  }

  async function choose(patient: Patient) {
    selectedIdRef.current = patient.id;
    setSelected(patient);
    setLoadingEncounters(true);
    try {
      const { encounters } = await api.patientHistory(patient.id);
      if (selectedIdRef.current !== patient.id) {
        return;
      }
      setEncounters(encounters);
    } catch (caught) {
      if (selectedIdRef.current !== patient.id) {
        return;
      }
      toast.error(errorText(caught));
      setEncounters([]);
    } finally {
      if (selectedIdRef.current === patient.id) {
        setLoadingEncounters(false);
      }
    }
  }

  return (
    <>
      <form className="flex flex-wrap items-end gap-2" onSubmit={search}>
        <Input
          className="min-w-0 flex-1 basis-64"
          label="Name, contact number or hospital number"
          placeholder="Ada Lovelace · 07700 900123 · H12345"
          value={query}
          onChange={setQuery}
        />
        <Button type="submit" className="min-h-11" disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </form>

      {searchedQuery === null ? (
        <p className={mutedTextClass}>
          Search for a registered patient to admit.
        </p>
      ) : results.length === 0 ? (
        <p className={mutedTextClass}>
          No patients match &ldquo;{searchedQuery}&rdquo;.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {results.map((patient) => {
            const isSelected = selected?.id === patient.id;
            return (
              <li
                key={patient.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-separator-border bg-background-secondary-default p-4"
              >
                <section className="min-w-0 flex-1 basis-48">
                  <p className="text-body-medium text-text-primary">
                    {patient.full_name}
                  </p>
                  <p className="text-body-2-regular text-text-secondary">
                    age {patient.age} · {sexLabel(patient.sex)} ·{" "}
                    <data
                      value={patient.contact_phone}
                      className={figureClass}
                    >
                      {patient.contact_phone}
                    </data>
                  </p>
                  <p className="text-body-2-regular text-text-secondary">
                    {patient.hospital_number !== null ? (
                      <>
                        Hospital number{" "}
                        <data
                          value={patient.hospital_number}
                          className={figureClass}
                        >
                          {patient.hospital_number}
                        </data>
                      </>
                    ) : (
                      "No hospital number on record"
                    )}
                  </p>
                </section>
                <Button
                  variant={isSelected ? "primary" : "secondary"}
                  className="min-h-11"
                  onClick={() => void choose(patient)}
                >
                  {isSelected ? "Admitting this patient" : "Admit this patient"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      {selected ? (
        <section className={cx(cardClass, "gap-3")}>
          <p className="text-body-medium text-text-primary">
            Admit {selected.full_name}
          </p>
          {loadingEncounters ? (
            <p className={mutedTextClass}>
              Loading this patient&rsquo;s visits…
            </p>
          ) : (
            <AdmitPatientForm
              patient={selected}
              encounters={encounters}
              onAdmitted={async () => {
                selectedIdRef.current = null;
                setSelected(null);
                setResults([]);
                setSearchedQuery(null);
                setQuery("");
                await onAdmitted();
              }}
            />
          )}
        </section>
      ) : null}
    </>
  );
}

/**
 * The admit form: a ward, a bed or location, and an optional linked visit.
 *
 * Shared by the board's admit section and patient history, so admitting a
 * patient reads the same wherever it is started. The visit list is passed in by
 * the caller — the board loads the chosen patient's visits, patient history
 * already holds them — so the form never fetches under its own heading. A
 * patient with no visits is admitted directly; leaving the visit unlinked does
 * the same for a patient who has some.
 */
export function AdmitPatientForm({
  patient,
  encounters,
  initialEncounterId = null,
  onAdmitted,
}: {
  patient: Patient;
  encounters: Encounter[];
  initialEncounterId?: number | null;
  onAdmitted: () => Promise<void> | void;
}) {
  const [ward, setWard] = useState("");
  const [bed, setBed] = useState("");
  const [encounterKey, setEncounterKey] = useState<string | null>(
    initialEncounterId != null ? String(initialEncounterId) : null,
  );
  const [saving, setSaving] = useState(false);

  // Start the form blank whenever the Patient changes, so a ward or bed typed
  // for one patient can never be admitted against another.
  useEffect(() => {
    setWard("");
    setBed("");
    setEncounterKey(
      initialEncounterId != null ? String(initialEncounterId) : null,
    );
  }, [patient.id, initialEncounterId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedWard = ward.trim();
    const trimmedBed = bed.trim();
    if (!trimmedWard || !trimmedBed) {
      toast.error("Enter the ward and the bed or location.");
      return;
    }
    setSaving(true);
    try {
      await api.admitPatient(
        patient.id,
        trimmedWard,
        trimmedBed,
        encounterKey != null ? Number(encounterKey) : null,
      );
      toast.success(
        `${patient.full_name} admitted to ${trimmedWard} · ${trimmedBed}.`,
      );
      setWard("");
      setBed("");
      setEncounterKey(null);
      await onAdmitted();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={submit}>
      <section className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Ward"
          isRequired
          value={ward}
          onChange={setWard}
          isDisabled={saving}
        />
        <Input
          label="Bed or location"
          isRequired
          value={bed}
          onChange={setBed}
          isDisabled={saving}
        />
      </section>

      {encounters.length > 0 ? (
        <Select
          label="Link to a visit (optional)"
          className="w-full"
          triggerClassName="min-h-11"
          placeholder="No linked visit — admit directly"
          selectedKey={encounterKey}
          onSelectionChange={(key) =>
            setEncounterKey(key == null ? null : String(key))
          }
        >
          {encounters.map((encounter) => (
            <SelectItem
              key={encounter.id}
              id={String(encounter.id)}
              textValue={`Encounter #${encounter.id}`}
            >
              Encounter #{encounter.id} · arrived{" "}
              {formatInstant(encounter.arrived_at)} · {encounter.reason_for_visit}
            </SelectItem>
          ))}
        </Select>
      ) : (
        <p className={mutedTextClass}>
          This patient has no visits on record, so they are admitted directly.
        </p>
      )}

      <footer className="flex flex-wrap gap-2">
        <Button type="submit" className="min-h-11" disabled={saving}>
          {saving ? "Admitting…" : "Admit to ward"}
        </Button>
      </footer>
    </form>
  );
}

interface VitalRow {
  label: string;
  value: string;
}

/**
 * One set of vitals as rows of label and value. The set holds the eight readings
 * the record keeps, shown as seven rows because the two blood-pressure figures
 * share a row. The values are shown exactly as charted; the client never
 * re-derives a threshold or marks a reading of its own.
 */
function readingsFor(observation: Observation): VitalRow[] {
  return [
    { label: "Pain", value: `${observation.pain_level} / 10` },
    {
      label: "Illness duration",
      value: `${observation.illness_duration_hours} h`,
    },
    { label: "Temperature", value: `${observation.temperature_c} °C` },
    { label: "Heart rate", value: `${observation.heart_rate_bpm} bpm` },
    {
      label: "Respiratory rate",
      value: `${observation.respiratory_rate_bpm} bpm`,
    },
    {
      label: "Blood pressure",
      value: `${observation.blood_pressure.systolic} / ${observation.blood_pressure.diastolic} mmHg`,
    },
    {
      label: "Oxygen saturation",
      value: `${observation.oxygen_saturation_percent}%`,
    },
  ];
}

/** A count with its noun, so "1 dose" never reads as "1 doses". */
function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}
