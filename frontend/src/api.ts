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
  assessment: Assessment | null;
}

export interface AssessmentSnapshot {
  presenting_complaint: string;
  age: number;
  pain_level: number;
  illness_duration_hours: number;
  temperature_c: number;
  heart_rate_bpm: number;
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

export interface Assessment {
  id: number;
  assessed_at: string;
  machine_recommendation: UrgencyLevel;
  final_decision: UrgencyLevel;
  recognised_symptom_groups: string[];
  override: OverrideRecord | null;
  snapshot: AssessmentSnapshot;
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
}

export interface QueueSnapshot {
  as_of: string;
  entries: QueueEntry[];
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
  correctIntake: (encounterId: number, intake: Intake) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}/intake`, {
      method: "PUT",
      body: JSON.stringify(intake),
    }),
  getEncounter: (encounterId: number) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}`),
  recentEncounters: (limit = 10) =>
    request<{ encounters: Encounter[] }>(
      `/api/clinical/encounters?limit=${limit}`,
    ),
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
  administratorQueue: () =>
    request<AdministratorQueueSnapshot>("/api/administrator/queue"),
};
