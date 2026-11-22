import { cx } from "@/utils/cx";
import { TriageButton } from "./button";

/**
 * TriageAssist UI Kit — QueueState (Figma frame 3:609)
 *
 * Rebuilt on BoardUI vocabulary:
 *   - Card is the shared recipe: rounded-3xl, border-border-button-default,
 *     bg-background-primary-default, p-6.
 *   - Loading skeletons use BoardUI's surface-tertiary for the bars.
 *   - Title/description use BoardUI composite type utilities.
 *   - Error mode has `role="alert"`.
 */
export interface TriageQueueStateProps {
  mode: "loading" | "empty" | "error";
  /** Empty / Error title, e.g. "Queue is empty" / "Couldn't load the queue". */
  title?: string;
  /** Supporting line for empty/error, e.g. "New arrivals will appear here." */
  description?: string;
  /** Empty-mode action label. Error mode is fixed to "Retry". */
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

const SKELETON_WIDTHS = ["w-[282px]", "w-[200px]", "w-[250px]"];

export function TriageQueueState({
  mode,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: TriageQueueStateProps) {
  return (
    <div
      className={cx(
        "flex min-h-65 flex-col gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6",
        className,
      )}
      role={mode === "error" ? "alert" : undefined}
    >
      {mode === "loading" ? (
        <div className="flex flex-col gap-3" aria-hidden="true">
          {SKELETON_WIDTHS.map((width, index) => (
            <div
              key={index}
              className={`h-4 rounded-sm bg-background-tertiary-default ${width}`}
            />
          ))}
        </div>
      ) : (
        <>
          {title ? (
            <h3 className="text-title-3-medium text-text-primary">{title}</h3>
          ) : null}
          {description ? (
            <p className="text-body-medium text-text-secondary">{description}</p>
          ) : null}
          {mode !== "empty" && !onAction ? null : (
            <TriageButton
              variant={mode === "error" ? "secondary" : "primary"}
              onClick={onAction}
            >
              {mode === "error" ? "Retry" : actionLabel}
            </TriageButton>
          )}
        </>
      )}
    </div>
  );
}