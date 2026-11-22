import type { ReactNode } from "react";
import { cx } from "@/utils/cx";

/**
 * TriageAssist UI Kit — CardSurface (Figma frame 3:348)
 *
 * Rebuilt on the app's shared card vocabulary (`src/design.ts cardClass` and
 * the BoardUI rule "cards: rounded-3xl with border-border-button-default"):
 * rounded-3xl, `bg-background-primary-default`, `border-border-button-default`,
 * p-6. The kit's states remap onto BoardUI borders — selection is the shared
 * focus/selection accent (`border-border-focus-ring`), error the shared error
 * border (`border-border-error-default`) — so kit and app cards read as one
 * system. The Figma `loading` state stays caller-supplied, as before.
 */
export type TriageCardState = "default" | "selected" | "error";

const stateBorder = {
  default: "border-border-button-default",
  selected: "border-border-focus-ring",
  error: "border-border-error-default",
} as const;

export function TriageCard({
  state = "default",
  className,
  children,
  ...props
}: {
  state?: TriageCardState;
  className?: string;
  children?: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "flex min-w-0 flex-col gap-3 rounded-3xl border bg-background-primary-default p-6",
        stateBorder[state],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
