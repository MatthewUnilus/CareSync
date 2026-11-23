import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";

import { api, errorText } from "./api";
import type {
  BoardAdmission,
  Investigation,
  MedicationDueDose,
  Observation,
  Task,
} from "./api";
import { cx } from "@/utils/cx";
import { formatInstant, plural } from "./queueDisplay";
import { readingsFor } from "./ObservationChart";

/**
 * Print sheets for the ward (ticket 37).
 *
 * Three sheets print:
 * - Handover sheet: the ward's patients with identity, location, reason, latest
 *   Observation, medication situation, open Tasks and unreviewed results.
 * - Medication round sheet: doses due in a chosen window, in the order they will
 *   be worked, with a space to record each one and the patient's identity.
 * - Ward worklist: outstanding Tasks and Investigations awaiting a result or a
 *   review, grouped by patient.
 *
 * Every sheet carries its generation time and the line "verify against the
 * system" (ADR 0009). The print stylesheet forces a light, high-contrast
 * presentation and drops all navigation and interactive controls.
 */

/** Format the current instant for the generation stamp. */
function generationStamp(): string {
  const now = new Date();
  return now.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** A patient's medication situation as a one-line summary. */
function medicationSummary(admission: BoardAdmission): string {
  const overdue = admission.overdue_medication_count;
  const due = admission.due_medication_count;
  const outstanding = admission.outstanding_medication_count;

  if (overdue > 0 && due > 0) {
    return `${overdue} overdue, ${due} due now, ${outstanding} outstanding`;
  }
  if (overdue > 0) {
    return `${overdue} overdue, ${outstanding} outstanding`;
  }
  if (due > 0) {
    return `${due} due now, ${outstanding} outstanding`;
  }
  if (outstanding > 0) {
    return `${outstanding} outstanding`;
  }
  return "no medication orders";
}

/** A patient's investigation summary for the handover sheet. */
function investigationSummary(
  investigations: Investigation[],
): { unreviewed: number; awaitingResult: number; oldestUnreviewed: string | null } {
  let unreviewed = 0;
  let awaitingResult = 0;
  let oldestUnreviewed: string | null = null;

  for (const inv of investigations) {
    if (inv.state === "result_available") {
      unreviewed += 1;
      if (
        oldestUnreviewed === null ||
        inv.result_available_at! < oldestUnreviewed
      ) {
        oldestUnreviewed = inv.result_available_at!;
      }
    } else if (inv.state === "requested" || inv.state === "sample_taken") {
      awaitingResult += 1;
    }
  }

  return { unreviewed, awaitingResult, oldestUnreviewed };
}

/** A patient's task summary for the handover sheet. */
function taskSummary(tasks: Task[]): { open: number; overdue: number } {
  let open = 0;
  let overdue = 0;
  for (const task of tasks) {
    if (task.status === "open") {
      open += 1;
      if (task.overdue) {
        overdue += 1;
      }
    }
  }
  return { open, overdue };
}

/** The latest observation for a patient, formatted for the handover sheet. */
function latestObservationForHandover(observation: Observation | null): string {
  if (!observation) {
    return "No observations charted yet.";
  }
  const rows = readingsFor(observation);
  const parts = rows
    .filter((r) => r.value !== "" && r.value !== "0 / 10" && r.value !== "0 h")
    .map((r) => `${r.label} ${r.value}`)
    .join(" \u00b7 ");
  const abnormal = observation.abnormal_fields.length > 0
    ? ` (${plural(observation.abnormal_fields.length, "reading", "readings")} outside range)`
    : "";
  return `${parts}${abnormal} \u2014 charted ${formatInstant(observation.taken_at)} by ${observation.actor.display_name}`;
}

/**
 * Print sheets mount into a portal at the end of <body>, so the print
 * stylesheet can hide the app root and print the sheet alone. On screen the
 * portal is presented as a full-page preview; the sheet's own controls are
 * marked `no-print`, and every other top-level node is hidden on paper.
 */
function SheetPortal({ children }: { children: ReactNode }) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = document.createElement("div");
    element.className = "print-sheet-portal";
    document.body.appendChild(element);
    setContainer(element);
    return () => {
      document.body.removeChild(element);
    };
  }, []);

  if (container === null) {
    return null;
  }
  return createPortal(children, container);
}

/* ==========================================================================
 * Handover Sheet
 * ========================================================================== */

