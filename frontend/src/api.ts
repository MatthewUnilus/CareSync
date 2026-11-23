import { detectPlatform } from "./runtime";
import { apiUrl, readApiBaseUrlOverride } from "./runtimeConfig";

export type Role = "clinical" | "administrator";

export type Sex = "female" | "male" | "other" | "unspecified";

export interface CurrentUser {
  id: number;
  email: string;
  display_name: string;
  role: Role;
}

export interface AccessResponse {
  role: Role;
  message: string;
}

export interface Patient {
  id: number;
  full_name: string;
  /**
   * The hospital number a Patient is identified by, when one was recorded.
   * Optional: a walk-in with no number is still a Patient. Two Patients who
   * share a name are separate records once both carry a number.
   */
  hospital_number: string | null;
  age: number;
  sex: Sex;
  contact_phone: string;
  contact_email: string | null;
  registered_at: string;
}

export interface NewPatient {
  full_name: string;
  /** Optional on registration; sent as `null` when left blank. */
  hospital_number: string | null;
  age: number;
  sex: Sex;
  contact_phone: string;
  contact_email: string | null;
}

export interface BloodPressure {
  systolic: number;
  diastolic: number;
}

/**
 * The eight readings of one set of vital signs.
 *
 * Every value is a plain number. The server owns the reference range that marks
 * a reading abnormal (ADR 0010), so the client sends values and never judges
 * them; it reads the mark back on the response.
 */
export interface ObservationReading {
  pain_level: number;
  illness_duration_hours: number;
  temperature_c: number;
  heart_rate_bpm: number;
  respiratory_rate_bpm: number;
  blood_pressure: BloodPressure;
  oxygen_saturation_percent: number;
}

/**
 * A set of vitals as charted against an Encounter or an Admission, as sent to
 * the chart's write routes. Matching the server's `ObservationPayload`: every
 * reading is required and only the notes are optional.
 */
export interface ObservationPayload extends ObservationReading {
  notes: string | null;
}

/**
 * The reason for a visit together with the first set of vitals, as sent when a
 * visit is opened.
 *
 * A visit no longer holds vital signs; every set of vitals is its own
 * Observation (ADR 0008), so the intake records the reason and charts the first
 * Observation in one act. Matching the server's `IntakePayload`.
 */
export interface Intake extends ObservationPayload {
  presenting_complaint: string;
}

/**
 * The reason for a visit alone, as sent when a visit is opened before any vitals
 * are measured. Matching the server's `VisitReasonPayload`.
 */
export interface VisitReasonIntake {
  presenting_complaint: string;
}

/**
 * The set of readings that immediately preceded another Observation, for the
 * chart to show beside the current one. Carries the time it was taken as well
 * as the readings, so the comparison can name when the earlier set was taken.
 */
export interface PreviousObservation extends ObservationPayload {
  taken_at: string;
}

/**
 * One Observation as the server returns it: its readings, the time they were
 * taken and who took them, the readings that fell outside their reference range
 * (marked for display only — ADR 0010), and the readings that immediately
 * preceded it so the direction of travel reads beside the current set.
 */
export interface Observation extends ObservationPayload {
  id: number;
  /** Exactly one of `encounter_id` / `admission_id` is set, never both. */
  encounter_id: number | null;
  admission_id: number | null;
  taken_at: string;
  actor: { id: number; display_name: string };
  /**
   * Whether the published adult reference ranges apply to this Patient. When
   * false — a child, for whom the adult ranges do not apply — no reading is
   * marked, so `abnormal_fields` is empty and the chart says why (ADR 0010).
   */
  reference_range_applies: boolean;
  /**
   * The names of the readings outside their reference range. The client renders
   * the mark from this list rather than re-deriving the thresholds, so the
   * bounds live in exactly one place (ADR 0010).
   */
  abnormal_fields: string[];
  /** The readings immediately preceding this set, or null for the first. */
  previous: PreviousObservation | null;
}

