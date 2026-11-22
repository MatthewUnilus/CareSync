import { cx } from "@/utils/cx";
import { TriagePriorityBadge, triagePriorityLabel, type TriagePriority } from "./priority-badge";
import { TriageButton } from "./button";

/**
 * TriageAssist UI Kit — PatientCardCompact (Figma frame 3:652)
 *
 * Rebuilt on BoardUI vocabulary. Two design decisions from the critique carry
 * through here:
 *
 * 1. The Figma sheet hardcoded the waiting card's badge to High. A waiting
 *    status is not a clinical urgency; the card now takes the governing
 *    urgency from the caller (`urgency` prop), defaulting to "pending" when
 *    no Assessment exists yet.
 * 2. Copy follows the product glossary: Machine Recommendation (never "AI"),
 *    Urgency Level, the Queue. The high-urgency status line rides the
 *    rose-text token — the same pair the queue's badge pair uses for High —
 *    so emphasis no longer depends on kit-local hex.
 */
export interface TriagePatientCardCompactProps {
  /** e.g. "Alex Morgan · TA-0107". */
  name: string;
  /** e.g. "Position 07 · Waiting 12 min" (waiting) — omit for local drafts. */
  queue?: string;
  /** The Machine Recommendation, or its absence ("Pending assessment"). */
  urgency: TriagePriority;
  /** Status line, e.g. "Machine recommendation: High" or "Assessment not yet requested". */
  aiStatus: string;
  /** Card action. */
  actionLabel: string;
  onAction: () => void;
  className?: string;
}

export function TriagePatientCardCompact({
  name,
  queue,
  urgency,
  aiStatus,
  actionLabel,
  onAction,
  className,
}: TriagePatientCardCompactProps) {
  return (
    <article
      className={cx(
        "flex flex-col gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6",
        "min-w-70",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-title-3-medium text-text-primary">{name}</h3>
        <TriagePriorityBadge priority={urgency} />
      </div>

      {queue ? (
        <p className="text-body-medium text-text-secondary">{queue}</p>
      ) : (
        <p className="text-body-medium text-text-secondary">
          Saved on this device · Not in live queue
        </p>
      )}

      <p className={cx("text-body-medium", urgency === "high" && "text-status-rose-text")}>
        {aiStatus}
      </p>

      <TriageButton
        variant="primary"
        onClick={onAction}
        aria-label={`${actionLabel}: ${name}. ${triagePriorityLabel(urgency)}`}
        className="w-full"
      >
        {actionLabel}
      </TriageButton>
    </article>
  );
}