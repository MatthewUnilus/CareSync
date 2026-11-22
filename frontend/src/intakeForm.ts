import type { Intake } from "./api";

/**
 * The reason for a visit as a controlled form holds it: a string until the
 * form is submitted.
 *
 * A visit records only its reason now — vitals are charted separately — so this
 * is the whole of the intake the form carries and the whole of what
 * `buildIntake` sends.
 */
export interface IntakeFormValues {
  complaint: string;
}

/**
 * The form values as the reason-only payload a visit accepts. Matching the
 * server's `VisitReasonPayload`, which refuses any extra field with a `422`.
 */
export function buildIntake(form: IntakeFormValues): Intake {
  return { presenting_complaint: form.complaint.trim() };
}
