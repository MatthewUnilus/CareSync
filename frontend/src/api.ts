import { detectPlatform } from "./runtime";
import { apiUrl, readApiBaseUrlOverride } from "./runtimeConfig";

export type Role = "clinical" | "administrator";

export type Sex = "female" | "male" | "other" | "unspecified";

export type UrgencyLevel = "High" | "Medium" | "Low";

/**
 * The fixed Override Reason set lives on the server
 * (`backend/app/override_reasons.py`) and is fetched from
 * `GET /api/clinical/override-reasons`, so the client never duplicates it.
 */
export type OverrideReason = string;


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
  age: number;
  sex: Sex;
  contact_phone: string;
  contact_email: string | null;
  registered_at: string;
}

export interface NewPatient {
  full_name: string;
  age: number;
  sex: Sex;
  contact_phone: string;
  contact_email: string | null;
}

export interface BloodPressure {
  systolic: number;
  diastolic: number;
}

export interface Intake {
  presenting_complaint: string;
  pain_level: number;
  illness_duration_hours: number;
  temperature_c: number;
  heart_rate_bpm: number;
  respiratory_rate_bpm: number;
  blood_pressure: BloodPressure;
  oxygen_saturation_percent: number;
  notes: string | null;
}

export interface Encounter {
  id: number;
  arrived_at: string;
  departed_at: string | null;
  status: "awaiting" | "departed";
  patient: Patient;
  intake: Intake;
  /** The governing (most recent) Assessment. */
  assessment: Assessment | null;
  /** Every Assessment, oldest first. Earlier ones keep their Overrides. */
  assessments: Assessment[];
}

export interface AssessmentSnapshot {
  presenting_complaint: string;
  age: number;
  pain_level: number;
  illness_duration_hours: number;
  temperature_c: number;
  heart_rate_bpm: number;
  respiratory_rate_bpm: number;
  blood_pressure: BloodPressure;
  oxygen_saturation_percent: number;
  notes: string | null;
}

export interface OverrideRecord {
  reason: OverrideReason;
  free_text: string | null;
  performed_at: string;
  performed_by: {
    id: number;
    display_name: string;
  };
}

export interface RedFlag {
  id: string;
  finding: string;
  citation: string;
  /**
   * Intake field names this rule keyed on, e.g. `oxygen_saturation_percent`.
   * Empty when the rule keyed on a recognised Symptom Group rather than a
   * measured value. The board marks exactly these fields as abnormal.
   */
  vitals: string[];
}

export interface Assessment {
  id: number;
  assessed_at: string;
  machine_recommendation: UrgencyLevel;
  final_decision: UrgencyLevel;
  recognised_symptom_groups: string[];
  /**
   * True when the complaint matched no Symptom Group and the fallback
   * provider was unavailable or timed out. Distinct from an Override.
   */
  unclassified: boolean;
  /** Every red flag that fired, explaining why this reached High. */
  red_flags: RedFlag[];
  override: OverrideRecord | null;
  snapshot: AssessmentSnapshot;
  /**
   * Set by a Re-assessment: the governing Assessment this one replaced.
   * Null on the first Assessment, so the sequence is reconstructable.
   */
  supersedes_assessment_id: number | null;
}

export interface QueueEntry {
  encounter_id: number;
  arrived_at: string;
  waiting_seconds: number;
  urgency_level: UrgencyLevel;
  patient: Patient;
  intake: Intake;
  assessment: Assessment;
  override_flag: boolean;
  /** Its own state, separate from override_flag. */
  unclassified_flag: boolean;
}

export interface QueueSnapshot {
  as_of: string;
  entries: QueueEntry[];
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
 * One Patient's Encounters over time, oldest first. Corpus rows (Encounters
 * carrying an evaluation run id) are absent, so a measurement row never reads
 * as a real visit.
 */
export interface PatientHistory {
  patient: Patient;
  encounters: Encounter[];
}

export interface AdministratorQueueEntry {
  encounter_id: number;
  arrived_at: string;
  waiting_seconds: number;
  urgency_level: UrgencyLevel;
  patient_name: string;
  presenting_complaint: string;
  machine_recommendation: UrgencyLevel;
  final_decision: UrgencyLevel;
  final_decision_differs: boolean;
}

export interface AdministratorQueueSnapshot {
  as_of: string;
  entries: AdministratorQueueEntry[];
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
  departed_at: string;
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
  assessment_id: number | null;
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
  openEncounter: (patientId: number, intake: Intake) =>
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
  queue: () => request<QueueSnapshot>("/api/clinical/queue"),
  overrideReasons: () =>
    request<{ reasons: OverrideReason[] }>("/api/clinical/override-reasons"),
  overrideFinalDecision: (
    encounterId: number,
    body: {
      assessment_id: number;
      final_decision: UrgencyLevel;
      reason: OverrideReason;
      free_text: string | null;
    },
  ) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}/override`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /*
   * Departure takes no body: the departure instant is the server's, recorded
   * at the moment of the action. The Encounter then leaves the awaiting
   * Queue on the next read.
   */
  departEncounter: (encounterId: number) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}/departure`, {
      method: "POST",
    }),
  /*
   * Re-assessment captures the Encounter's current intake and appends a new
   * Assessment. It is only ever sent from an explicit Clinical action; the
   * queue reorders on the next read because it sorts on the latest Final
   * Decision.
   */
  reassessEncounter: (encounterId: number, intake: Intake) =>
    requestDetailed<Encounter>(
      `/api/clinical/encounters/${encounterId}/reassessment`,
      {
        method: "POST",
        body: JSON.stringify(intake),
      },
    ),
  administratorQueue: () =>
    request<AdministratorQueueSnapshot>("/api/administrator/queue"),
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
