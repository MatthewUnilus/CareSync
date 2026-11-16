import type { Intake, RedFlag, Sex, UrgencyLevel } from "./api";

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
 * a boarding incident legible on a board.
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

/*
 * Urgency presentation, mapped onto the BoardUI status palette:
 * High → rose (red), Medium → yellow (amber), Low → lime (green).
 * The triage band (border-l) is the at-a-glance edge on a queue card; the
 * text class sets the level name beside it. Medium is deliberately yellow,
 * not orange — orange is the Override flag's colour, and the two can appear
 * together.
 */
const URGENCY_TEXT_CLASS: Record<UrgencyLevel, string> = {
  High: "text-status-rose-text",
  Medium: "text-status-yellow-text",
  Low: "text-status-lime-text",
};

const URGENCY_BORDER_CLASS: Record<UrgencyLevel, string> = {
  High: "border-l-status-rose-text",
  Medium: "border-l-status-yellow-text",
  Low: "border-l-status-lime-text",
};

/**
 * The urgency badge: a filled chip naming the level, sized and weighted so it
 * reads at arm's length. This is the same background/text token pair the Chip
 * component uses, which is the combination already verified for contrast.
 *
 * The badge carries the word, not only the colour, so urgency survives for a
 * clinician who cannot separate the hues.
 */
const URGENCY_BADGE_CLASS: Record<UrgencyLevel, string> = {
  High: "bg-status-rose-background text-status-rose-text",
  Medium: "bg-status-yellow-background text-status-yellow-text",
  Low: "bg-status-lime-background text-status-lime-text",
};

export function urgencyTextClass(level: UrgencyLevel): string {
  return URGENCY_TEXT_CLASS[level];
}

export function urgencyBorderClass(level: UrgencyLevel): string {
  return URGENCY_BORDER_CLASS[level];
}

export function urgencyBadgeClass(level: UrgencyLevel): string {
  return URGENCY_BADGE_CLASS[level];
}

/**
 * How overdue a wait is, as a band the board can escalate on.
 *
 * These are *presentation* thresholds for drawing attention, not clinical
 * decision rules: nothing here re-triages, reorders, or changes any stored
 * Urgency Level. The Queue remains ordered by Final Decision then arrival time
 * (`app/queue.py`), and the spec puts time-based escalation of the *decision*
 * out of scope. What the board owes a clinician is a visible signal that a wait
 * has grown unreasonable, which is a display concern only.
 *
 * Bands are deliberately generous so an ordinary day does not scream: under
 * four hours is routine; four hours is a long wait; twelve hours is a breach; a
 * day or more is a boarding incident and is the loudest state.
 */
export type WaitBand = "routine" | "long" | "breach" | "critical";

const HOUR = 3600;
const LONG_WAIT_SECONDS = 4 * HOUR;
const BREACH_WAIT_SECONDS = 12 * HOUR;
const CRITICAL_WAIT_SECONDS = 24 * HOUR;

export function waitBand(seconds: number): WaitBand {
  if (seconds >= CRITICAL_WAIT_SECONDS) {
    return "critical";
  }
  if (seconds >= BREACH_WAIT_SECONDS) {
    return "breach";
  }
  if (seconds >= LONG_WAIT_SECONDS) {
    return "long";
  }
  return "routine";
}

/**
 * The waiting figure, escalating in size and weight as well as colour.
 *
 * Size and weight carry the signal too, so the escalation is still legible to a
 * clinician who cannot separate red from green. The waiting time is the largest
 * element on the card past the routine band: it is the fact that changes while
 * nobody is looking, and the one a board exists to surface.
 */
export function waitTextClass(band: WaitBand): string {
  switch (band) {
    case "critical":
      return "text-title-2-semibold text-status-rose-text";
    case "breach":
      return "text-title-3-semibold text-status-rose-text";
    case "long":
      return "text-title-3-semibold text-status-yellow-text";
    default:
      return "text-title-3-medium text-text-primary";
  }
}

/** The sentence beside an escalated wait, or null when it is routine. */
export function waitBandLabel(band: WaitBand, seconds: number): string | null {
  switch (band) {
    case "critical":
      return `boarding ${Math.floor(seconds / 86400)}d — escalate`;
    case "breach":
      return "over 12h waiting";
    case "long":
      return "over 4h waiting";
    default:
      return null;
  }
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
 * The queue shows elapsed time for scanning, but a bare elapsed figure cannot
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

/*
 * Abnormal-vital marking is driven by the server's fired red flags, not by a
 * second copy of the thresholds in the client: each flag names the intake
 * fields it keyed on (`red_flags.py` → `RedFlag.vitals`). So the values the
 * card highlights are exactly the ones the recommendation was made from, and a
 * threshold can never drift between the engine and the screen.
 */
export function abnormalVitalFields(redFlags: RedFlag[]): Set<string> {
  const marked = new Set<string>();
  for (const flag of redFlags) {
    for (const vital of flag.vitals) {
      marked.add(vital);
    }
  }
  return marked;
}

/** True when the given intake field is one a red flag keyed on. */
export function isVitalAbnormal(
  redFlags: RedFlag[],
  field: keyof Intake,
): boolean {
  return redFlags.some((flag) => flag.vitals.includes(field));
}