export interface Encounter {
  id: number;
  arrived_at: string;
  ended_at: string | null;
  status: "open" | "ended";
  patient: Patient;
  reason_for_visit: string;
}

/**
 * Patients matching a search fragment. A discovery result, not an identity
 * decision: several records may come back for one query, and the caller
 * chooses. The server never treats a name alone as an identity match.
 */
export interface PatientSearchResults {
  patients: Patient[];
}

/**
 * One Patient's Encounters over time, oldest first.
 */
export interface PatientHistory {
  patient: Patient;
  encounters: Encounter[];
}

/**
 * An inpatient stay on a ward: where the Patient is, for how long, and the
 * Encounter it came from when the patient was seen first (ADR 0008). An
 * Admission is separate from an Encounter — an Encounter is a visit with a
 * reason and an end, an Admission is a period of inpatient care with a
 * location — so a ward and a bed never sit on an Encounter.
 */
export interface WardAdmission {
  id: number;
  patient: Patient;
  ward: string;
  bed: string;
  admitted_at: string;
  discharged_at: string | null;
  /** The Encounter this stay came from, or null for a direct admission. */
  encounter_id: number | null;
  status: "open" | "discharged";
}

/**
 * One open Admission as the Ward Board returns it: the stay plus the latest
 * Observation charted against it and the counts of outstanding work the later
 * ward features fill in.
 *
 * Every count is tallied from the record on read and stored nowhere, so none of
 * it can drift. The board's order and these figures are the server's; the client
 * renders them as given and never computes a score, a priority or a re-order
 * from them.
 */
export interface BoardAdmission extends WardAdmission {
  latest_observation: Observation | null;
  outstanding_medication_count: number;
  overdue_medication_count: number;
  due_medication_count: number;
  open_task_count: number;
  unreviewed_result_count: number;
}

/** The open Admissions, already ordered by outstanding work by the server. */
export interface WardBoard {
  admissions: BoardAdmission[];
}

/**
 * A person a Task can be assigned to (or who raised one), as the ward's staff
 * list returns them: an id and the name to show.
 */
export interface TaskPerson {
  id: number;
  display_name: string;
}

/**
 * A Task: a unit of work raised against an Admission by a Clinical user, either
 * by hand from a patient's page or from a saved Ward Round Entry note
 * (CONTEXT.md, ticket 33).
 *
 * It is neither the instruction nor a Nursing Note. The description is free text
 * as given; the due time is optional, so work with a deadline is distinguishable
 * from work without one; and the assignee is optional, so both an assigned
 * caseload and a shared ward work. Marking it done records who and when, in the
 * same transaction as the change. `overdue` is the server's mark at the moment of
 * the read — the client shows the word and never re-derives the boundary, and
 * nothing acts on an overdue Task: it is not escalated, reassigned or closed.
 */
export interface Task {
  id: number;
  admission_id: number;
  patient: Patient;
  description: string;
  due_at: string | null;
  assignee: TaskPerson | null;
  author: TaskPerson;
  status: "open" | "done";
  completed_by: TaskPerson | null;
  completed_at: string | null;
  overdue: boolean;
  /** The Ward Round Entry note this Task was raised from, or null for a hand-raised Task. */
  note_id: number | null;
}

/** The ward's staff, the people a Task can be assigned to. */
export interface WardStaff {
  users: TaskPerson[];
}

/** Tasks as the server returns them. */
export interface WardTasks {
  tasks: Task[];
}

/**
 * The fields of a new Task, as sent to raise one. `due_at` is an ISO 8601 instant
 * or null for work with no deadline; `assignee_user_id` is a staff id or null to
 * leave the Task unassigned.
 */
export interface NewTaskPayload {
  description: string;
  due_at: string | null;
  assignee_user_id: number | null;
}

/**
 * One frequency's round times: the clock times of day the frequency maps to, as
 * the ward's convention holds them (ADR 0011). The policy is served from one
 * module so a hospital's own set replaces the default in one place, and it is
 * shown to the reader — a round time is a convention, not clinical advice.
 *
 * The times are provisional **UTC** clock times: this build carries no ward
 * timezone, so the schedule is placed on the UTC clock and the due list is asked
 * for and shown on the UTC clock to match.
 */