export function HandoverSheet({
  admissions,
  allInvestigations,
  allTasks,
  onClose,
}: {
  admissions: BoardAdmission[];
  /** All investigations across the ward, for the summary. */
  allInvestigations: Investigation[];
  /** All tasks across the ward, for the summary. */
  allTasks: Task[];
  onClose: () => void;
}) {
  // Group investigations and tasks by admission for quick lookup
  const investigationsByAdmission = new Map<number, Investigation[]>();
  for (const inv of allInvestigations) {
    const arr = investigationsByAdmission.get(inv.admission_id) ?? [];
    arr.push(inv);
    investigationsByAdmission.set(inv.admission_id, arr);
  }

  const tasksByAdmission = new Map<number, Task[]>();
  for (const task of allTasks) {
    const arr = tasksByAdmission.get(task.admission_id) ?? [];
    arr.push(task);
    tasksByAdmission.set(task.admission_id, arr);
  }

  // Fetch medication due list for medication summaries
  const [doses, setDoses] = useState<MedicationDueDose[] | null>(null);
  const requestRef = useRef(0);

  const loadDoses = useCallback(async () => {
    const requestId = ++requestRef.current;
    const now = new Date();
    const startOfDay = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const endOfDay = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
    try {
      const { doses: loaded } = await api.medicationDue(
        startOfDay.toISOString(),
        endOfDay.toISOString(),
      );
      if (requestRef.current !== requestId) return;
      setDoses(loaded);
    } catch {
      // Silently fail; the summary will just say "no medication orders"
    }
  }, []);

  useEffect(() => {
    void loadDoses();
  }, [loadDoses]);

  // Group doses by admission for quick lookup
  const dosesByAdmission = new Map<number, MedicationDueDose[]>();
  if (doses) {
    for (const dose of doses) {
      const arr = dosesByAdmission.get(dose.admission_id) ?? [];
      arr.push(dose);
      dosesByAdmission.set(dose.admission_id, arr);
    }
  }

  return (
    <div className="print-sheet">
      <header className="print-sheet-header">
        <h1 className="print-sheet-title">Ward Handover Sheet</h1>
        <p className="print-sheet-meta">
          CareSync \u00b7 Ward board handover \u00b7 Generated <span className="print-generation-stamp">{generationStamp()}</span>
        </p>
      </header>

      {admissions.length === 0 ? (
        <p className="print-section-empty">No patients on the ward board.</p>
      ) : (
        <ol className="flex flex-col gap-4">
          {admissions.map((admission) => {
            const patient = admission.patient;
            const invs = investigationsByAdmission.get(admission.id) ?? [];
            const tsks = tasksByAdmission.get(admission.id) ?? [];
            const invSummary = investigationSummary(invs);
            const taskSum = taskSummary(tsks);
            const medSummary = medicationSummary(admission);
            const latestObs = latestObservationForHandover(admission.latest_observation);

            return (
              <li key={admission.id} className="print-patient-block">
                <header className="print-patient-header">
                  <h2 className="print-patient-name">{patient.full_name}</h2>
                  <span className="print-chip print-chip-neutral">
                    Ward {admission.ward} \u00b7 Bed {admission.bed}
                  </span>
                  {patient.hospital_number !== null && (
                    <span className="print-chip print-chip-soft">
                      Hospital #: {patient.hospital_number}
                    </span>
                  )}
                  <span className="print-chip print-chip-soft">
                    Age {patient.age} \u00b7 {patient.sex}
                  </span>
                </header>

                <p className="print-patient-detail">
                  <span className="print-patient-detail-label">Admitted:</span>{" "}
                  {formatInstant(admission.admitted_at)}
                  {admission.encounter_id != null
                    ? ` \u00b7 Linked to Encounter #${admission.encounter_id}`
                    : " \u00b7 Direct admission"}
                </p>

                <section className="print-section">
                  <h3 className="print-section-title">Why they are here</h3>
                  <p className="print-patient-detail">
                    {admission.encounter_id != null
                      ? "See Encounter record for presenting complaint."
                      : "No linked visit \u2014 admitted directly."}
                  </p>
                </section>

                <section className="print-section">
                  <h3 className="print-section-title">Latest observation</h3>
                  <p className="print-patient-detail">{latestObs}</p>
                </section>

                <section className="print-section">
                  <h3 className="print-section-title">Medication situation</h3>
                  <p className="print-patient-detail">{medSummary}</p>
                </section>

                <section className="print-section">
                  <h3 className="print-section-title">Open tasks</h3>
                  {tsks.length === 0 ? (
                    <p className="print-section-empty">No open tasks.</p>
                  ) : (
                    <>
                      <p className="print-patient-detail">
                        {taskSum.open} open {plural(taskSum.overdue, "overdue", "overdue")}
                      </p>
                      <ul className="print-patient-detail">
                        {tsks
                          .filter((t) => t.status === "open")
                          .map((task) => (
                            <li key={task.id}>
                              {task.description}
                              {task.due_at && (
                                <>
                                  {" \u2014 due "}
                                  <time className="print-figure" dateTime={task.due_at}>
                                    {formatInstant(task.due_at)}
                                  </time>
                                </>
                              )}
                              {task.assignee && (
                                <> \u00b7 assigned to {task.assignee.display_name}</>
                              )}
                              {task.overdue && <span className="print-chip print-chip-overdue">overdue</span>}
                            </li>
                          ))}
                      </ul>
                    </>
                  )}
                </section>

                <section className="print-section">
                  <h3 className="print-section-title">Investigations</h3>
                  {invs.length === 0 ? (
                    <p className="print-section-empty">No investigations recorded.</p>
                  ) : (
                    <>
                      {invSummary.unreviewed > 0 && (
                        <p className="print-patient-detail">
                          <span className="print-chip print-chip-purple">
                            {invSummary.unreviewed} result{plural(invSummary.unreviewed, "", "s")} awaiting review
                          </span>
                          {invSummary.oldestUnreviewed && (
                            <> \u00b7 oldest since {formatInstant(invSummary.oldestUnreviewed)}</>
                          )}
                        </p>
                      )}
                      {invSummary.awaitingResult > 0 && (
                        <p className="print-patient-detail">
                          <span className="print-chip print-chip-blue">
                            {invSummary.awaitingResult} test{plural(invSummary.awaitingResult, "", "s")} awaiting result
                          </span>
                        </p>
                      )}
                      {invSummary.unreviewed === 0 && invSummary.awaitingResult === 0 && (
                        <p className="print-section-empty">No outstanding investigations.</p>
                      )}
                    </>
                  )}
                </section>
              </li>
            );
          })}
        </ol>
      )}

      <p className="print-verify-line">Verify against the system.</p>

      <footer style={{ marginTop: "2rem", textAlign: "center" }}>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={() => window.print()}
        >
          Print this sheet
        </Button>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={onClose}
        >
          Close
        </Button>
      </footer>
    </div>
  );
}

