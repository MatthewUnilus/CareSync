import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Chip } from "@/components/base/badges/chip";
import { Input } from "@/components/base/input/input";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type { Encounter, Patient, WardAdmission } from "./api";
import { cardClass, figureClass, mutedTextClass } from "./design";
import ObservationChart from "./ObservationChart";
import { AdmitPatientForm } from "./WardBoard";
import { formatInstant, sexLabel } from "./queueDisplay";

/**
 * Find a Patient and read one Patient's Encounters over time.
 *
 * Search here is an aid to discovery, not identity resolution. The registration
 * rule matches a person by their hospital number, or — when neither record
 * carries one — by the whole name *and* the whole phone number together. This
 * box may match part of a name, phone number or hospital number, and offers
 * candidates for a human to choose between. The results list therefore shows
 * age, sex and hospital number beside each name, so two Patients who share a
 * name remain distinguishable at the point of selection. A blank query is never
 * sent: the server returns nothing for one, and the view keeps that discipline
 * by not firing the request at all.
 *
 * A selected Patient who carries no number offers an explicit attach action.
 * Attaching is not a search: the reader names the exact record, confirms the
 * identity shown beside it, and the server refuses a number another record
 * already holds. On success the view mirrors the server's Patient, so the
 * heading and the candidate row both show the new number.
 */
