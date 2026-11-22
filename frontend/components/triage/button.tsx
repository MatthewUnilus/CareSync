import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { cx } from "@/utils/cx";

/**
 * TriageAssist UI Kit — Button (Figma file 6ncuGPzBeHmGeytEWAYcaO, Controls sheet 3:77)
 *
 * Variant matrix from Figma:
 *   Variant = Primary (3:260) | Secondary (3:279) | Destructive (3:298)
 *   State   = Default | Pressed | Disabled | Loading
 *
 * Rebuilt on BoardUI's vocabulary — the design decision behind this rebuild:
 *   - tokens: `bg-button-primary` / `bg-button-danger` gradient utilities and
 *     the shared `background-*` / `text-*` / `border-*` semantic families,
 *     with BoardUI Button's exact disabled treatment. No kit-local hex tokens.
 *   - mechanics: BoardUI Button's `button-press-motion` and its shared
 *     `border-border-focus-ring` focus treatment, so kit and app buttons
 *     feel identical in the hand.
 *   - one deliberate deviation stands: the kit keeps a 48px minimum touch
 *     target (clinical gloves / accessibility) where BoardUI's medium is 36px.
 */
export type TriageButtonVariant = "primary" | "secondary" | "destructive";
export type TriageButtonState = "default" | "loading" | "disabled";

export interface TriageButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: TriageButtonVariant;
  /** Loading keeps the default look and prevents duplicate activation; disabled is fully non-actionable. */
  state?: TriageButtonState;
  children?: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

const styles = {
  base: [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "min-h-12 px-4 py-3 rounded-2lg",
    "font-sans select-none",
    "button-press-motion",
    "outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-border-focus-ring",
    "disabled:cursor-not-allowed aria-disabled:cursor-not-allowed",
  ].join(" "),

  variant: {
    primary: {
      default: "bg-button-primary text-text-white shadow-xs",
      loading: "bg-button-primary text-text-white shadow-xs",
    },
    secondary: {
      default: [
        "bg-background-primary-default text-text-primary",
        "border border-border-button-default shadow-xs",
        "hover:bg-background-primary-hover hover:border-border-button-hover",
        "active:bg-background-primary-active active:border-border-button-active",
      ].join(" "),
      loading:
        "bg-background-primary-default text-text-primary border border-border-button-default",
    },
    destructive: {
      default: "bg-button-danger text-text-white shadow-xs",
      loading: "bg-button-danger text-text-white shadow-xs",
    },
  },

  // BoardUI's disabled treatment, lifted from components/base/buttons/button.tsx:
  // neutral disabled surface, tertiary text, no shadow.
  disabled: {
    primary: "bg-background-primary-disabled text-text-tertiary shadow-none",
    secondary:
      "bg-background-primary-disabled text-text-tertiary border border-border-button-default shadow-none",
    destructive: "bg-background-primary-disabled text-text-tertiary shadow-none",
  },
} as const;

export function TriageButton({
  variant = "primary",
  state = "default",
  children,
  className,
  type = "button",
  ref,
  disabled,
  onClick,
  ...props
}: TriageButtonProps) {
  const isDisabled = state === "disabled" || disabled;
  const isLoading = state === "loading";

  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled || isLoading}
      aria-busy={isLoading || undefined}
      aria-disabled={isDisabled || undefined}
      onClick={isLoading ? undefined : onClick}
      className={cx(
        styles.base,
        isDisabled ? styles.disabled[variant] : styles.variant[variant][isLoading ? "loading" : "default"],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** Style maps, exported for the gallery and advanced composition. */
export const triageButtonStyles = styles;
