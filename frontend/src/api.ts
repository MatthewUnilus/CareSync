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
  hospital_number: string | null;
  age: number;
  sex: Sex;
  contact_phone: string;
  contact_email: string | null;
  registered_at: string;
}

export interface NewPatient {
  full_name: string;
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

export interface ObservationReading {
  pain_level: number;
  illness_duration_hours: number;
  temperature_c: number;
  heart_rate_bpm: number;
  respiratory_rate_bpm: number;
  blood_pressure: BloodPressure;
  oxygen_saturation_percent: number;
}

export interface ObservationPayload extends ObservationReading {
  notes: string | null;
}

export interface Intake extends ObservationPayload {
  presenting_complaint: string;
}

export interface VisitReasonIntake {
  presenting_complaint: string;
}

export interface PreviousObservation extends ObservationPayload {
  taken_at: string;
}

export interface Observation extends ObservationPayload {
  id: number;
  encounter_id: number | null;
  admission_id: number | null;
  taken_at: string;
  actor: { id: number; display_name: string };
  reference_range_applies: boolean;
  abnormal_fields: string[];
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

export interface PatientSearchResults {
  patients: Patient[];
}

export interface PatientHistory {
  patient: Patient;
  encounters: Encounter[];
}

export interface WardAdmission {
  id: number;
  patient: Patient;
  ward: string;
  bed: string;
  admitted_at: string;
  discharged_at: string | null;
  encounter_id: number | null;
  status: "open" | "discharged";
}

export interface BoardAdmission extends WardAdmission {
  latest_observation: Observation | null;
  outstanding_medication_count: number;
  overdue_medication_count: number;
  due_medication_count: number;
  open_task_count: number;
  unreviewed_result_count: number;
}

export interface WardBoard {
  admissions: BoardAdmission[];
}

export interface TaskPerson {
  id: number;
  display_name: string;
}

export interface WardStaff {
  users: TaskPerson[];
}

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
  note_id: number | null;
}

export interface WardTasks {
  tasks: Task[];
}

export interface NewTaskPayload {
  description: string;
  due_at: string | null;
  assignee_user_id: number | null;
}

export type InvestigationState =
  | "requested"
  | "sample_taken"
  | "result_available"
  | "reviewed";

export interface Investigation {
  id: number;
  admission_id: number;
  patient: Patient;
  test_name: string;
  requested_at: string;
  requested_by: { id: number; display_name: string };
  state: InvestigationState;
  sample_taken_at: string | null;
  result_available_at: string | null;
  result_note: string | null;
  reviewed_at: string | null;
  reviewed_by: { id: number; display_name: string } | null;
  instructed_by: string | null;
}

export interface Investigations {
  investigations: Investigation[];
}

export interface NewInvestigationPayload {
  test_name: string;
  instructed_by: string | null;
}

export interface MedicationRoundTime {
  key: string;
  label: string;
  times: string[];
}

export interface MedicationRoundTimes {
  frequencies: MedicationRoundTime[];
}

export interface MedicationOrder {
  id: number;
  admission_id: number;
  drug: string;
  dose: string;
  route: string;
  frequency: string;
  start_at: string;
  instructed_by: string;
  status: "active" | "stopped";
  stopped_at: string | null;
}

export interface MedicationOrders {
  orders: MedicationOrder[];
}

export interface MedicationOrderPayload {
  drug: string;
  dose: string;
  route: string;
  frequency: string;
  start_at: string;
  instructed_by: string;
}

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

export interface MedicationDueList {
  doses: MedicationDueDose[];
}

export interface MedicationAdministrationReason {
  key: string;
  label: string;
  requires_text: boolean;
}

export interface MedicationAdministrationReasons {
  reasons: MedicationAdministrationReason[];
}

export type MedicationAdministrationOutcome =
  | "given"
  | "withheld"
  | "refused"
  | "unavailable";

export interface MedicationAdministrationReasonRef {
  key: string;
  label: string;
  text: string | null;
}

export interface MedicationAdministration {
  id: number;
  order_id: number;
  admission_id: number;
  drug: string;
  dose: string;
  route: string;
  due_at: string;
  outcome: MedicationAdministrationOutcome;
  reason: MedicationAdministrationReasonRef | null;
  recorded_at: string;
  actor: { id: number; display_name: string };
  late: boolean;
}

export interface MedicationAdministrationPayload {
  due_at: string;
  outcome: MedicationAdministrationOutcome;
  reason_key: string | null;
  reason_text: string | null;
}

export interface MedicationAdministrationGridSlot {
  due_at: string;
  state: string;
  administration: MedicationAdministration | null;
}

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

export interface MedicationAdministrationGrid {
  order: MedicationAdministrationGridOrder;
  slots: MedicationAdministrationGridSlot[];
}

export interface MedicationAdministrationHistorySlot {
  order_id: number;
  drug: string;
  dose: string;
  route: string;
  due_at: string;
  state: string;
  administration: MedicationAdministration | null;
}

export interface MedicationAdministrationHistory {
  slots: MedicationAdministrationHistorySlot[];
}

export interface NoteTemplateField {
  key: string;
  label: string;
}

export interface NoteTemplate {
  key: string;
  label: string;
  fields: NoteTemplateField[];
}

export interface NoteTemplates {
  templates: NoteTemplate[];
}

export interface NotePrefill {
  fields: Record<string, string>;
  source_observation: {
    taken_at: string;
    actor: { id: number; display_name: string };
  } | null;
}

export interface NursingNoteField {
  key: string;
  value: string;
}

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

export interface NursingNotes {
  notes: NursingNote[];
}

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
  action: string;
  action_label: string;
  detail: string | null;
  recorded_at: string;
  actor: {
    id: number;
    display_name: string;
  };
  patient_id: number | null;
  encounter_id: number | null;
  admission_id: number | null;
}

