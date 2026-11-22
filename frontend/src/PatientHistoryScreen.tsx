import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { toast } from "@/components/base/toast/toast";

import { api, errorText } from "./api";
import type { Encounter, Patient } from "./api";
import { cardClass, figureClass, mutedTextClass } from "./design";
import { formatInstant, sexLabel } from "./queueDisplay";

/**
 * Find a Patient and read one Patient's Encounters over time.
 *
 * Search here is an aid to discovery, not identity resolution. The registration
 * rule matches a person only when the whole name *and* the whole phone number
 * agree; this box may match part of either and offers candidates for a human to
 * choose between. The results list therefore shows age and sex beside each name,
 * so two Patients who share a name remain distinguishable at the point of
 * selection. A blank query is never sent: the server returns nothing for one,
 * and the view keeps that discipline by not firing the request at all.
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
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSearching(false);
    }
  }

  async function openHistory(patient: Patient) {
    selectedIdRef.current = patient.id;
    setSelected(patient);
    setLoadingHistory(true);
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
   * A visit has just ended server-side. Show the server's own ended Encounter
   * at once so the row leaves its open state, then re-read the list so the view
   * matches the server exactly. The immediate update also keeps the row honest
   * if the re-read itself fails.
   */
  async function handleEncounterEnded(ended: Encounter) {
    if (!selected) {
      return;
    }
    setHistory((previous) =>
      previous.map((encounter) =>
        encounter.id === ended.id ? ended : encounter,
      ),
    );
    await refreshHistory(selected.id);
  }

  return (
    <>
      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Find a patient
        </h2>
        <p className={mutedTextClass}>
          Search by name or contact number. This finds candidates, not an
          identity: a Patient is only ever recognised by their full name and
          phone number together, so two people who share a name stay separate.
          An empty search shows nothing.
        </p>

        <form className="flex flex-wrap items-end gap-2" onSubmit={handleSearch}>
          <Input
            className="min-w-0 flex-1 basis-64"
            label="Name or contact number"
            placeholder="Ada Lovelace · 07700 900123"
            value={query}
            onChange={setQuery}
          />
          <Button type="submit" className="min-h-11" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </Button>
        </form>

        {searchedQuery === null ? (
          <p className={mutedTextClass}>
            Enter a name or contact number to search.
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
                     * Age and sex sit beside the name so two Patients who share
                     * a name are still distinguishable here. There is no medical
                     * record number in scope, so this is the identity the
                     * prototype can honestly show.
                     */}
                    <p className="text-body-2-regular text-text-secondary">
                      age {patient.age} · {sexLabel(patient.sex)} ·{" "}
                      <span className={figureClass}>{patient.contact_phone}</span>
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
            Every visit for this Patient, oldest first.
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
                  {encounter.status === "open" ? (
                    <EndVisitAction
                      encounter={encounter}
                      onEnded={handleEncounterEnded}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
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
