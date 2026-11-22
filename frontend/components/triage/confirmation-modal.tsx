import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "@/utils/cx";
import { TriageButton } from "./button";

/**
 * TriageAssist UI Kit — ConfirmationModal (Figma frame 3:630, "Delete draft")
 *
 * Rebuilt on BoardUI tokens. The destructive-confirm dialog follows the
 * app's actual destruction flow (the queue's Departure two-step inline
 * confirm uses the same vocabulary: the first press arms, the second
 * commits).
 *
 * BoardUI bindings:
 *   - Panel: rounded-3xl, border-border-button-default,
 *     bg-background-primary-default, p-6 — the standard card recipe, elevated
 *     on a dimmed page ground (bg-background-tertiary-default/80).
 *   - Title: text-title-3-medium. Body: text-body-medium.
 *   - Actions: kit buttons (secondary cancel + destructive confirm) with the
 *     kit's 48px clinical touch target, matching the kit's other actions.
 *
 * Focus contract preserved from the Figma note: focus starts on the cancel
 * action, Escape cancels, and focus returns to the initiating element on
 * close. While a deletion is in flight, the confirm shows its loading label
 * and the overlay stops dismissing on click/Escape so a double-press cannot
 * skip the confirmation record.
 */
export interface TriageConfirmationModalProps {
  open: boolean;
  /** e.g. "Delete intake draft?". */
  title: string;
  /** e.g. "Alex Morgan · Local draft TA-0107". */
  contextLine?: string;
  /** Warning body, e.g. "This will remove the saved intake from this device…". */
  children?: ReactNode;
  confirmLabel?: string;
  deletingLabel?: string;
  cancelLabel?: string;
  deleting?: boolean;
  onConfirm?: () => void;
  onCancel: () => void;
  className?: string;
}

export function TriageConfirmationModal({
  open,
  title,
  contextLine,
  children,
  confirmLabel = "Delete draft",
  deletingLabel = "Deleting…",
  cancelLabel = "Keep draft",
  deleting = false,
  onConfirm,
  onCancel,
  className,
}: TriageConfirmationModalProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    restoreRef.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !deleting) {
        event.stopPropagation();
        onCancel();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      // Return focus to the initiating action on close.
      restoreRef.current?.focus();
      restoreRef.current = null;
    };
  }, [open, onCancel, deleting]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background-tertiary-default/80 p-6"
      onClick={deleting ? undefined : onCancel}
    >
      <section
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        className={cx(
          "flex w-full max-w-[508px] flex-col gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6 shadow-lg",
          className,
        )}
      >
        <h2 className="text-title-3-medium text-text-primary">{title}</h2>
        {contextLine ? (
          <p className="text-body-medium text-text-secondary">{contextLine}</p>
        ) : null}
        <div className="text-body-medium text-text-secondary">{children}</div>
        <div className="mt-2 flex gap-3">
          <TriageButton
            ref={cancelRef}
            variant="secondary"
            disabled={deleting}
            onClick={onCancel}
          >
            {cancelLabel}
          </TriageButton>
          <TriageButton
            variant="destructive"
            state={deleting ? "loading" : "default"}
            onClick={onConfirm}
          >
            {deleting ? deletingLabel : confirmLabel}
          </TriageButton>
        </div>
      </section>
    </div>
  );
}