export interface MedicationRoundTime {
  /**
   * The frequency key an order carries, one the policy serves, e.g.
   * `once_daily` or `twice_daily` (not a shorthand such as `OD`/`BD`).
   */
  key: string;
  /** The frequency's human label, e.g. `Once daily`. */
  label: string;
  /** The clock times the frequency maps to, each `HH:MM` on the UTC clock. */
  times: string[];
}

/** The ward's frequency-to-round-time policy, the single definition of the convention. */
export interface MedicationRoundTimes {
  frequencies: MedicationRoundTime[];
}

/**
 * A Medication Order: the transcription of a medication instruction a doctor
 * already gave, recorded against an Admission (ADR 0011).
 *
 * It is not a prescription. The system calculates no dose, checks no dose
 * against a maximum and checks no interaction or allergy, because it holds none
 * of that data. Its clinical fields — drug, dose, route, frequency and start
 * time — are frozen when it is written, so a change is a stop and a new order
 * and both stay in the record.
 */
export interface MedicationOrder {
  id: number;
  admission_id: number;
  drug: string;
  dose: string;
  route: string;
  /** The frequency key, one the round-times policy serves (e.g. `once_daily`). */
  frequency: string;
  start_at: string;
  /** Who gave the instruction being transcribed, as free text (e.g. "Dr Okafor"). */
  instructed_by: string;
  status: "active" | "stopped";
  stopped_at: string | null;
}

/** One Admission's orders, as the server returns them. */
export interface MedicationOrders {
  orders: MedicationOrder[];
}

/**
 * The fields of a new order, as sent to transcribe an instruction. The client
 * sends the clinical fields as given and computes none of them.
 */
export interface MedicationOrderPayload {
  drug: string;
  dose: string;
  route: string;
  frequency: string;
  start_at: string;
  instructed_by: string;
}

/**
 * One dose due from an open order, derived at read time from the order and its
 * frequency's round times and stored nowhere (ADR 0011).
 *
 * `overdue` is the server's mark at the moment of the read; the client shows the
 * word and never re-derives the boundary. Nothing acts on an overdue dose.
 */
export interface MedicationDueDose {
  order_id: number;
  admission_id: number;
  patient: Patient;
  drug: string;
  dose: string;
  route: string;
  due_at: string;
  overdue: boolean;
}

/** Every dose due across the ward in a window, already ordered by due time. */
export interface MedicationDueList {
  doses: MedicationDueDose[];
}

/**
 * One reason a dose was not given, as the server fixes the set (ticket 35).
 *
 * The set is the server's one definition, offered to the client rather than
 * hard-coded, so a ward's own words replace it in one place. `requires_text`
 * marks the reason that must carry free text (the "other" case); free text is
 * permitted only for that reason, so the reason set stays reportable.
 */
export interface MedicationAdministrationReason {
  key: string;
  label: string;
  requires_text: boolean;
}

/** The fixed reason set a not-given dose is answered with. */
export interface MedicationAdministrationReasons {
  reasons: MedicationAdministrationReason[];
}

/**
 * The fixed outcome set for a recorded dose: given, withheld, refused or
 * unavailable. Not giving a dose is as recordable as giving it.
 */
export type MedicationAdministrationOutcome =
  | "given"
  | "withheld"
  | "refused"
  | "unavailable";

/** The reason held on a recorded dose, with its free text where one was given. */
export interface MedicationAdministrationReasonRef {
  key: string;
  label: string;
  text: string | null;
}

/**
 * One Medication Administration: a dose recorded against a due slot of an order
 * (ticket 35, CONTEXT.md — Medication Administration).
 *
 * It is append-only and records what a nurse attests to. There is no barcode or
 * wristband verification and the record does not claim any. `late` is the
 * server's mark that the record's `recorded_at` followed the slot's `due_at`: the
 * client shows the word and never re-derives it. Nothing is escalated and no
 * order changes on an administration.
 */
