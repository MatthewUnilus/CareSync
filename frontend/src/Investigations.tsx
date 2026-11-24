import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import type { ChipColor } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@/components/base/segmented-control/segmented-control";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, ApiError, errorText } from "./api";
import type {
  BoardAdmission,
  Investigation,
  InvestigationState,
  NewInvestigationPayload,
} from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
} from "./design";
import { formatInstant } from "./queueDisplay";
import { usePolling } from "./usePolling";

/**
 * Investigations and the two chase lists (ticket 36, ADR 0012).
 *
 * An Investigation is a test a doctor requested against an Admission, followed
 * to its result and marked reviewed. This module holds the two cross-patient
 * worklists a nurse works from — results nobody has read yet, and tests nobody
 * has a result for yet — and the per-Admission writer and record mounted from a
 * board row.
 *
 * This is a progress list, not a results viewer. The system tracks progress and
 * the review act only: it never reads, parses, flags or interprets a result
 * value, shows no reference range and marks nothing abnormal, and produces no
 * suggestion. The test name, the requested-by name and the result note are free
 * text as given. The four states are the server's; the client shows them and
 * derives no clinical meaning of its own.
 *
 * The two worklists are one table read two ways, so they are two views over one
 * read with a single toggle, not two features.
 */

/** Operational data: the cross-patient worklists re-read every five seconds. */
const INVESTIGATION_POLL_INTERVAL_MS = 5_000;

/** The server's four states as they are shown to a reader. */
const STATE_LABELS: Record<InvestigationState, string> = {
  requested: "requested",
  sample_taken: "sample taken",
  // A freshly available result is not overdue; it is simply awaiting review, so
  // the state reads neutrally rather than as an alarm.
  result_available: "result awaiting review",
  reviewed: "reviewed",
};

/**
 * A Chip colour for a state. The server's state is shown as given; this only
 * chooses how it reads, and never decides it.
 */
function stateColor(state: InvestigationState): ChipColor {
  switch (state) {
    case "requested":
      return "neutral";
    case "sample_taken":
      return "blue";
    case "result_available":
      return "neutral";
    case "reviewed":
      return "lime";
  }
}

/**
 * The two cross-patient worklists, mounted once at the board level: results
 * awaiting review, so nothing goes unread, and tests awaiting a result, so the
 * nurse knows what to chase. Both are one record read two ways, so a single
 * `SegmentedControl` switches between them over one read rather than two
 * features.
 *
 * It is operational data, so it re-reads every five seconds through `usePolling`.
 * Every action is explicit and writes through the server, and the board is
 * re-read after a write so its results-awaiting-review count follows.
 */
