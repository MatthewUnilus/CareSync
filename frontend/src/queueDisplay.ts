import type { UrgencyLevel } from "./api";

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

export function urgencyTextClass(level: UrgencyLevel): string {
  return URGENCY_TEXT_CLASS[level];
}

export function urgencyBorderClass(level: UrgencyLevel): string {
  return URGENCY_BORDER_CLASS[level];
}

export function formatArrival(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
