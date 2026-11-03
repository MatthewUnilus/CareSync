import type { Intake } from "./api";

/**
 * The intake fields as a controlled form holds them: every value is a string
 * until the form is submitted. Shared by intake capture and Re-assessment, so
 * both send exactly the same shape and the same numeric conversions.
 */
export interface IntakeFormValues {
  complaint: string;
  painLevel: string;
  durationHours: string;
  temperatureC: string;
  heartRate: string;
  systolic: string;
  diastolic: string;
  oxygenSaturation: string;
  notes: string;
}

export function intakeFormValues(intake: Intake): IntakeFormValues {
  return {
    complaint: intake.presenting_complaint,
    painLevel: String(intake.pain_level),
    durationHours: String(intake.illness_duration_hours),
    temperatureC: String(intake.temperature_c),
    heartRate: String(intake.heart_rate_bpm),
    systolic: String(intake.blood_pressure.systolic),
    diastolic: String(intake.blood_pressure.diastolic),
    oxygenSaturation: String(intake.oxygen_saturation_percent),
    notes: intake.notes ?? "",
  };
}

export function buildIntake(form: IntakeFormValues): Intake {
  return {
    presenting_complaint: form.complaint.trim(),
    pain_level: Number(form.painLevel),
    illness_duration_hours: Number(form.durationHours),
    temperature_c: Number(form.temperatureC),
    heart_rate_bpm: Number(form.heartRate),
    blood_pressure: {
      systolic: Number(form.systolic),
      diastolic: Number(form.diastolic),
    },
    oxygen_saturation_percent: Number(form.oxygenSaturation),
    notes: form.notes.trim() ? form.notes.trim() : null,
  };
}
