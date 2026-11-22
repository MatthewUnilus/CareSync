import { cx } from "@/utils/cx";

/**
 * TriageAssist UI Kit — UrgencyBadge (Figma frame 3:364, Clinical patterns sheet)
 *
 * Rebuilt to match the real queue's urgency presentation exactly
 * (`src/queueDisplay.ts URGENCY_BADGE_CLASS`, which the product screens use):
 *   High   bg-status-rose-background    text-status-rose-text
 *   Medium bg-status-yellow-background  text-status-yellow-text
 *   Low    bg-status-lime-background    text-status-lime-text
 * (Medium is deliberately yellow, not orange — orange is the Override flag's
 * colour; see queueDisplay.ts.)
 *
 * Pending/Unavailable are not urgency levels: they sit on the neutral
 * background-tertiary/text-secondary pair BoardUI reserves for statusless
 * chips, so a missing Assessment never reads as a level.
 *
 * Glossary: these are Urgency Levels (High/Medium/Low). The word "priority"
 * belongs to the Figma file's era, not the product's.
 *
 * Accessibility contract (Figma description): non-interactive status, full
 * label exposed to assistive technology as visible text.
 */
export type TriagePriority = "high" | "medium" | "low" | "pending" | "unavailable";

const LABELS: Record<TriagePriority, string> = {
  high: "High urgency",
  medium: "Medium urgency",
  low: "Low urgency",
  pending: "Pending assessment",
  "unavailable": "Unavailable",
};

const styles: Record<TriagePriority, string> = {
  high: "bg-status-rose-background text-status-rose-text",
  medium: "bg-status-yellow-background text-status-yellow-text",
  low: "bg-status-lime-background text-status-lime-text",
  pending: "bg-background-tertiary-default text-text-secondary",
  unavailable: "bg-background-tertiary-default text-text-secondary",
};

export function TriagePriorityBadge({
  priority,
  className,
}: {
  priority: TriagePriority;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-md px-1.5 py-1",
        "text-body-medium",
        styles[priority],
        className,
      )}
    >
      {LABELS[priority]}
    </span>
  );
}

/** Full label for a priority, for use in aria-labels and body copy. */
export function triagePriorityLabel(priority: TriagePriority): string {
  return LABELS[priority];
}