export interface MedicationAdministration {
  id: number;
  order_id: number;
  admission_id: number;
  drug: string;
  dose: string;
  route: string;
  /** The due slot this record answers, an ISO 8601 instant on the UTC clock. */
  due_at: string;
  outcome: MedicationAdministrationOutcome;
  /** The reason, present only where the outcome is not given. */
  reason: MedicationAdministrationReasonRef | null;
  recorded_at: string;
  actor: { id: number; display_name: string };
  /** The server's mark that the record came after the due time; shown, not derived. */
  late: boolean;
}

/**
 * The fields of a new administration, as sent to record a dose. `due_at` is the
 * slot's identity, so the (order, due time) pair can be recorded once. The reason
 * is present only where the outcome is not given, and `reason_text` only where
 * the chosen reason requires it.
 */
export interface MedicationAdministrationPayload {
  due_at: string;
  outcome: MedicationAdministrationOutcome;
  reason_key: string | null;
  reason_text: string | null;
}

/**
 * One slot of an order's administration grid: what was due and what happened to
 * it. `state` and any times are the server's; the client shows them and derives
 * no clinical judgement of its own.
 */
export interface MedicationAdministrationGridSlot {
  due_at: string;
  state: string;
  administration: MedicationAdministration | null;
}

/**
 * The order a grid is charted for: the clinical fields and derived condition, so
 * the chart reads as the paper chart it replaces. It omits `instructed_by`, which
 * belongs to the transcription, not the doses.
 */
export interface MedicationAdministrationGridOrder {
  id: number;
  admission_id: number;
  drug: string;
  dose: string;
  route: string;
  frequency: string;
  start_at: string;
  status: "active" | "stopped";
  stopped_at: string | null;
}

/**
 * A week of one order's doses as a grid — the shape a medication chart takes on
 * paper and what ticket 37 prints. `order` is the order the slots belong to.
 */
export interface MedicationAdministrationGrid {
  order: MedicationAdministrationGridOrder;
  slots: MedicationAdministrationGridSlot[];
}

/**
 * One slot of an admission's administration history: a dose that was due from
 * one of its orders and what happened to it, so the record reads as what was due,
 * what happened, when and by whom.
 */
export interface MedicationAdministrationHistorySlot {
  order_id: number;
  drug: string;
  dose: string;
  route: string;
  due_at: string;
  state: string;
  administration: MedicationAdministration | null;
}

/** An admission's administrations in a window, already ordered by due time. */
export interface MedicationAdministrationHistory {
  slots: MedicationAdministrationHistorySlot[];
}

/**
 * One field of a Note Template, as the server defines it. The client renders the
 * fields a template carries and never hard-codes what a template holds, so a
 * change to a template's fields is a server change with no client change.
 */
export interface NoteTemplateField {
  key: string;
  label: string;
}

/**
 * One Note Template: a fixed vocabulary of fields a nurse writes against. The
 * definitions live on the server (ADR 0013); the client asks for them and builds
 * the form from whatever comes back.
 */
export interface NoteTemplate {
  key: string;
  label: string;
  fields: NoteTemplateField[];
}

/** The Note Templates, served as a fixed vocabulary. */
export interface NoteTemplates {
  templates: NoteTemplate[];
}

/**
 * The values a new note starts with, taken from the patient's latest
 * Observation so the vitals are there to confirm or amend rather than to
 * retype. `source_observation` names where the values came from and is null
 * when nothing could be prefilled, so the client can say so rather than
 * implying the numbers are the nurse's own.
 */
export interface NotePrefill {
  /** The prefilled values, keyed by the template's field keys. */
  fields: Record<string, string>;
  source_observation: {
    taken_at: string;
    actor: { id: number; display_name: string };
  } | null;
}

/** One field of a written note: the key it was written against and its free text. */
export interface NursingNoteField {
  key: string;
  value: string;
}

