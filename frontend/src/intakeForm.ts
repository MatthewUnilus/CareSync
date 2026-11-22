import type { Intake, ObservationPayload, VisitReasonIntake } from "./api";

/**
 * The intake fields as a controlled form holds them: every value is a string
 * until the form is submitted.
 *
 * Shared by the intake screen and the Observation chart, so charting the first
 * set of vitals on a visit and charting a later set on the ward send exactly the
 * same shape and the same numeric conversions.
 */
export interface IntakeFormValues {
  complaint: string;
  painLevel: string;
  durationHours: string;
  temperatureC: string;
  heartRate: string;
  respiratoryRate: string;
  systolic: string;
  diastolic: string;
  oxygenSaturation: string;
  notes: string;
}

/**
 * Per-field validation messages for a set of vitals. Each key names the field it
 * belongs beside, so one error can never stand in for another.
 */
export interface ObservationFieldErrors {
  painLevel?: string;
  durationHours?: string;
  temperatureC?: string;
  heartRate?: string;
  respiratoryRate?: string;
  systolic?: string;
  diastolic?: string;
  oxygenSaturation?: string;
  notes?: string;
}

/** Every field blank, for a fresh form. */
export function emptyIntakeFormValues(): IntakeFormValues {
  return {
    complaint: "",
    painLevel: "",
    durationHours: "",
    temperatureC: "",
    heartRate: "",
    respiratoryRate: "",
    systolic: "",
    diastolic: "",
    oxygenSaturation: "",
    notes: "",
  };
}

/**
 * The eight readings and the notes as the chart's write routes accept them.
 *
 * A blank note is sent as `null`, so an unremarked set and one with an empty
 * note are stored identically.
 */
export function buildObservationPayload(
  form: IntakeFormValues,
): ObservationPayload {
  return {
    pain_level: Number(form.painLevel),
    illness_duration_hours: Number(form.durationHours),
    temperature_c: Number(form.temperatureC),
    heart_rate_bpm: Number(form.heartRate),
    respiratory_rate_bpm: Number(form.respiratoryRate),
    blood_pressure: {
      systolic: Number(form.systolic),
      diastolic: Number(form.diastolic),
    },
    oxygen_saturation_percent: Number(form.oxygenSaturation),
    notes: form.notes.trim() ? form.notes.trim() : null,
  };
}

/**
 * The form values as the payload a visit accepts: the reason together with the
 * first set of vitals, so opening a visit charts its first Observation.
 *
 * Matching the server's `IntakePayload`; the server also accepts the reason
 * alone, but this form always sends the full shape.
 */
export function buildIntake(form: IntakeFormValues): Intake {
  return {
    presenting_complaint: form.complaint.trim(),
    ...buildObservationPayload(form),
  };
}

/**
 * The reason for a visit alone, as the payload a visit accepts before any vitals
 * are measured. A visit may be opened this way, then have its first Observation
 * charted later once the readings are taken.
 */
export function buildReasonOnlyIntake(form: IntakeFormValues): VisitReasonIntake {
  return { presenting_complaint: form.complaint.trim() };
}

/**
 * The readings' numeric bounds, mirrored from the server's `ObservationPayload`.
 * These are the intake bounds the server enforces, repeated here only so the
 * form can name the problem beside the field instead of leaving it to a `422`.
 */
const READING_BOUNDS: {
  key: keyof ObservationFieldErrors;
  label: string;
  min: number;
  max: number;
}[] = [
  { key: "painLevel", label: "Pain level", min: 1, max: 10 },
  { key: "durationHours", label: "Illness duration", min: 0, max: 8760 },
  { key: "temperatureC", label: "Temperature", min: 30, max: 45 },
  { key: "heartRate", label: "Heart rate", min: 20, max: 300 },
  { key: "respiratoryRate", label: "Respiratory rate", min: 0, max: 80 },
  { key: "systolic", label: "Systolic pressure", min: 50, max: 300 },
  { key: "diastolic", label: "Diastolic pressure", min: 20, max: 200 },
  { key: "oxygenSaturation", label: "Oxygen saturation", min: 50, max: 100 },
];

/**
 * The most characters a note may carry, matching the server's stored column.
 */
export const NOTES_MAX_LENGTH = 2000;

/**
 * Validate a set of vitals before it is sent. Every reading is required and
 * within its bounds, systolic must exceed diastolic, and an optional note must
 * stay within its length.
 *
 * The server is the authority — this only spares the reader a round trip; a
 * value that slips through is still refused by the server's own bounds.
 */
export function validateObservationForm(
  form: IntakeFormValues,
): ObservationFieldErrors {
  const errors: ObservationFieldErrors = {};

  for (const { key, label, min, max } of READING_BOUNDS) {
    const raw = form[key].trim();
    if (raw === "") {
      errors[key] = `${label} is required`;
      continue;
    }
    const value = Number(raw);
    if (!Number.isFinite(value) || value < min || value > max) {
      errors[key] = `Enter between ${min} and ${max}`;
    }
  }

  const systolic = Number(form.systolic);
  const diastolic = Number(form.diastolic);
  if (
    !errors.systolic &&
    !errors.diastolic &&
    Number.isFinite(systolic) &&
    Number.isFinite(diastolic) &&
    systolic <= diastolic
  ) {
    errors.systolic = "Systolic must be greater than diastolic";
  }

  if (form.notes.trim().length > NOTES_MAX_LENGTH) {
    errors.notes = `Keep notes within ${NOTES_MAX_LENGTH} characters`;
  }

  return errors;
}
