/**
 * TriageAssist UI Kit — public surface.
 *
 * Self-contained component library built from the Figma UI kit
 * (file 6ncuGPzBeHmGeytEWAYcaO). Bound to BoardUI's semantic tokens and
 * composite type utilities (styles/theme.css, styles/typography.css) — the
 * kit has no token system of its own. Its one deliberate deviation: a 48px
 * minimum touch target on interactive controls (clinical gloves /
 * accessibility) where BoardUI's medium control is 36px.
 *
 * Vocabulary follows CONTEXT.md's glossary: Machine Recommendation, Urgency
 * Level, Override, Final Decision — never "AI", never "reviewed".
 */
export { TriageButton, triageButtonStyles } from "./button";
export type {
  TriageButtonProps,
  TriageButtonState,
  TriageButtonVariant,
} from "./button";

export {
  TriagePriorityBadge,
  triagePriorityLabel,
} from "./priority-badge";
export type { TriagePriority } from "./priority-badge";

export { TriageLabeledInput } from "./labeled-input";
export type {
  TriageInputState,
  TriageLabeledInputProps,
} from "./labeled-input";

export { TriageCard } from "./card";
export type { TriageCardState } from "./card";

export { TriageConnectionBanner } from "./connection-banner";
export type { TriageConnectionState } from "./connection-banner";

export { TriagePatientListItem } from "./patient-list-item";
export type { TriagePatientListItemProps } from "./patient-list-item";

export { TriagePatientCardCompact } from "./patient-card-compact";
export type { TriagePatientCardCompactProps } from "./patient-card-compact";

export { TriageVitalSignsCard } from "./vital-signs-card";
export type {
  TriageVitalRow,
  TriageVitalSignsCardProps,
} from "./vital-signs-card";

export { TriagePriorityResultCard } from "./priority-result-card";
export type {
  TriageDecisionStatus,
  TriagePriorityResultCardProps,
} from "./priority-result-card";

export { TriagePriorityOverrideForm } from "./priority-override-form";
export type {
  OverrideReasonValue,
  TriagePriorityOverrideFormProps,
} from "./priority-override-form";

export { TriageQueueState } from "./queue-state";
export type { TriageQueueStateProps } from "./queue-state";

export { TriageConfirmationModal } from "./confirmation-modal";
export type { TriageConfirmationModalProps } from "./confirmation-modal";