export default function PatientHistoryScreen() {
  const [query, setQuery] = useState("");
  // The query that produced the current results. Separate from what is now in
  // the box so the empty state can tell "nothing typed yet" from "no matches".
  const [searchedQuery, setSearchedQuery] = useState<string | null>(null);
  const [results, setResults] = useState<Patient[]>([]);
  const [searching, setSearching] = useState(false);

  const [selected, setSelected] = useState<Patient | null>(null);
  const [history, setHistory] = useState<Encounter[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [admissions, setAdmissions] = useState<WardAdmission[]>([]);
  const [loadingAdmissions, setLoadingAdmissions] = useState(false);
  // The open Encounter the chart writes against, chosen explicitly from the
  // Patient's visits. Null means the chart is read-only: nothing is charted
  // until the reader names a visit, so an ambiguous history never silently
  // chooses one. A Patient with several open visits therefore has no default.
  const [chartingEncounterId, setChartingEncounterId] = useState<number | null>(
    null,
  );
  // The Patient whose history the view is allowed to show. Each fetch captures
  // the id it was started for and, once it resolves, writes nothing unless that
  // Patient is still selected. Without this, a slow reply for the previous
  // Patient — or an end-of-visit refresh racing a switch — would drop its rows
  // under the new Patient's heading.
  const selectedIdRef = useRef<number | null>(null);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      // An empty query must not become a listing of the whole Patient table.
      // Clear any stale results rather than requesting them.
      setSearchedQuery(null);
      setResults([]);
      return;
    }

    setSearching(true);
    try {
      const { patients } = await api.searchPatients(trimmed);
      setResults(patients);
      setSearchedQuery(trimmed);
      // The previously selected Patient may not be among the new results; clear
      // the history so a stale record cannot sit under a fresh search, and
      // retire any history fetch still in flight for the old selection.
      selectedIdRef.current = null;
      setSelected(null);
      setHistory([]);
      setAdmissions([]);
      setChartingEncounterId(null);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSearching(false);
    }
  }

  async function openHistory(patient: Patient) {
    selectedIdRef.current = patient.id;
    setSelected(patient);
    // A new Patient has no charting subject until the reader names one.
    setChartingEncounterId(null);
    setLoadingHistory(true);
    // The stays load beside the visits, from the same Patient. A failure here
    // is reported by `refreshAdmissions` itself and leaves the visits alone.
    void refreshAdmissions(patient.id);
    try {
      const { encounters } = await api.patientHistory(patient.id);
      if (selectedIdRef.current !== patient.id) {
        return;
      }
      setHistory(encounters);
    } catch (caught) {
      if (selectedIdRef.current !== patient.id) {
        return;
      }
      toast.error(errorText(caught));
      setHistory([]);
    } finally {
      if (selectedIdRef.current === patient.id) {
        setLoadingHistory(false);
      }
    }
  }

  /**
   * Re-read the selected Patient's Encounters. Unlike `openHistory`, a failure
   * here leaves the list as it was rather than clearing it: the reader did not
   * ask for a new Patient, so the row they were reading must not vanish.
   */
  async function refreshHistory(patientId: number) {
    // A refresh only speaks for the Patient it was started for. If the operator
    // has since switched Patient or searched again, drop it: the previous
    // Patient's rows must not land under the new heading, and this request must
    // not clear the busy state the new Patient's load owns.
    if (selectedIdRef.current !== patientId) {
      return;
    }
    setLoadingHistory(true);
    try {
      const { encounters } = await api.patientHistory(patientId);
      if (selectedIdRef.current !== patientId) {
        return;
      }
      setHistory(encounters);
    } catch (caught) {
      if (selectedIdRef.current !== patientId) {
        return;
      }
      toast.error(errorText(caught));
    } finally {
      if (selectedIdRef.current === patientId) {
        setLoadingHistory(false);
      }
    }
  }

  /**
   * Re-read the selected Patient's Admissions. Like `refreshHistory`, a failure
   * leaves the list as it was and a reply only speaks for the Patient it was
   * started for.
   */
  async function refreshAdmissions(patientId: number) {
    if (selectedIdRef.current !== patientId) {
      return;
    }
    setLoadingAdmissions(true);
    try {
      const { admissions } = await api.patientAdmissions(patientId);
      if (selectedIdRef.current !== patientId) {
        return;
      }
      setAdmissions(admissions);
    } catch (caught) {
      if (selectedIdRef.current !== patientId) {
        return;
      }
      toast.error(errorText(caught));
    } finally {
      if (selectedIdRef.current === patientId) {
        setLoadingAdmissions(false);
      }
    }
  }

  /**
   * A visit has just ended server-side. Show the server's own ended Encounter
   * at once so the row leaves its open state, then re-read the list so the view
   * matches the server exactly. The immediate update also keeps the row honest
   * if the re-read itself fails.
   */
  async function handleEncounterEnded(ended: Encounter) {
    if (!selected) {
      return;
    }
    // An ended visit can no longer be charted against, so a selection pointing
    // at it is dropped rather than left charting into a closed visit.
    setChartingEncounterId((current) => (current === ended.id ? null : current));
    setHistory((previous) =>
      previous.map((encounter) =>
        encounter.id === ended.id ? ended : encounter,
      ),
    );
    await refreshHistory(selected.id);
  }

  /**
   * A hospital number was just attached server-side. Mirror the server's
   * Patient into both the selected record and its candidate row, so the header
   * and the list agree on the number the server now holds. History is untouched:
   * attaching a number does not alter a Patient's Encounters.
   */
  function handleNumberAttached(updated: Patient) {
    setSelected((current) =>
      current && current.id === updated.id ? updated : current,
    );
    setResults((current) =>
      current.map((patient) =>
        patient.id === updated.id ? updated : patient,
      ),
    );
  }

  return (
    <>
      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Find a patient
        </h2>
        <p className={mutedTextClass}>
          Search by name, contact number or hospital number. This finds
          candidates, not an identity: a Patient is recognised by their hospital
          number, or by their full name and phone number together, so two people
          who share a name stay separate. An empty search shows nothing.
        </p>

        <form className="flex flex-wrap items-end gap-2" onSubmit={handleSearch}>
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
            Enter a name, contact number or hospital number to search.
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
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-separator-border bg-background-secondary-default p-4"
                >
                  <div className="min-w-0 flex-1 basis-48">
                    <p className="text-body-medium font-medium text-text-primary">
                      {patient.full_name}
                    </p>
                    {/*
                     * Age, sex and hospital number sit beside the name so two
                     * Patients who share a name are still distinguishable here.
                     */}
                    <p className="text-body-2-regular text-text-secondary">
                      age {patient.age} · {sexLabel(patient.sex)} ·{" "}
                      <span className={figureClass}>{patient.contact_phone}</span>
                    </p>
                    <p className="text-body-2-regular text-text-secondary">
                      {patient.hospital_number ? (
                        <>
                          Hospital number{" "}
                          <span className={figureClass}>
                            {patient.hospital_number}
                          </span>
                        </>
                      ) : (
                        "No hospital number on record"
                      )}
                    </p>
                  </div>
                  <Button
                    variant={isSelected ? "primary" : "secondary"}
                    className="min-h-11"
                    onClick={() => void openHistory(patient)}
                  >
                    {isSelected ? "Viewing history" : "View history"}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {selected ? (
        <section className={cardClass}>
          <h2 className="text-title-3-medium text-text-primary">
            {selected.full_name} — encounters over time
          </h2>
          <p className={mutedTextClass}>
            age {selected.age} · {sexLabel(selected.sex)} ·{" "}
            <span className={figureClass}>{selected.contact_phone}</span>
          </p>
          <p className={mutedTextClass}>
            {selected.hospital_number ? (
              <>
                Hospital number{" "}
                <span className={figureClass}>
                  {selected.hospital_number}
                </span>
              </>
            ) : (
              "No hospital number on record"
            )}
          </p>

          {selected.hospital_number ? null : (
            <AttachNumberAction
              key={selected.id}
              patient={selected}
              onAttached={handleNumberAttached}
            />
          )}

          <p className={mutedTextClass}>
            Every visit for this Patient, oldest first. Choose an open visit to
            chart a new set of vitals against it; an ended visit cannot be
            charted against, and nothing is charted until a visit is chosen.
          </p>

          {loadingHistory ? (
            <p className={mutedTextClass}>Loading encounters…</p>
          ) : history.length === 0 ? (
            <p className={mutedTextClass}>
              This patient has no encounters on record.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {history.map((encounter) => (
                <li
                  key={encounter.id}
                  className="flex flex-col gap-1 rounded-2xl border border-border-button-default bg-background-primary-default p-4"
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-body-semibold text-text-primary">
                      Encounter #{encounter.id}
                    </span>
                    <span
                      className={`text-body-2-regular ${mutedTextClass} ${figureClass}`}
                    >
                      {formatInstant(encounter.arrived_at)}
                    </span>
                    {encounter.ended_at ? (
                      <span className="text-body-2-regular text-text-secondary">
                        ended {formatInstant(encounter.ended_at)}
                      </span>
                    ) : (
                      <span className="text-body-2-regular text-text-secondary">
                        open
                      </span>
                    )}
                  </div>
                  <p className="text-body-regular text-text-primary wrap-anywhere">
                    {encounter.reason_for_visit}
                  </p>
                  <footer className="flex flex-wrap gap-2">
                    {encounter.status === "open" ? (
                      <Button
                        variant={
                          chartingEncounterId === encounter.id
                            ? "primary"
                            : "secondary"
                        }
                        className="min-h-11"
                        onClick={() =>
                          setChartingEncounterId((current) =>
                            current === encounter.id ? null : encounter.id,
                          )
                        }
                      >
                        {chartingEncounterId === encounter.id
                          ? "Charting against this visit"
                          : "Chart vitals against this visit"}
                      </Button>
                    ) : null}
                    {encounter.status === "open" ? (
                      <EndVisitAction
                        encounter={encounter}
                        onEnded={handleEncounterEnded}
                      />
                    ) : null}
                  </footer>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {/*
       * The Patient's inpatient stays, including discharged ones, so a closed
       * Admission keeps its place in the history beside the visits. An open stay
       * is also on the ward board. Admitting from here starts a stay for this
       * Patient, optionally linked to one of their visits.
       */}
      {selected ? (
        <section className={cardClass}>
          <h2 className="text-title-3-medium text-text-primary">
            {selected.full_name} — admissions
          </h2>
          <p className={mutedTextClass}>
            Every inpatient stay for this Patient, newest first, including
            discharged stays. An open stay is also on the ward board; a
            discharged stay keeps its full history here.
          </p>

          {loadingAdmissions ? (
            <p className={mutedTextClass}>Loading admissions…</p>
          ) : admissions.length === 0 ? (
            <p className={mutedTextClass}>
              This patient has no admissions on record.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {[...admissions]
                .sort((left, right) =>
                  right.admitted_at.localeCompare(left.admitted_at),
                )
                .map((admission) => (
                  <li key={admission.id} className={cardClass}>
                    <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <h3 className="text-body-semibold text-text-primary">
                        Admission #{admission.id}
                      </h3>
                      <Chip
                        variant="bold"
                        color={
                          admission.status === "open" ? "lime" : "neutral"
                        }
                      >
                        {admission.status === "open"
                          ? "On the ward"
                          : "Discharged"}
                      </Chip>
                    </header>
                    <p className={mutedTextClass}>
                      Ward{" "}
                      <data value={admission.ward} className={figureClass}>
                        {admission.ward}
                      </data>
                      {" · Bed "}
                      <data value={admission.bed} className={figureClass}>
                        {admission.bed}
                      </data>
                      {admission.encounter_id != null
                        ? ` · linked to encounter #${admission.encounter_id}`
                        : " · no linked visit"}
                    </p>
                    <p className={mutedTextClass}>
                      Admitted{" "}
                      <time
                        dateTime={admission.admitted_at}
                        className={figureClass}
                      >
                        {formatInstant(admission.admitted_at)}
                      </time>
                      {admission.discharged_at !== null ? (
                        <>
                          {" · Discharged "}
                          <time
                            dateTime={admission.discharged_at}
                            className={figureClass}
                          >
                            {formatInstant(admission.discharged_at)}
                          </time>
                        </>
                      ) : null}
                    </p>
                  </li>
                ))}
            </ul>
          )}

          <AdmitToWardAction
            key={selected.id}
            patient={selected}
            encounters={history}
            onAdmitted={() => refreshAdmissions(selected.id)}
          />
        </section>
      ) : null}

      {/*
       * The Observation chart sits with the selected Patient, so the latest
       * vitals are read without walking back to the ward. Charting a repeat set
       * is reachable here: once the reader names an open visit above, the chart
       * carries the form and writes against it. Without a named visit the chart
       * is read-only, so an ambiguous history never silently chooses one, and an
       * ended visit is never a subject.
       */}
      {selected ? (
        <ObservationChart
          patientId={selected.id}
          encounterId={chartingEncounterId ?? undefined}
        />
      ) : null}
    </>
  );
}

/**
 * End an open Encounter from its row in the history.
 *
 * The action is self-contained so the row reads as a plain record until the
 * reader chooses to act. It sends no body: the server stamps the end instant.
 * The button disables while the request is in flight, which both names the busy
 * state and stops a second click becoming a duplicate end — an already-ended
 * visit is refused with a `409`. Errors surface as a toast, matching the rest
 * of this screen; the success path hands the server's Encounter back to the
 * list so it refreshes to the ended state.
 */
function EndVisitAction({
  encounter,
  onEnded,
}: {
  encounter: Encounter;
  onEnded: (ended: Encounter) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);

  async function end() {
    setSaving(true);
    try {
      const ended = await api.endEncounter(encounter.id);
      toast.success(`Visit #${encounter.id} ended.`);
      await onEnded(ended);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Button
      variant="secondary"
      className="min-h-11 self-start"
      disabled={saving}
      onClick={() => void end()}
    >
      {saving ? "Ending visit…" : "End visit"}
    </Button>
  );
}

/**
 * Attach a hospital number to the selected Patient.
 *
 * Offered only while the Patient carries no number, and kept inside the record
 * it changes: the confirm copy repeats the name, age, sex and phone so the
 * reader attaches to the person they mean, not to whichever row was nearest.
 * Attaching identifies the existing record — it never merges records — and the
 * server refuses a number another Patient already holds (`409`) or a malformed
 * one (`422`); both surface as a toast, matching the rest of this screen. The
 * field and the button disable while the request is in flight so a second click
 * cannot become a duplicate. On success the server's Patient is handed back so
 * the heading and candidate row reflect the stored number.
 */
function AttachNumberAction({
  patient,
  onAttached,
}: {
  patient: Patient;
  onAttached: (updated: Patient) => void;
}) {
  const [number, setNumber] = useState("");
  const [saving, setSaving] = useState(false);

  async function attach(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = number.trim();
    if (!trimmed) {
      toast.error("Enter a hospital number to attach.");
      return;
    }
    setSaving(true);
    try {
      const updated = await api.attachHospitalNumber(patient.id, trimmed);
      toast.success(
        `Hospital number ${updated.hospital_number} attached to ${updated.full_name}.`,
      );
      onAttached(updated);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border-button-default bg-background-primary-default p-4">
      <p className={mutedTextClass}>
        Attaching a hospital number identifies this record as this Patient. It
        does not merge them with anyone else, and the number must not already
        belong to another record. Confirm this is the right person before
        attaching:
      </p>
      <p className="text-body-medium font-medium text-text-primary">
        {patient.full_name}
      </p>
      <p className="text-body-2-regular text-text-secondary">
        age {patient.age} · {sexLabel(patient.sex)} ·{" "}
        <span className={figureClass}>{patient.contact_phone}</span>
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={attach}
      >
        <Input
          className="min-w-0 flex-1 basis-56"
          label="Hospital number"
          placeholder="H12345"
          value={number}
          onChange={setNumber}
          isDisabled={saving}
        />
        <Button type="submit" className="min-h-11" disabled={saving}>
          {saving ? "Attaching…" : "Attach hospital number"}
        </Button>
      </form>
    </div>
  );
}

/**
 * Admit the selected Patient to a ward from their history.
 *
 * The action reads as a plain record until chosen, then opens the shared admit
 * form. The visits already loaded for the Patient are passed in, so a stay can
 * be linked to the visit it came from — keeping the visit and the stay one
 * history — or left unlinked for a direct admission. On success the admissions
 * list is re-read, so the new stay appears at once.
 */
function AdmitToWardAction({
  patient,
  encounters,
  onAdmitted,
}: {
  patient: Patient;
  encounters: Encounter[];
  onAdmitted: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button
        variant="secondary"
        className="min-h-11"
        onClick={() => setOpen(true)}
      >
        Admit to ward
      </Button>
    );
  }

  return (
    <section className={cx(cardClass, "gap-3")}>
      <p className={mutedTextClass}>
        Admitting <bdi>{patient.full_name}</bdi> records an inpatient stay on a
        ward. Link the visit they were seen in first to keep the visit and the
        stay one history; leaving it unlinked admits them directly.
      </p>
      <AdmitPatientForm
        patient={patient}
        encounters={encounters}
        onAdmitted={async () => {
          setOpen(false);
          await onAdmitted();
        }}
      />
      <footer className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          className="min-h-11"
          onClick={() => setOpen(false)}
        >
          Cancel
        </Button>
      </footer>
    </section>
  );
}
