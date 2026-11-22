import type { ReactNode } from "react";
import { cx } from "@/utils/cx";
import { Chip } from "@/components/base/badges/chip";
import { triagePriorityLabel, type TriagePriority } from "./priority-badge";

/**
 * TriageAssist UI Kit — PatientListItem (Figma frame 3:419)
 *
 * Rebuilt on BoardUI vocabulary:
 *   - Urgency badge is the shared Chip component (caption variant, status pairs)
 *     so it is pixel-identical to the queue and Administrator table badges.
 *   - Whole-row 48px minimum action area preserved from the Figma contract.
 *   - Glossary: "Machine Recommendation" / "Urgency Level" — no "AI" or "priority".
 *   - Border on High urgency uses the same left-border accent the queue uses
 *     (`border-l-status-rose-text`), so the signal reads consistently across
 *     the kit and the product screens.
 */
export interface TriagePatientListItemProps {
  /** e.g. "01 · Maya Patel" — queue position and patient name. */
  name: string;
  /** e.g. "TA-0104 · 46 years". */
  meta: string;
  /** Machine Recommendation (Urgency Level). */
  priority: TriagePriority;
  /** Presenting symptom, e.g. "Chest pain, shortness of breath". */
  symptom: string;
  /** e.g. "Waiting 04 min". */
  waiting: string;
  /** Machine Recommendation line, e.g. "Machine recommendation: High". */
  reviewStatus?: ReactNode;
  /** Row action. When set, the whole row becomes a 48px-min interactive element. */
  onSelect?: () => void;
  className?: string;
}

export function TriagePatientListItem({
  name,
  meta,
  priority,
  symptom,
  waiting,
  reviewStatus,
  onSelect,
  className,
}: TriagePatientListItemProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-title-3-medium text-text-primary">{name}</span>
          <span className="text-caption-1-medium text-text-secondary">{meta}</span>
        </div>
        <Chip variant="caption" color={
          priority === "high" ? "rose"
          : priority === "medium" ? "yellow"
          : priority === "low" ? "lime"
          : "neutral"
        }>
          {priority === "pending" ? "Pending"
          : priority === "unavailable" ? "Unavailable"
          : priority.charAt(0).toUpperCase() + priority.slice(1)}
        </Chip>
      </div>
      <p className="text-body-medium text-text-secondary">{symptom}</p>
      <div className="flex items-center justify-between gap-3">
        <span className="text-body-medium text-text-secondary">{waiting}</span>
        {reviewStatus ? (
          <span className="text-caption-1-medium text-text-secondary">
            {reviewStatus}
          </span>
        ) : null}
      </div>
    </>
  );

  const container = cx(
    "flex w-full flex-col gap-3 rounded-3xl border bg-background-primary-default p-6",
    priority === "high" ? "border-l-4 border-l-status-rose-text" : "border-border-button-default",
    onSelect && "min-h-12 cursor-pointer text-start",
    className,
  );

  if (onSelect) {
    return (
      <button
        type="button"
        onClick={onSelect}
        aria-label={`${name}. ${triagePriorityLabel(priority)}${
          reviewStatus ? `. ${typeof reviewStatus === "string" ? reviewStatus : ""}` : ""
        }`}
        className={container}
      >
        {body}
      </button>
    );
  }

  return (
    <div className={container}>
      {body}
    </div>
  );
}