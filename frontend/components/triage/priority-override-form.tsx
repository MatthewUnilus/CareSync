import { useState, type FormEvent } from "react";
import { cx } from "@/utils/cx";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { Button } from "@/components/base/buttons/button";
import {
  TriagePriorityBadge,
  triagePriorityLabel,
  type TriagePriority,
} from "./priority-badge";

/**
 * TriageAssist UI Kit — PriorityOverrideForm (Figma frame 3:564)
 *
 * Rebuilt on the real app's override flow (QueueBoard.tsx OverrideAction) and
 * BoardUI vocabulary. What the critique flagged and what changed:
 *
 * 1. No fabricated "Assigned by A. Chen · 09:48". The server owns the audit
 *    trail (the queue reads `entry.assessment.override.performed_by`); the
 *    form only sends { final_decision, reason, free_text }.
 * 2. The fixed Override Reason set comes from the backend's single source of
 *    truth (`override_reasons.py`) — the same values the API exposes. Free
 *    text appears only for "other", matching the server-side rule.
 * 3. Glossary: Machine Recommendation (never "AI"), Urgency Level / Final
 *    Decision, Override (the act), Override Reason (the fixed set).
 * 4. BoardUI primitives: Select for the Final Decision and Reason, Textarea
 *    for free text, Button for actions — the same components the product
 *    screen composes, so the kit form and the queue form agree.
 * 5. The unchanged guard mirrors the queue: confirm stays disabled while the
 *    Final Decision equals the Machine Recommendation.
 */
export type OverrideReasonValue =
  | "vitals inconsistent with recommendation"
  | "symptom not captured"
  | "clinical gestalt"
  | "patient deteriorating"
  | "duplicate entry"
  | "other";

const OVERRIDE_REASONS: OverrideReasonValue[] = [
  "vitals inconsistent with recommendation",
  "symptom not captured",
  "clinical gestalt",
  "patient deteriorating",
  "duplicate entry",
  "other",
];

const URGENCY_LEVELS: TriagePriority[] = ["high", "medium", "low"];

export interface TriagePriorityOverrideFormProps {
  /** e.g. "Sofia Reyes · TA-0106". */
  patient: string;
  /** The Machine Recommendation ("high" | "medium" | "low" | "pending" | "unavailable"). */
  recommendation: TriagePriority;
  /** The urgency currently in the queue before this Override (the Final Decision). */
  currentPriority: TriagePriority;
  /** Called with the Final Decision and reason once the server confirms. */
  onConfirm?: (payload: {
    finalDecision: TriagePriority;
    reason: OverrideReasonValue;
    freeText: string | null;
  }) => Promise<void> | void;
  onCancel?: () => void;
  className?: string;
}

export function TriagePriorityOverrideForm({
  patient,
  recommendation,
  currentPriority,
  onConfirm,
  onCancel,
  className,
}: TriagePriorityOverrideFormProps) {
  const [finalDecision, setFinalDecision] = useState<TriagePriority>(
    currentPriority,
  );
  const [reason, setReason] = useState("");
  const [freeText, setFreeText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Unchanged guard, as in the queue: an Override must change the decision.
  const unchanged = finalDecision === recommendation;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (reason === "") {
      setError("Select a reason before confirming.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await onConfirm?.({
        finalDecision,
        reason: reason as OverrideReasonValue,
        freeText: reason === "other" ? freeText : null,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={cx(
        "flex flex-col gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6",
        className,
      )}
    >
      <h3 className="text-title-3-medium text-text-primary">Override</h3>
      <p className="text-body-medium text-text-secondary">{patient}</p>

      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <p className="text-caption-1-medium text-text-secondary">
            Machine Recommendation
          </p>
          <TriagePriorityBadge priority={recommendation} />
        </div>
      </div>

      <p className="text-body-medium text-text-secondary">
        An override changes the Final Decision and keeps the recommendation on
        record.
      </p>

      <div className="flex flex-col gap-3">
        <Select
          label="Final Decision"
          triggerClassName="min-h-11"
          selectedKey={finalDecision}
          onSelectionChange={(key) => setFinalDecision(key as TriagePriority)}
        >
          {URGENCY_LEVELS.map((level) => (
            <SelectItem key={level} id={level} textValue={triagePriorityLabel(level)}>
              {triagePriorityLabel(level)}
            </SelectItem>
          ))}
        </Select>

        <Select
          label="Override Reason"
          triggerClassName="min-h-11"
          isRequired
          placeholder="Select a reason"
          selectedKey={reason === "" ? null : reason}
          onSelectionChange={(key) => setReason(key === null ? "" : String(key))}
        >
          {OVERRIDE_REASONS.map((value) => (
            <SelectItem key={value} id={value} textValue={value}>
              {value}
            </SelectItem>
          ))}
        </Select>

        {reason === "other" ? (
          <Textarea
            label="Other reason"
            value={freeText}
            onChange={setFreeText}
            rows={3}
            maxLength={2000}
            placeholder="Describe the reason in your own words"
          />
        ) : null}

        {unchanged ? (
          <p className="text-body-medium text-text-secondary" role="status">
            Choose a Final Decision different from the Machine Recommendation.
          </p>
        ) : null}

        {error ? (
          <p className="text-body-medium text-text-error-primary" role="status">
            {error}
          </p>
        ) : null}

        <div className="flex gap-3">
          <Button
            type="submit"
            className="min-h-11"
            disabled={saving || reason === "" || unchanged}
            aria-busy={saving}
          >
            {saving ? "Saving…" : "Override"}
          </Button>
          <Button
            variant="secondary"
            className="min-h-11"
            onClick={onCancel}
            disabled={saving}
          >
            Cancel
          </Button>
        </div>
      </div>
    </form>
  );
}