export interface AuditLog {
  entries: AuditEntry[];
}

export interface WardCensusReport {
  total_patients: number;
  by_ward: Record<string, number>;
  by_bed: Record<string, number>;
}

export interface LengthOfStayDistributionItem {
  admission_id: number;
  patient: string;
  ward: string;
  bed: string;
  seconds: number;
  days: number;
}

export interface LengthOfStayReport {
  average_seconds: number;
  distribution: LengthOfStayDistributionItem[];
}

export interface MedicationTimelinessReport {
  on_time: number;
  late: number;
  not_given: number;
  total: number;
  on_time_pct: number;
}

export interface InvestigationReviewReport {
  awaiting_review_count: number;
  oldest_wait_seconds: number | null;
}

export interface TaskCompletionReport {
  raised: number;
  completed: number;
  completion_pct: number;
}

export interface StudyTaskRunCreateRequest {
  task_label: string;
  participant_id: string;
}

export interface StudyTaskRunEndRequest {
  participant_id: string;
}

export interface StudyTaskRunAbandonRequest {
  participant_id: string;
}

export interface StudyTaskRunResponse {
  id: number;
  task_label: string;
  participant_id: string;
  started_at: string;
  ended_at: string | null;
  status: string;
}

export interface StudyTaskRunListResponse {
  runs: StudyTaskRunResponse[];
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

export const SESSION_LOCKED_EVENT = "caresync:session-locked";

export function errorText(caught: unknown): string {
  return caught instanceof ApiError
    ? caught.message
    : "Unable to reach the server.";
}

async function requestDetailed<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
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
  searchPatients: (query: string, limit = 20) =>
    request<PatientSearchResults>(
      `/api/clinical/patients?q=${encodeURIComponent(query)}&limit=${limit}`,
    ),
  patientHistory: (patientId: number) =>
    request<PatientHistory>(`/api/clinical/patients/${patientId}/encounters`),
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
  patientObservations: (patientId: number) =>
    request<{ observations: Observation[] }>(
      `/api/clinical/patients/${patientId}/observations`,
    ),
  attachHospitalNumber: (patientId: number, hospitalNumber: string) =>
    request<Patient>(`/api/clinical/patients/${patientId}/hospital-number`, {
      method: "POST",
      body: JSON.stringify({ hospital_number: hospitalNumber }),
    }),
  endEncounter: (encounterId: number) =>
    request<Encounter>(`/api/clinical/encounters/${encounterId}/end`, {
      method: "POST",
    }),
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
  medicationDue: (from: string, to: string) =>
    request<MedicationDueList>(
      `/api/ward/medications/due?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
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
  medicationAdministrationGrid: (orderId: number, from: string, to: string) =>
    request<MedicationAdministrationGrid>(
      `/api/ward/medication-orders/${orderId}/administration-grid?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
  admissionMedicationAdministrations: (
    admissionId: number,
    from: string,
    to: string,
  ) =>
    request<MedicationAdministrationHistory>(
      `/api/ward/admissions/${admissionId}/medication-administrations?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),
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
  admissionInvestigations: (admissionId: number) =>
    request<Investigations>(
      `/api/ward/admissions/${admissionId}/investigations`,
    ),
  recordInvestigation: (
    admissionId: number,
    payload: NewInvestigationPayload,
  ) =>
    request<Investigation>(
      `/api/ward/admissions/${admissionId}/investigations`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  markInvestigationSampleTaken: (investigationId: number) =>
    request<Investigation>(
      `/api/ward/investigations/${investigationId}/sample-taken`,
      { method: "POST" },
    ),
  recordInvestigationResult: (investigationId: number, resultNote: string) =>
    request<Investigation>(
      `/api/ward/investigations/${investigationId}/result`,
      { method: "POST", body: JSON.stringify({ result_note: resultNote }) },
    ),
  reviewInvestigation: (investigationId: number) =>
    request<Investigation>(`/api/ward/investigations/${investigationId}/review`, {
      method: "POST",
    }),
  investigationsAwaitingReview: () =>
    request<Investigations>("/api/ward/investigations/awaiting-review"),
  investigationsAwaitingResult: () =>
    request<Investigations>("/api/ward/investigations/awaiting-result"),
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
  dailyVisitsReport: () =>
    request<DailyVisitsReport>("/api/administrator/reports/daily-visits"),
  performanceReport: () =>
    request<PerformanceReport>("/api/administrator/reports/performance"),
  wardCensusReport: () =>
    request<WardCensusReport>("/api/administrator/reports/ward-census"),
  lengthOfStayReport: () =>
    request<LengthOfStayReport>("/api/administrator/reports/length-of-stay"),
  medicationTimelinessReport: (days = 7) =>
    request<MedicationTimelinessReport>(
      `/api/administrator/reports/medication-timeliness?days=${days}`,
    ),
  investigationReviewReport: () =>
    request<InvestigationReviewReport>(
      "/api/administrator/reports/investigation-review",
    ),
  taskCompletionReport: (days = 7) =>
    request<TaskCompletionReport>(
      `/api/administrator/reports/task-completion?days=${days}`,
    ),
  auditLog: (encounterId?: number) =>
    request<AuditLog>(
      `/api/administrator/audit-log${encounterId ? `?encounter_id=${encounterId}` : ""}`,
    ),

  // Study Instrumentation (ticket 40)
  startStudyTaskRun: (payload: StudyTaskRunCreateRequest) =>
    request<StudyTaskRunResponse>("/api/clinical/study-task-runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  endStudyTaskRun: (runId: number, payload: StudyTaskRunEndRequest) =>
    request<StudyTaskRunResponse>(`/api/clinical/study-task-runs/${runId}/end`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  abandonStudyTaskRun: (runId: number, payload: StudyTaskRunAbandonRequest) =>
    request<StudyTaskRunResponse>(`/api/clinical/study-task-runs/${runId}/abandon`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  listStudyTaskRuns: () =>
    request<StudyTaskRunListResponse>("/api/clinical/study-task-runs"),
};