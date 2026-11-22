import { cx } from "@/utils/cx";
import {
  TriagePriorityBadge,
  triagePriorityLabel,
  type TriagePriority,
} from "./priority-badge";
import { TriageButton } from "./button";

/**
 * TriageAssist UI Kit — MachineRecommendationCard (Figma frame 3:512)
 *
 * Rebuilt on BoardUI vocabulary. The Figma sheet said "AI priority
 * recommendation" with "Awaiting review / Reviewed" states; the product
 * glossary (CONTEXT.md) does not say "AI", and the act of changing the level
 * is an Override, not a review. What this card now presents:
 *
 *   - The Machine Recommendation, with its Urgency Level badge.
 *   - Decision state per the queue's vocabulary: "Awaiting Override" when no
 *     Final Decision exists, "Overridden" when a human set a Final Decision
 *     (with the note naming who and why — the server's audit fields, never a
 *     fabricated default), and "Recommendation unavailable" when the engine
 *     produced nothing usable.
 *   - The Final Decision as its own line — the human-assigned urgency is
 *     never implied to be machine-set. When it differs from the
 *     recommendation, it takes the Override flag's orange, the same signal
 *     the Administrator dashboard uses for "Differs".
 *
 * Type: BoardUI composite utilities (text-title-3-medium, text-body-medium,
 * text-caption-1-*). Tone boxes ride the status token pairs, not kit hex.
 *
 * Caption: "Decision support only. Not a diagnosis."
 */
export type TriageDecisionStatus = "awaiting" | "overridden" | "unavailable";

export interface TriagePriorityResultCardProps {
  /** e.g. "Machine Recommendation". */
  title?: string;
  /** e.g. "Sofia Reyes · TA-0106". */
  patient: string;
  /** The Machine Recommendation. */
  recommendation: TriagePriority;
  /** "Why this was recommended" body — the red flags and symptom groups. */
  explanation: string;
  /** e.g. "Assessment · 09:42". */
  assessedAt?: string;
  decisionStatus: TriageDecisionStatus;
  /** e.g. "Overridden by A. Chen · 09:44 — clinical gestalt" (from the server). */
  decisionNote?: string;
  /** Final human-assigned Urgency Level line, e.g. "Final Decision: Medium". */
  finalDecision?: string;
  /** Card action: Awaiting → "Override"; Unavailable → "Complete assessment"; Overridden → "View assessment history". */
  onAction?: () => void;
  className?: string;
}

const STATUS_BOX = {
  awaiting: "bg-status-blue-background text-status-blue-text",
  overridden: "bg-status-lime-background text-status-lime-text",
  unavailable: "bg-status-yellow-background text-status-yellow-text",
} as const;

const STATUS_LABEL: Record<TriageDecisionStatus, string> = {
  awaiting: "Awaiting Override",
  overridden: "Overridden",
  unavailable: "Recommendation unavailable",
};

const ACTION_LABEL: Record<TriageDecisionStatus, string> = {
  awaiting: "Override",
  overridden: "View assessment history",
  unavailable: "Complete assessment",
};

const ACTION_VARIANT: Record<
  TriageDecisionStatus,
  "primary" | "secondary"
> = {
  awaiting: "primary",
  overridden: "secondary",
  unavailable: "primary",
};

export function TriagePriorityResultCard({
  title = "Machine Recommendation",
  patient,
  recommendation,
  explanation,
  assessedAt,
  decisionStatus,
  decisionNote,
  finalDecision,
  onAction,
  className,
}: TriagePriorityResultCardProps) {
  return (
    <section
      className={cx(
        "flex flex-col gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6",
        className,
      )}
    >
      <h3 className="text-title-3-medium text-text-primary">{title}</h3>
      <p className="text-body-medium text-text-secondary">{patient}</p>
      <TriagePriorityBadge priority={recommendation} />

      <div className="flex flex-col gap-1">
        <h4 className="text-body-medium font-semibold text-text-primary">
          Why this was recommended
        </h4>
        <p className="text-body-medium text-text-secondary">{explanation}</p>
      </div>

      {assessedAt ? (
        <p className="text-caption-1-regular text-text-secondary">{assessedAt}</p>
      ) : null}

      <div
        className={cx(
          "flex flex-col gap-1 rounded-2xl p-4",
          STATUS_BOX[decisionStatus],
        )}
      >
        <p className="text-body-medium font-semibold">
          {STATUS_LABEL[decisionStatus]}
        </p>
        {decisionNote ? (
          <p className="text-caption-1-regular">{decisionNote}</p>
        ) : null}
      </div>

      {finalDecision ? (
        <p
          className={cx(
            "text-body-medium font-medium",
            decisionStatus === "overridden"
              ? "text-status-orange-text"
              : "text-text-secondary",
          )}
        >
          {finalDecision}
        </p>
      ) : null}

      <p className="text-caption-1-regular text-text-secondary">
        Decision support only. Not a diagnosis.
      </p>

      {onAction ? (
        <TriageButton
          variant={ACTION_VARIANT[decisionStatus]}
          onClick={onAction}
          aria-label={`${ACTION_LABEL[decisionStatus]}: ${patient}. ${triagePriorityLabel(recommendation)}`}
        >
          {ACTION_LABEL[decisionStatus]}
        </TriageButton>
      ) : null}
    </section>
  );
}