/* ==========================================================================
 * Medication Round Sheet
 * ========================================================================== */

export function MedicationRoundSheet({
  admissions,
  onClose,
}: {
  admissions: BoardAdmission[];
  onClose: () => void;
}) {
  const [day, setDay] = useState(() => {
    const now = new Date();
    return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
  });
  const [doses, setDoses] = useState<MedicationDueDose[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async (chosenDay: string) => {
    const requestId = ++requestRef.current;
    setLoadError(null);
    try {
      const [year, month, date] = chosenDay.split("-").map(Number);
      const from = new Date(Date.UTC(year, month - 1, date, 0, 0, 0, 0)).toISOString();
      const to = new Date(Date.UTC(year, month - 1, date + 1, 0, 0, 0, 0)).toISOString();
      const { doses: loaded } = await api.medicationDue(from, to);
      if (requestRef.current !== requestId) return;
      setDoses(loaded);
    } catch (caught) {
      if (requestRef.current !== requestId) return;
      setLoadError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    void load(day);
  }, [day, load]);

  // Where each admission's patient is
  const locations = new Map(
    admissions.map((admission) => [admission.id, `${admission.ward} \u00b7 ${admission.bed}`]),
  );

  return (
    <div className="print-sheet">
      <header className="print-sheet-header">
        <h1 className="print-sheet-title">Medication Round Sheet</h1>
        <p className="print-sheet-meta">
          CareSync \u00b7 Medication round \u00b7 UTC day: {day} \u00b7 Generated{" "}
          <span className="print-generation-stamp">{generationStamp()}</span>
        </p>
      </header>

      <div className="no-print" style={{ marginBottom: "1rem" }}>
        <Input
          className="w-full sm:w-56"
          label="Day (UTC)"
          type="date"
          value={day}
          onChange={setDay}
        />
      </div>

      {loadError !== null ? (
        <p className="print-section-empty" role="alert">{loadError}</p>
      ) : doses === null ? (
        <p className="print-section-empty">Loading the due list\u2026</p>
      ) : doses.length === 0 ? (
        <p className="print-section-empty">
          No doses are due in this window. A stopped order produces no further
          doses, and a recorded dose leaves the list.
        </p>
      ) : (
        <section className="print-table-wrap">
          <table className="print-table">
            <caption className="print-table-caption">
              Doses due in the chosen UTC day, ordered by due time; times are UTC.
              Each row has space to record the outcome. A dose is answered on its
              own row, once per slot.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="print-table-th" style={{ width: "16%" }}>Due (UTC)</th>
                <th scope="col" className="print-table-th" style={{ width: "20%" }}>Patient</th>
                <th scope="col" className="print-table-th" style={{ width: "15%" }}>Location</th>
                <th scope="col" className="print-table-th" style={{ width: "15%" }}>Drug</th>
                <th scope="col" className="print-table-th" style={{ width: "10%" }}>Dose</th>
                <th scope="col" className="print-table-th" style={{ width: "10%" }}>Route</th>
                <th scope="col" className="print-table-th" style={{ width: "14%" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {doses.map((dose) => (
                <tr key={`${dose.order_id}:${dose.due_at}`} className="print-table-tr">
                  <td className="print-table-td print-figure">
                    <time dateTime={dose.due_at}>
                      {new Date(dose.due_at).toLocaleString(undefined, {
                        timeZone: "UTC",
                        dateStyle: "short",
                        timeStyle: "short",
                      })} UTC
                    </time>
                  </td>
                  <td className="print-table-td">
                    {dose.patient.full_name}
                    {dose.patient.hospital_number !== null && (
                      <>
                        {" \u00b7 "}
                        <data className="print-figure" value={dose.patient.hospital_number}>
                          {dose.patient.hospital_number}
                        </data>
                      </>
                    )}
                  </td>
                  <td className="print-table-td">
                    {locations.get(dose.admission_id) ?? "Not on the board"}
                  </td>
                  <td className="print-table-td">{dose.drug}</td>
                  <td className="print-table-td">{dose.dose}</td>
                  <td className="print-table-td">{dose.route}</td>
                  <td className="print-table-td">
                    <span
                      className={cx(
                        "print-chip",
                        dose.overdue ? "print-chip-overdue" : "print-chip-due",
                      )}
                    >
                      {dose.overdue ? "overdue" : "due"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <p className="print-verify-line">Verify against the system.</p>

      <footer style={{ marginTop: "2rem", textAlign: "center" }}>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={() => window.print()}
        >
          Print this sheet
        </Button>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={onClose}
        >
          Close
        </Button>
      </footer>
    </div>
  );
}

/* ==========================================================================
 * Ward Worklist Sheet
 * ========================================================================== */

export function WardWorklistSheet({
  admissions,
  allTasks,
  allInvestigations,
  onClose,
}: {
  admissions: BoardAdmission[];
  allTasks: Task[];
  allInvestigations: Investigation[];
  onClose: () => void;
}) {
  // Group by admission
  const tasksByAdmission = new Map<number, Task[]>();
  for (const task of allTasks) {
    if (task.status === "open") {
      const arr = tasksByAdmission.get(task.admission_id) ?? [];
      arr.push(task);
      tasksByAdmission.set(task.admission_id, arr);
    }
  }

  const investigationsByAdmission = new Map<number, Investigation[]>();
  for (const inv of allInvestigations) {
    if (inv.state === "result_available" || inv.state === "requested" || inv.state === "sample_taken") {
      const arr = investigationsByAdmission.get(inv.admission_id) ?? [];
      arr.push(inv);
      investigationsByAdmission.set(inv.admission_id, arr);
    }
  }

  // Admissions that have any outstanding work
  const admissionsWithWork = admissions.filter(
    (a) =>
      (tasksByAdmission.get(a.id)?.length ?? 0) > 0 ||
      (investigationsByAdmission.get(a.id)?.length ?? 0) > 0,
  );

  return (
    <div className="print-sheet">
      <header className="print-sheet-header">
        <h1 className="print-sheet-title">Ward Worklist</h1>
        <p className="print-sheet-meta">
          CareSync \u00b7 Outstanding tasks and investigations \u00b7 Generated{" "}
          <span className="print-generation-stamp">{generationStamp()}</span>
        </p>
      </header>

      {admissionsWithWork.length === 0 ? (
        <p className="print-section-empty">No outstanding tasks or investigations across the ward.</p>
      ) : (
        <ol className="flex flex-col gap-4">
          {admissionsWithWork.map((admission) => {
            const patient = admission.patient;
            const tsks = tasksByAdmission.get(admission.id) ?? [];
            const invs = investigationsByAdmission.get(admission.id) ?? [];

            return (
              <li key={admission.id} className="print-patient-block">
                <header className="print-patient-header">
                  <h2 className="print-patient-name">{patient.full_name}</h2>
                  <span className="print-chip print-chip-neutral">
                    Ward {admission.ward} \u00b7 Bed {admission.bed}
                  </span>
                  {patient.hospital_number !== null && (
                    <span className="print-chip print-chip-soft">
                      Hospital #: {patient.hospital_number}
                    </span>
                  )}
                </header>

                {tsks.length > 0 && (
                  <section className="print-section">
                    <h3 className="print-section-title">
                      Open Tasks ({tsks.length})
                    </h3>
                    <ul className="print-patient-detail">
                      {tsks.map((task) => (
                        <li key={task.id}>
                          {task.description}
                          {task.due_at && (
                            <>
                              {" \u2014 due "}
                              <time className="print-figure" dateTime={task.due_at}>
                                {formatInstant(task.due_at)}
                              </time>
                            </>
                          )}
                          {task.assignee && (
                            <> \u00b7 assigned to {task.assignee.display_name}</>
                          )}
                          {task.overdue && <span className="print-chip print-chip-overdue">overdue</span>}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {invs.length > 0 && (
                  <section className="print-section">
                    <h3 className="print-section-title">
                      Investigations ({invs.length})
                    </h3>
                    <ul className="print-patient-detail">
                      {invs.map((inv) => (
                        <li key={inv.id}>
                          <strong>{inv.test_name}</strong> \u2014{" "}
                          <span
                            className={cx(
                              "print-chip",
                              inv.state === "result_available"
                                ? "print-chip-purple"
                                : inv.state === "sample_taken"
                                  ? "print-chip-blue"
                                  : "print-chip-neutral",
                            )}
                          >
                            {inv.state === "result_available"
                              ? "result awaiting review"
                              : inv.state === "sample_taken"
                                ? "sample taken"
                                : "requested"}
                          </span>
                          {inv.state === "result_available" && inv.result_available_at && (
                            <>
                              {" \u00b7 result since "}
                              <time className="print-figure" dateTime={inv.result_available_at}>
                                {formatInstant(inv.result_available_at)}
                              </time>
                            </>
                          )}
                          {inv.instructed_by && (
                            <> \u00b7 requested by {inv.instructed_by}</>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </li>
            );
          })}
        </ol>
      )}

      <p className="print-verify-line">Verify against the system.</p>

      <footer style={{ marginTop: "2rem", textAlign: "center" }}>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={() => window.print()}
        >
          Print this sheet
        </Button>
        <Button
          variant="secondary"
          className="min-h-11 no-print"
          onClick={onClose}
        >
          Close
        </Button>
      </footer>
    </div>
  );
}

/* ==========================================================================
 * Print Sheet Launcher (buttons in the clinical workspace)
 * ========================================================================== */

export function PrintSheetLauncher({
  admissions,
  allInvestigations,
  allTasks,
}: {
  admissions: BoardAdmission[];
  allInvestigations: Investigation[];
  allTasks: Task[];
}) {
  const [openSheet, setOpenSheet] = useState<"handover" | "medication" | "worklist" | null>(null);

  if (openSheet === "handover") {
    return (
      <SheetPortal>
        <HandoverSheet
          admissions={admissions}
          allInvestigations={allInvestigations}
          allTasks={allTasks}
          onClose={() => setOpenSheet(null)}
        />
      </SheetPortal>
    );
  }
  if (openSheet === "medication") {
    return (
      <SheetPortal>
        <MedicationRoundSheet
          admissions={admissions}
          onClose={() => setOpenSheet(null)}
        />
      </SheetPortal>
    );
  }
  if (openSheet === "worklist") {
    return (
      <SheetPortal>
        <WardWorklistSheet
          admissions={admissions}
          allTasks={allTasks}
          allInvestigations={allInvestigations}
          onClose={() => setOpenSheet(null)}
        />
      </SheetPortal>
    );
  }

  return (
    <div className="flex flex-wrap gap-2 no-print">
      <Button
        variant="secondary"
        className="min-h-11"
        onClick={() => setOpenSheet("handover")}
      >
        Print handover sheet
      </Button>
      <Button
        variant="secondary"
        className="min-h-11"
        onClick={() => setOpenSheet("medication")}
      >
        Print medication round sheet
      </Button>
      <Button
        variant="secondary"
        className="min-h-11"
        onClick={() => setOpenSheet("worklist")}
      >
        Print ward worklist
      </Button>
    </div>
  );
}