/**
 * One nursing note as the server returns it: the Admission it belongs to, the
 * template it was written from, its author and time, the fields it carries, and
 * the correction links. A note that corrects another names it in
 * `corrects_note_id`; a note that has been corrected names its replacement in
 * `corrected_by_note_id` and stays in the record, shown as corrected. Both links
 * are one-directional: a correction points back, the corrected note is marked
 * forward.
 */
export interface NursingNote {
  id: number;
  admission_id: number;
  template_key: string;
  author: { id: number; display_name: string };
  recorded_at: string;
  corrects_note_id: number | null;
  corrected_by_note_id: number | null;
  fields: NursingNoteField[];
}

/** One Admission's notes, already in time order by the server. */
export interface NursingNotes {
  notes: NursingNote[];
}

/** The shape sent to write a note: a template, its fields as free text, and the note this one corrects (or null). */
export interface NursingNotePayload {
  template_key: string;
  fields: NursingNoteField[];
  corrects_note_id: number | null;
}

export interface DailyVisitsReport {
  day: string;
  starts_at: string;
  ends_at: string;
  volume: number;
  throughput: number;
  awaiting: number;
}

export interface PerformanceEntry {
  encounter_id: number;
  arrived_at: string;
  ended_at: string;
  waiting_seconds: number;
}

export interface PerformanceReport {
  completed: number;
  average_waiting_seconds: number;
  entries: PerformanceEntry[];
}

export interface AuditEntry {
  id: number;
  /** The machine key, used for filtering and counting. */
  action: string;
  /** The action's human label, served from beside the enum; render this. */
  action_label: string;
  detail: string | null;
  recorded_at: string;
  actor: {
    id: number;
    display_name: string;
  };
  patient_id: number | null;
  encounter_id: number | null;
}

export interface AuditLog {
  entries: AuditEntry[];
}

