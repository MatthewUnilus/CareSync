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

export interface DailyQueueReport {
  day: string;
  starts_at: string;
  ends_at: string;
  volume: number;
  throughput: number;
  awaiting: number;
}

export interface UrgencyLevelCount {
  urgency_level: UrgencyLevel;
  encounters: number;
}

export interface UrgencyDistributionReport {
  total: number;
  levels: UrgencyLevelCount[];
}

export interface PerformanceEntry {
  encounter_id: number;
  arrived_at: string;
  assessed_at: string;
  departed_at: string;
  waiting_seconds: number;
  processing_seconds: number;
}

export interface PerformanceReport {
  completed: number;
  average_waiting_seconds: number;
  average_processing_seconds: number;
  entries: PerformanceEntry[];
}

export type AccuracyFallbackMode = "fallback-disabled" | "fallback-enabled";

/**
 * Where the run's matrix came from: a live per-case manifest, a stored
 * evaluation run, or the offline artefact.
 */
export type AccuracyRunSource = "assessments" | "evaluation" | "harness";

export interface AccuracyMajorityBaseline {
  majority_class: UrgencyLevel;
  accuracy: number;
  /** Negative when the model is worse than always predicting the commonest label. */
  model_minus_baseline: number;
  beats_baseline: boolean;
}

export interface AccuracyGroundTruthSource {
  name: string;
  version: string;
  citation: string;
  document: string | null;
}

export interface AccuracyConfusionCell {
  machine_recommendation: UrgencyLevel;
  ground_truth: UrgencyLevel;
  assessments: number;
}

export interface AccuracyLevelMetrics {
  urgency_level: UrgencyLevel;
  ground_truth_count: number;
  predicted_count: number;
  correct: number;
  /** Null when the engine never predicted this level. */
  precision: number | null;
  /** Null when no case had this ground truth. */
  recall: number | null;
}

export interface AccuracyPriorityErrorRate {
  count: number;
  denominator: number;
  rate: number | null;
}

export interface AccuracyLevelRecall {
  count: number;
  denominator: number;
  rate: number | null;
}

/** A secondary scoring of a run: explicitly not a Machine Recommendation. */
export interface AccuracyRunVariant {
  description: string;
  total: number;
  correct: number;
  accuracy: number;
  macro_f1: number;
  false_high_priority: AccuracyPriorityErrorRate;
  false_low_priority: AccuracyPriorityErrorRate;
  high_class_recall: AccuracyLevelRecall;
}

export interface AccuracyRunSample {
  labelled_cases: number;
  resolved_assessments: number;
  missing_assessments: number[];
  inconsistent_recommendations: number[];
}

export interface AccuracyFallbackCoverage {
  enabled: boolean;
  fallback_used: number;
  unclassified: number;
  /** Null for a fallback-disabled run: coverage is not exercised. */
  coverage: number | null;
  unclassified_rate: number | null;
}

export interface AccuracyRun {
  run_id: string;
  /** The producer's own mode: cross_validated, pipeline or assessment. */
  run_mode: string;
  source: AccuracyRunSource;
  /** The first available run is primary; for a harness artefact it is cross-validated. */
  primary: boolean;
  mode: AccuracyFallbackMode;
  dataset: string | null;
  engine_artefact: string | null;
  ground_truth: AccuracyGroundTruthSource;
  sample: AccuracyRunSample;
  confusion_matrix: AccuracyConfusionCell[];
  levels: AccuracyLevelMetrics[];
  total: number;
  correct: number;
  accuracy: number | null;
  macro_f1: number | null;
  majority_baseline: AccuracyMajorityBaseline | null;
  false_high_priority: AccuracyPriorityErrorRate;
  false_low_priority: AccuracyPriorityErrorRate;
  high_class_recall: AccuracyLevelRecall;
  fallback: AccuracyFallbackCoverage;
  classifier_only: AccuracyRunVariant | null;
}

export interface AccuracyOverrideReasonCount {
  reason: OverrideReason;
  overrides: number;
  share: number | null;
}

export interface AccuracyOverrideMetrics {
  assessments: number;
  overridden_assessments: number;
  overrides: number;
  rate: number | null;
  reasons: AccuracyOverrideReasonCount[];
}

export interface AccuracyEvaluationReport {
  available: boolean;
  /** Why no accuracy figure can be shown. Null when a run is available. */
  empty_reason: string | null;
  runs: AccuracyRun[];
  overrides: AccuracyOverrideMetrics;
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
   * server's UTC day; the other two are whole-record views.
   */
  dailyQueueReport: () =>
    request<DailyQueueReport>("/api/administrator/reports/daily-queue"),
  priorityDistributionReport: () =>
    request<UrgencyDistributionReport>(
      "/api/administrator/reports/priority-distribution",
    ),
  performanceReport: () =>
    request<PerformanceReport>("/api/administrator/reports/performance"),
  /*
   * The flagship report. Its accuracy figures come from stored immutable
   * Assessments joined to a labelled evaluation run; when no such run exists
   * the response says so explicitly instead of returning a zero score.
   */
  accuracyEvaluationReport: () =>
    request<AccuracyEvaluationReport>(
      "/api/administrator/reports/accuracy-evaluation",
    ),
};
