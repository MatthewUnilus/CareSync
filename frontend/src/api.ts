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