interface ApiResult<T> {
  body: T;
  status: number;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * A locked session is refused with 423, distinct from 401. Any request can
 * return it, including the background polls the workspaces run, so the lock
 * is announced as an event rather than left to each caller: the app listens
 * and shows the lock screen, whichever screen was open when the lock landed.
 */
export const SESSION_LOCKED_EVENT = "caresync:session-locked";

/**
 * A caught error as a sentence a user can act on.
 *
 * A server refusal carries its own message; anything else means the request
 * never reached the server, which the reader is told plainly rather than shown
 * a stack or a blank.
 */
export function errorText(caught: unknown): string {
  return caught instanceof ApiError
    ? caught.message
    : "Unable to reach the server.";
}

async function requestDetailed<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  // Read the base URL per request: the native Server setting can change
  // without reloading the app. The web build resolves to "", so the request
  // stays relative and same-origin exactly as before.
  const url = apiUrl(path, {
    platform: detectPlatform(),
    configured: import.meta.env.VITE_API_BASE_URL,
    override: readApiBaseUrlOverride(),
  });

  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return { body: undefined as T, status: response.status };
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`;
    if (response.status === 423) {
      window.dispatchEvent(new Event(SESSION_LOCKED_EVENT));
    }
    throw new ApiError(response.status, detail);
  }

  return { body: body as T, status: response.status };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await requestDetailed<T>(path, init)).body;
}

export const api = {
  me: () => request<CurrentUser>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<CurrentUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  /*
   * Lock and switch-user. Locking hides the workspace without ending the
   * session; the server refuses a locked session on every route until unlock
   * succeeds. Switch-user is the deliberate handover: it ends the session and
   * returns to sign-in, and is the same server effect as logout.
   */
  lock: () => request<void>("/api/auth/lock", { method: "POST" }),
  unlock: (password: string) =>
    request<CurrentUser>("/api/auth/unlock", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  switchUser: () => request<void>("/api/auth/switch-user", { method: "POST" }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  access: (scope: Role) =>
    request<AccessResponse>(`/api/${scope}/access`),
  registerPatient: (patient: NewPatient) =>
    requestDetailed<Patient>("/api/clinical/patients", {
      method: "POST",
      body: JSON.stringify(patient),
    }),
  openEncounter: (patientId: number, intake: Intake | VisitReasonIntake) =>
    request<Encounter>("/api/clinical/encounters", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId, intake }),
    }),
  getEncounter: (encounterId: number) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}`),
  recentEncounters: (limit = 10) =>
    request<{ encounters: Encounter[] }>(
      `/api/clinical/encounters?limit=${limit}`,
    ),
  /*
   * Patient search is a discovery aid. The caller must not send a blank query
   * (the server returns nothing for one), and should not debounce it into a
   * bulk list: the view deliberately fires no request until something is typed.
   */
  searchPatients: (query: string, limit = 20) =>
    request<PatientSearchResults>(
      `/api/clinical/patients?q=${encodeURIComponent(query)}&limit=${limit}`,
    ),
  patientHistory: (patientId: number) =>
    request<PatientHistory>(`/api/clinical/patients/${patientId}/encounters`),
  /*
   * Charting a set of vitals writes one append-only Observation against its
   * subject — an Encounter or an Admission, never both. A set is unchangeable
   * once saved (ADR 0008), so there is no edit or delete route; a correction is
   * a new set. The response is the stored Observation, including the readings
   * that preceded it and the ones the server marked abnormal.
   */
  chartEncounterObservation: (encounterId: number, payload: ObservationPayload) =>
    request<Observation>(`/api/clinical/encounters/${encounterId}/observations`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  chartAdmissionObservation: (admissionId: number, payload: ObservationPayload) =>
    request<Observation>(`/api/clinical/admissions/${admissionId}/observations`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /*
   * One Patient's Observations, newest first. This is the chart's read: the
   * single time series for a Patient's vitals, across every Encounter and
   * Admission they have.
   */
  patientObservations: (patientId: number) =>
    request<{ observations: Observation[] }>(
      `/api/clinical/patients/${patientId}/observations`,
    ),
  /*
   * Attach a hospital number to an existing Patient who has none. The server is
   * the authority on identity: a number already held by another record is
   * refused with a `409`, and a malformed one with a `422`. The Patient is
   * returned carrying the number, which the caller mirrors into the view.
   */
  attachHospitalNumber: (patientId: number, hospitalNumber: string) =>
    request<Patient>(`/api/clinical/patients/${patientId}/hospital-number`, {
      method: "POST",
      body: JSON.stringify({ hospital_number: hospitalNumber }),
    }),
  /*
   * Ending a visit takes no body: the end instant is the server's, recorded at
   * the moment of the action. An already-ended visit is a `409`; an unknown
   * Encounter is a `404`.
   */
  endEncounter: (encounterId: number) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}/end`, {
      method: "POST",
    }),

  /*
   * Ward admissions and the board.
   *
   * Admitting records an inpatient stay on a ward, optionally linking the visit
   * the patient was seen in first so the visit and the stay read as one history.
   * A direct admission leaves `encounter_id` null. A location move keeps the
   * board honest about where a patient is; discharging closes the stay and keeps
   * its history. Each mutation writes one Audit Entry in the same transaction as
   * the change (the server's job, not the client's).
   *
   * The board is derived on every read and stores nothing: the server returns the
   * open Admissions ordered by outstanding work, with the latest Observation and
   * the counts the later ward features fill in. The client shows the server's
   * order and counts and never re-ranks them.
   */
  wardBoard: () => request<WardBoard>("/api/ward/board"),
  patientAdmissions: (patientId: number) =>
    request<{ admissions: WardAdmission[] }>(
      `/api/ward/admissions?patient_id=${patientId}`,
    ),
  admitPatient: (
    patientId: number,
    ward: string,
    bed: string,
    encounterId: number | null,
  ) =>
    request<WardAdmission>("/api/ward/admissions", {
      method: "POST",
      body: JSON.stringify({
        patient_id: patientId,
        ward,
        bed,
        encounter_id: encounterId,
      }),
    }),
  moveAdmission: (admissionId: number, ward: string, bed: string) =>
    request<WardAdmission>(`/api/ward/admissions/${admissionId}/move`, {
      method: "POST",
      body: JSON.stringify({ ward, bed }),
    }),
  dischargeAdmission: (admissionId: number) =>
    request<WardAdmission>(`/api/ward/admissions/${admissionId}/discharge`, {
      method: "POST",
    }),

  /*
   * Medication orders, round times and the due list (ADR 0011).
   *
   * An order transcribes an instruction a doctor already gave: the client sends
   * the drug, dose, route, frequency, start time and who instructed it, and the
   * server freezes those fields. Nothing is computed here — no dose, no maximum,
   * no interaction or allergy check — and a change is a stop and a new order. The
   * round times a frequency maps to are served from one module and shown to the
   * reader rather than assumed. The due list is derived on read from the open
   * orders and those round times and is stored nowhere, so it cannot drift from
   * the orders behind it. The round times are provisional UTC clock times, so the
   * due window is a UTC day and due times are shown on the UTC clock.
   */
  medicationRoundTimes: () =>
    request<MedicationRoundTimes>("/api/ward/medications/round-times"),
  writeMedicationOrder: (
    admissionId: number,
    payload: MedicationOrderPayload,
  ) =>
    request<MedicationOrder>(
      `/api/ward/admissions/${admissionId}/medication-orders`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  admissionMedicationOrders: (admissionId: number) =>
    request<MedicationOrders>(
      `/api/ward/admissions/${admissionId}/medication-orders`,
    ),
  stopMedicationOrder: (orderId: number) =>
    request<MedicationOrder>(`/api/ward/medication-orders/${orderId}/stop`, {
      method: "POST",
    }),
  /*
   * A window of doses due across the ward, `[from, to)`, as ISO 8601 instants.
   * The round times are provisional UTC clock times, so a caller asks for the
   * UTC calendar day (`Date.UTC` bounds) to match the schedule.
   */
  medicationDue: (from: string, to: string) =>
    request<MedicationDueList>(
      `/api/ward/medications/due?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  /*
   * Medication administrations (ticket 35, CONTEXT.md — Medication
   * Administration).
   *
   * A dose is recorded as given, withheld, refused or unavailable against one due
   * slot; not giving a dose is as recordable as giving it. The reason set is the
   * server's and is read, not hard-coded, and a reason is required when the dose
   * was not given, with free text only where the chosen reason requires it. A
   * recorded slot leaves the due list and the record stays readable. A dose given
   * after its due time can still be recorded and comes back marked `late`; the
   * server sends the states and times and the client derives none of them, and
   * nothing is escalated and no order changes. The record says what a nurse
   * attests to: there is no barcode or wristband verification and none is
   * claimed. The grid is a week of one order's doses, the shape of a paper chart.
   */
  medicationAdministrationReasons: () =>
    request<MedicationAdministrationReasons>(
      "/api/ward/medication-administration-reasons",
    ),
  recordMedicationAdministration: (
    orderId: number,
    payload: MedicationAdministrationPayload,
  ) =>
    request<MedicationAdministration>(
      `/api/ward/medication-orders/${orderId}/administrations`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  /*
   * A week of one order's doses as a grid, `[from, to)`, as ISO 8601 instants.
   * The round times are provisional UTC clock times, so a caller asks for UTC
   * calendar days (`Date.UTC` bounds) to match the schedule.
   */
  medicationAdministrationGrid: (orderId: number, from: string, to: string) =>
    request<MedicationAdministrationGrid>(
      `/api/ward/medication-orders/${orderId}/administration-grid?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  /*
   * An admission's administration history in a window, `[from, to)`. As with the
   * due list and the grid, the calendar window is a UTC day to match the schedule.
   */
  admissionMedicationAdministrations: (
    admissionId: number,
    from: string,
    to: string,
  ) =>
    request<MedicationAdministrationHistory>(
      `/api/ward/admissions/${admissionId}/medication-administrations?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  /*
   * Tasks and the ward round (ticket 33).
   *
   * A Task is a unit of work raised against an Admission, by hand from a
   * patient's page or from a saved Ward Round Entry note, and several Tasks can
   * be raised from one entry in a single call because a round gives several
   * instructions in one conversation. It carries an optional due time and an
   * optional assignee, and a Clinical user marks it done, which records who and
   * when. Overdue is the server's mark on read: the client shows the word and
   * nothing acts on it — a Task is never escalated, reassigned or closed by the
   * system. Raising, completing and assigning each write one Audit Entry in the
   * same transaction as the change (the server's job, not the client's). The
   * cross-patient list is filtered to one assignee by `mine`; that is assignment
   * only, not a notion of whose patients these are.
   */
  wardStaff: () => request<WardStaff>("/api/ward/staff"),
  createAdmissionTask: (admissionId: number, payload: NewTaskPayload) =>
    request<Task>(`/api/ward/admissions/${admissionId}/tasks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createWardRoundTasks: (
    admissionId: number,
    noteId: number,
    tasks: NewTaskPayload[],
  ) =>
    request<WardTasks>(`/api/ward/admissions/${admissionId}/ward-round-tasks`, {
      method: "POST",
      body: JSON.stringify({ note_id: noteId, tasks }),
    }),
  admissionTasks: (admissionId: number) =>
    request<WardTasks>(`/api/ward/admissions/${admissionId}/tasks`),
  wardTasks: (mine: boolean, includeDone: boolean) =>
    request<WardTasks>(
      `/api/ward/tasks?mine=${mine ? "true" : "false"}&include_done=${includeDone ? "true" : "false"}`,
    ),
  completeTask: (taskId: number) =>
    request<Task>(`/api/ward/tasks/${taskId}/complete`, { method: "POST" }),
  assignTask: (taskId: number, assigneeUserId: number | null) =>
    request<Task>(`/api/ward/tasks/${taskId}/assign`, {
      method: "POST",
      body: JSON.stringify({ assignee_user_id: assigneeUserId }),
    }),
  /*
   * Nursing notes and their templates.
   *
   * The templates are a fixed vocabulary served from one module; the client
   * renders whatever fields a template carries and never hard-codes a
   * template-specific schema, so adding a field is a server change alone. A new
   * note prefills from the patient's latest Observation: the prefill route
   * returns the values keyed by the template's field keys, plus the Observation
   * they came from so the client can show the source rather than imply the nurse
   * typed them. A note is append-only — correcting one writes a new note that
   * points at the note it corrects, and the corrected note stays in the record.
   * The notes read is already in time order.
   */
  noteTemplates: () => request<NoteTemplates>("/api/ward/note-templates"),
  admissionNotePrefill: (admissionId: number, templateKey: string) =>
    request<NotePrefill>(
      `/api/ward/admissions/${admissionId}/note-prefill?template_key=${encodeURIComponent(templateKey)}`,
    ),
  admissionNotes: (admissionId: number) =>
    request<NursingNotes>(`/api/ward/admissions/${admissionId}/notes`),
  writeAdmissionNote: (admissionId: number, payload: NursingNotePayload) =>
    request<NursingNote>(`/api/ward/admissions/${admissionId}/notes`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /*
   * Reports are read-only derivations. The daily figure defaults to the
   * server's UTC day; the performance figure is a whole-record view.
   */
  dailyVisitsReport: () =>
    request<DailyVisitsReport>("/api/administrator/reports/daily-visits"),
  performanceReport: () =>
    request<PerformanceReport>("/api/administrator/reports/performance"),

  /*
   * The audit log is an append-only record of clinical mutations, oldest first.
   * Each entry is recorded in the same transaction as the act it describes.
   * Optional encounter_id filter narrows to one Encounter.
   */
  auditLog: (encounterId?: number) =>
    request<AuditLog>(
      `/api/administrator/audit-log${encounterId ? `?encounter_id=${encounterId}` : ""}`,
    ),
};
