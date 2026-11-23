import type { Sex } from "./api";

/**
 * The Sex labels, in the order a form offers them.
 *
 * One definition so the intake select and any read-only view of a Patient's
 * sex cannot disagree about what a stored value is called.
 */
export const SEX_OPTIONS: { value: Sex; label: string }[] = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "unspecified", label: "Unspecified" },
];

/** A stored Sex value as it is shown to a reader. */
export function sexLabel(sex: Sex): string {
  return SEX_OPTIONS.find((option) => option.value === sex)?.label ?? sex;
}

/** An instant as a reader's local date and time. */
export function formatInstant(value: string): string {
  return new Date(value).toLocaleString();
}

export function formatWaiting(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ${seconds % 60}s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

/**
 * A waiting time as a clinician reads it, not as a stopwatch counts it.
 *
 * `147h 19m` is six days, but nothing in that string says so at a glance. Past
 * a day the figure is expressed in days and hours, which is the unit that makes
 * a long visit legible at a glance.
 */
export function formatWaitingLong(seconds: number): string {
  const totalMinutes = Math.floor(seconds / 60);
  if (totalMinutes < 60) {
    return formatWaiting(seconds);
  }
  const hours = Math.floor(totalMinutes / 60);
  if (hours < 24) {
    return `${hours}h ${totalMinutes % 60}m`;
  }
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours === 0 ? `${days}d` : `${days}d ${remHours}h`;
}

export function formatArrival(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The instant a patient arrived, as an absolute date and time.
 *
 * A list shows elapsed time for scanning, but a bare elapsed figure cannot
 * be checked against a clock or a handover note. The expanded card shows the
 * arrival instant so the arithmetic is never the reader's problem.
 */
export function formatArrivalFull(value: string): string {
  return new Date(value).toLocaleString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A count with its noun, so "1 dose" never reads as "1 doses". */
export function plural(count: number, singular: string, pluralForm: string): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}