export default function InvestigationWorklists({
  admissions,
  onChanged,
}: {
  /** The open Admissions, so a row can name where its patient is. */
  admissions: BoardAdmission[];
  /** Called after a write, so the board's results-awaiting-review count refreshes. */
  onChanged: () => Promise<void> | void;
}) {
  const [view, setView] = useState<"review" | "result" | "late">("review");
  const [awaitingReview, setAwaitingReview] = useState<Investigation[] | null>(
    null,
  );
  const [lateResults, setLateResults] = useState<Investigation[] | null>(null);
  const [awaitingResult, setAwaitingResult] = useState<Investigation[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestRef = useRef(0);

  // One read serves both views: the two lists are the same record filtered two
  // ways, so they are fetched together and the toggle only chooses which is
  // shown, with both counts visible on the control.
  const load = useCallback(async () => {
    const requestId = ++requestRef.current;
    try {
      const [review, result, late] = await Promise.all([
        api.investigationsAwaitingReview(),
        api.investigationsAwaitingResult(),
        api.lateInvestigationResults(),
      ]);
      if (requestRef.current !== requestId) {
        return;
      }
      setAwaitingReview(review.investigations);
      setAwaitingResult(result.investigations);
      setLateResults(late.investigations);
      setLoadError(null);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, []);

  usePolling(load, INVESTIGATION_POLL_INTERVAL_MS);

  // Where each admission's patient is, as the board holds it.
  const locations = new Map(
    admissions.map((admission) => [
      admission.id,
      `${admission.ward} · ${admission.bed}`,
    ]),
  );

  // A write from either list changes the list and the board's counts.
  const handleChanged = useCallback(async () => {
    await load();
    await onChanged();
  }, [load, onChanged]);

  const shown = { review: awaitingReview, result: awaitingResult, late: lateResults }[view];
  const isReview = view === "review";

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">
        Investigations to chase
      </h3>
      <p className={mutedTextClass}>
        Track outstanding tests, results awaiting review, and laboratory results
        that still need review after discharge.
      </p>
      <p className="text-body-2-regular text-text-secondary">
        This tracks progress and the review act only. It is not a results viewer:
        a result note is the laboratory&rsquo;s words as given, and this system
        never reads, parses, flags or interprets a value, shows no reference range
        and marks nothing abnormal.
      </p>

      <section className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          aria-label="Investigation worklist"
          selectedKeys={[view]}
          onSelectionChange={(keys) => {
            if (keys.has("review")) {
              setView("review");
            } else if (keys.has("result")) {
              setView("result");
            } else if (keys.has("late")) {
              setView("late");
            }
          }}
        >
          <SegmentedControlItem id="review">
            {`Results awaiting review${
              awaitingReview !== null ? ` (${awaitingReview.length})` : ""
            }`}
          </SegmentedControlItem>
          <SegmentedControlItem id="result">
            {`Tests awaiting a result${
              awaitingResult !== null ? ` (${awaitingResult.length})` : ""
            }`}
          </SegmentedControlItem>
          <SegmentedControlItem id="late">
            Late results after discharge{lateResults ? ` (${lateResults.length})` : ""}
          </SegmentedControlItem>
        </SegmentedControl>
        <Button
          variant="secondary"
          className="min-h-11"
          onClick={() => void load()}
        >
          Refresh lists
        </Button>
      </section>

      {loadError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void load()}
            >
              Retry loading investigations
            </Button>
          </footer>
        </section>
      ) : shown === null ? (
        <p className={mutedTextClass}>Loading investigations…</p>
      ) : shown.length === 0 ? (
        <p className={mutedTextClass}>
          {view === "late" ? "No late results are awaiting review." : isReview
            ? "No results are awaiting review. A result appears here as soon as it is recorded, and leaves once it is marked reviewed."
            : "No tests are awaiting a result. A test appears here when it is requested, and leaves once a result is recorded."}
        </p>
      ) : (
        <ol className="flex flex-col gap-4">
          {shown.map((investigation) => (
            <InvestigationItem
              key={investigation.id}
              investigation={investigation}
              location={view === "late"
                ? `Discharged · Admission #${investigation.admission_id}`
                : locations.get(investigation.admission_id)}
              discharged={view === "late"}
              onChanged={handleChanged}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

/**
 * One Admission's Investigations: the requester and the record of what was
 * requested, mounted from a patient's row on the board. Every state is shown
 * together, so the record is the whole history — requested, sample taken, result
 * available and reviewed — rather than only the outstanding work.
 */
export function AdmissionInvestigations({
  admissionId,
  onInvestigationsChanged,
  discharged = false,
}: {
  admissionId: number;
  /** Called after a write, so the board's counts and the worklists refresh. */
  onInvestigationsChanged?: () => Promise<void> | void;
  discharged?: boolean;
}) {
  const [investigations, setInvestigations] = useState<Investigation[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);

  const [testName, setTestName] = useState("");
  const [instructedBy, setInstructedBy] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const load = useCallback(async (id: number) => {
    const requestId = ++requestRef.current;
    try {
      const { investigations: loaded } = await api.admissionInvestigations(id);
      if (requestRef.current !== requestId) {
        return;
      }
      setInvestigations(loaded);
      setLoadError(null);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, []);

  // A change of Admission is a change of patient: clear the requester and
  // re-read, so nothing written for the previous patient survives under the new
  // one.
  useEffect(() => {
    setTestName("");
    setInstructedBy("");
    setSaveError(null);
    setInvestigations(null);
    return () => {
      requestRef.current += 1;
    };
  }, [admissionId]);
  const loadCurrent = useCallback(() => load(admissionId), [load, admissionId]);
  usePolling(loadCurrent, INVESTIGATION_POLL_INTERVAL_MS);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = testName.trim();
    if (!trimmed) {
      setSaveError("Name the test to request.");
      return;
    }
    const payload: NewInvestigationPayload = {
      test_name: trimmed,
      // Optional: a nurse can record the test without naming the requester.
      instructed_by: instructedBy.trim() || null,
    };
    setSaving(true);
    setSaveError(null);
    try {
      await api.recordInvestigation(admissionId, payload);
      toast.success("Investigation requested.");
      setTestName("");
      setInstructedBy("");
      await load(admissionId);
      // A new request changes the board's counts and the chase lists.
      await onInvestigationsChanged?.();
    } catch (caught) {
      setSaveError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={cardClass}>
      <h4 className="text-title-3-medium text-text-primary">Investigations</h4>
      {!discharged && <p className={mutedTextClass}>
        Record a test requested for this patient and follow it to its result. The
        test name is the request in the words it was given; there is no fixed list.
        This tracks progress and the review act only — it is not a results viewer,
        so a result note is the laboratory&rsquo;s words as given and is never
        read, parsed, flagged or interpreted, and nothing is suggested.
      </p>}

      {!discharged && <form className="flex flex-col gap-4" onSubmit={save}>
        <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2">
          <legend className={sectionLabelClass}>Request a test</legend>
          <Input
            className="sm:col-span-2"
            label="Test"
            hint="As requested, e.g. FBC, urgent CT head"
            value={testName}
            isDisabled={saving}
            onChange={setTestName}
          />
          <Input
            className="sm:col-span-2"
            label="Requested by (doctor)"
            hint="Who requested the test, e.g. Dr Okafor; leave blank if not recorded"
            value={instructedBy}
            isDisabled={saving}
            onChange={setInstructedBy}
          />
        </fieldset>

        {saveError !== null ? (
          <p className={noticeClass.error} role="alert">
            {saveError}
          </p>
        ) : null}

        <footer>
          <Button type="submit" className="min-h-11" disabled={saving}>
            {saving ? "Saving…" : "Request test"}
          </Button>
        </footer>
      </form>}

      <section className="flex flex-col gap-3">
        <h4 className={sectionLabelClass}>Recorded investigations</h4>
        <p className="text-body-2-regular text-text-secondary">
          Every test for this patient with its progress: requested, sample taken,
          result available and reviewed are shown together, so a reviewed result
          stays in the record.
        </p>

        {loadError !== null ? (
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
        ) : null}

        {investigations === null ? (
          loadError !== null ? null : (
            <p className={mutedTextClass}>Loading investigations…</p>
          )
        ) : investigations.length === 0 ? (
          <p className={mutedTextClass}>
            No investigations recorded for this patient yet.
          </p>
        ) : (
          <ol className="flex flex-col gap-4">
            {investigations.map((investigation) => (
              <InvestigationItem
                key={investigation.id}
                investigation={investigation}
                showPatient={false}
                discharged={discharged}
                onChanged={async () => {
                  await load(admissionId);
                  await onInvestigationsChanged?.();
                }}
              />
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}

/** The action a row is currently writing, so only its own button reads as busy. */
type InvestigationAction = "send" | "sample" | "result" | "review";

/**
 * One Investigation in a list: who it is for and where, the test name as
 * requested, the state and the progress times, the result note when one is on the
 * record, and the next action a person takes.
 *
 * The actions are explicit and go to the server: mark the sample taken, record a
 * result as free text, or mark a result reviewed — the accountable act, which is
 * offered only once a result is available and is disabled with an explanation
 * until then. Nothing here decides anything clinically and no result value is
 * ever read, parsed or interpreted.
 */
function InvestigationItem({
  investigation,
  location,
  showPatient = true,
  discharged = false,
  onChanged,
}: {
  investigation: Investigation;
  /** Where the patient is, when the board knows it. */
  location?: string;
  /** Show the patient's name; off inside a single patient's own record. */
  showPatient?: boolean;
  discharged?: boolean;
  onChanged: () => Promise<void> | void;
}) {
  const [pending, setPending] = useState<InvestigationAction | null>(null);
  const [recording, setRecording] = useState(false);
  const [resultNote, setResultNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { state } = investigation;
  const busy = pending !== null;
  const canReview = state === "result_available" && (!discharged || investigation.result_published_by !== null);

  async function sendToLaboratory() {
    setPending("send");
    setError(null);
    try {
      await api.sendInvestigationToLab(investigation.id);
      toast.success("Investigation sent to the laboratory.");
      await onChanged();
    } catch (caught) {
      setError(errorText(caught));
      if (caught instanceof ApiError && caught.status === 409) await onChanged();
    } finally {
      setPending(null);
    }
  }

  async function takeSample() {
    setPending("sample");
    setError(null);
    try {
      await api.markInvestigationSampleTaken(investigation.id);
      toast.success("Sample marked taken.");
      await onChanged();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  }

  async function recordResult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = resultNote.trim();
    if (!trimmed) {
      setError("Record the result as the laboratory gave it.");
      return;
    }
    setPending("result");
    setError(null);
    try {
      await api.recordInvestigationResult(investigation.id, trimmed);
      toast.success("Result recorded.");
      setResultNote("");
      setRecording(false);
      await onChanged();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPending(null);
    }
  }

  async function review() {
    setPending("review");
    setError(null);
    try {
      await api.reviewInvestigation(investigation.id);
      toast.success("Result marked reviewed.");
      await onChanged();
    } catch (caught) {
      setError(errorText(caught));
      if (caught instanceof ApiError && caught.status === 409) await onChanged();
    } finally {
      setPending(null);
    }
  }

  return (
    <li className={cx(cardClass, "gap-2")}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {showPatient ? (
          <h5 className="text-body-semibold text-text-primary">
            {investigation.patient.full_name}
          </h5>
        ) : null}
        {location !== undefined ? (
          <Chip variant="caption" color="soft">
            {location}
          </Chip>
        ) : null}
        <Chip variant="bold" color={stateColor(state)}>
          {STATE_LABELS[state]}
        </Chip>
      </header>

      <p className="text-body-regular text-text-primary wrap-anywhere">
        {investigation.test_name}
      </p>

      <p className="text-body-2-regular text-text-secondary">
        Requested{" "}
        <time dateTime={investigation.requested_at} className={figureClass}>
          {formatInstant(investigation.requested_at)}
        </time>{" "}
        by <bdi>{investigation.requested_by.display_name}</bdi>
        {investigation.sample_taken_at !== null ? (
          <>
            {" · sample taken "}
            <time
              dateTime={investigation.sample_taken_at}
              className={figureClass}
            >
              {formatInstant(investigation.sample_taken_at)}
            </time>
          </>
        ) : null}
        {investigation.result_available_at !== null ? (
          <>
            {" · result available "}
            <time
              dateTime={investigation.result_available_at}
              className={figureClass}
            >
              {formatInstant(investigation.result_available_at)}
            </time>
          </>
        ) : null}
      </p>

      {investigation.instructed_by !== null ? (
        <p className="text-body-2-regular text-text-secondary">
          Requested by <bdi>{investigation.instructed_by}</bdi>
        </p>
      ) : null}

      {investigation.lab_sent_at && (
        <p className={mutedTextClass}>
          Sent to laboratory {formatInstant(investigation.lab_sent_at)} by {investigation.lab_sent_by?.display_name}.
          {investigation.lab_received_at
            ? ` Acknowledged ${formatInstant(investigation.lab_received_at)} by ${investigation.lab_received_by?.display_name}.`
            : " Awaiting acknowledgement."}
        </p>
      )}
      {investigation.result_published_by && (
        <p className={mutedTextClass}>
          Published by {investigation.result_published_by.display_name}.
        </p>
      )}
      {investigation.result_note !== null ? (
        <section className="flex flex-col gap-1">
          <h6 className={sectionLabelClass}>Result, as recorded</h6>
          <p className="text-body-regular text-text-primary wrap-anywhere whitespace-pre-wrap">
            {investigation.result_note}
          </p>
        </section>
      ) : null}

      {state === "reviewed" ? (
        <p className="text-body-2-regular text-text-secondary">
          Reviewed
          {investigation.reviewed_by !== null ? (
            <>
              {" by "}
              <bdi>{investigation.reviewed_by.display_name}</bdi>
            </>
          ) : null}
          {investigation.reviewed_at !== null ? (
            <>
              {" "}
              <time dateTime={investigation.reviewed_at} className={figureClass}>
                {formatInstant(investigation.reviewed_at)}
              </time>
            </>
          ) : null}
          .
        </p>
      ) : (!discharged || canReview) && (
        <footer className="flex flex-wrap items-end gap-2">
          {state === "requested" ? (
            <Button
              variant="secondary"
              className="min-h-11"
              disabled={busy}
              onClick={() => void takeSample()}
            >
              {pending === "sample" ? "Working…" : "Mark sample taken"}
            </Button>
          ) : null}
          {state === "sample_taken" && !investigation.lab_sent_at && (
            <Button variant="secondary" className="min-h-11" disabled={busy}
              onClick={() => void sendToLaboratory()}>
              {pending === "send" ? "Sending…" : "Send to laboratory"}
            </Button>
          )}
          {state === "sample_taken" && !investigation.lab_sent_at ? (
            <Button
              variant={recording ? "primary" : "secondary"}
              className="min-h-11"
              aria-expanded={recording}
              disabled={busy}
              onClick={() => setRecording((current) => !current)}
            >
              {recording ? "Cancel" : "Record result"}
            </Button>
          ) : null}
          <Button
            variant="secondary"
            className="min-h-11"
            disabled={busy || !canReview}
            onClick={() => void review()}
          >
            {pending === "review" ? "Working…" : "Mark reviewed"}
          </Button>
          {!canReview ? (
            <small className="text-body-2-regular text-text-secondary">
              A result must be on the record before it can be reviewed.
            </small>
          ) : null}
        </footer>
      )}

      {recording && state === "sample_taken" ? (
        <form className="flex flex-col gap-3" onSubmit={recordResult}>
          <Textarea
            rows={3}
            label="Result"
            hint="The laboratory's words as given; this system never reads or interprets a value"
            value={resultNote}
            isDisabled={busy}
            onChange={setResultNote}
          />
          <footer>
            <Button type="submit" className="min-h-11" disabled={busy}>
              {pending === "result" ? "Recording…" : "Record result"}
            </Button>
          </footer>
        </form>
      ) : null}

      {error !== null ? (
        <p className={noticeClass.error} role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}
