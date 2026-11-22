import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { toast } from "@/components/base/toast/toast";
import { TappableInfo } from "@/components/base/utils/tappable-info";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type { Encounter, Patient } from "./api";
import { cardClass, figureClass, mutedTextClass, sectionLabelClass } from "./design";
import {
  formatInstant,
  sexLabel,
  urgencyBadgeClass,
  urgencyBorderClass,
} from "./queueDisplay";

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
      // the history so a stale record cannot sit under a fresh search.
      setSelected(null);
      setHistory([]);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSearching(false);
    }
  }

  async function openHistory(patient: Patient) {
    setSelected(patient);
    setLoadingHistory(true);
    try {
      const { encounters } = await api.patientHistory(patient.id);
      setHistory(encounters);
    } catch (caught) {
      toast.error(errorText(caught));
      setHistory([]);
    } finally {
      setLoadingHistory(false);
    }
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
            Every visit for this Patient, oldest first, with the Urgency Level
            that governed it. Evaluation-run rows are excluded, so corpus data
            never appears as a real visit.
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
                  className={cx(
                    "grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-2 rounded-2xl border bg-background-primary-default p-4 max-sm:grid-cols-1",
                    encounter.assessment
                      ? urgencyBorderClass(encounter.assessment.final_decision)
                      : "border-border-button-default",
                  )}
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="text-body-semibold text-text-primary">
                        Encounter #{encounter.id}
                      </span>
                      <span className={`text-body-2-regular ${mutedTextClass} ${figureClass}`}>
                        {formatInstant(encounter.arrived_at)}
                      </span>
                      {encounter.departed_at ? (
                        <span className="text-body-2-regular text-text-secondary">
                          departed {formatInstant(encounter.departed_at)}
                        </span>
                      ) : (
                        <span className="text-body-2-regular text-text-secondary">
                          awaiting
                        </span>
                      )}
                    </div>
                    <p className="text-body-regular text-text-primary wrap-anywhere">
                      {encounter.intake.presenting_complaint}
                    </p>
                  </div>
                  {encounter.assessment ? (
                    <div className="flex flex-col items-end gap-1 max-sm:items-start">
                      <span className={sectionLabelClass}>Final decision</span>
                      <span
                        className={`rounded-md px-2 py-0.5 text-body-semibold ${urgencyBadgeClass(
                          encounter.assessment.final_decision,
                        )}`}
                      >
                        {encounter.assessment.final_decision}
                      </span>
                      {encounter.assessment.final_decision !==
                      encounter.assessment.machine_recommendation ? (
                        <TappableInfo
                          summary="overridden from"
                          detail="The Final Decision differs from the machine recommendation because an Override was recorded."
                        >
                          {({ showDetail }) => (
                            <span className="text-body-2-regular text-text-secondary">
                              overridden from{" "}
                              {showDetail ? encounter.assessment!.machine_recommendation : ""}
                            </span>
                          )}
                        </TappableInfo>
                      ) : null}
                    </div>
                  ) : (
                    <span className={mutedTextClass}>Not yet assessed</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </>
  );
}
