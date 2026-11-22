"use client";

import { useId, type InputHTMLAttributes, type ReactNode, type Ref } from "react";
import {
  TextField,
  InputBase,
} from "@/components/base/input/input";
import { Label } from "@/components/base/input/label";
import { HintText, hintTextClassName } from "@/components/base/input/hint-text";
import { FieldError as AriaFieldError } from "react-aria-components";

/**
 * TriageAssist UI Kit — InputLabeledField (Figma frame 3:332, Controls sheet)
 *
 * Rebuilt on BoardUI's composed Input architecture (TextField → Label →
 * InputBase → HintText/FieldError) so the kit input is mechanically identical
 * to the product screens' intake fields (IntakeFields.tsx NumberField).
 *
 * Key mappings from the Figma spec:
 *   - Visible label always (Label component, Inter Medium 14/20 = text-body-medium)
 *   - Persistent unit suffix via InputBase's trailingAddon (never placeholder-only)
 *   - Placeholder color via BoardUI's `text-text-placeholder` token (fixes Item 7)
 *   - Error state via BoardUI's `text-text-error-primary` and `bg-background-tertiary-error`
 *   - Disabled via BoardUI's disabled tokens
 *   - Focus ring is the shared `border-border-focus-ring` (not kit-local action/primary)
 *   - Sizing: medium (h-9 rounded-2lg) matches BoardUI Input's medium; font is
 *     text-body-regular (14/20) per the field's inner text.
 *
 * The kit's 48px minimum touch target (clinical gloves) applies to buttons only;
 * inputs follow BoardUI's 36px so forms stay dense and scannable.
 */
export type TriageInputState = "default" | "error" | "disabled";

import type { FieldErrorProps as AriaFieldErrorProps } from "react-aria-components";

export interface TriageLabeledInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> {
  label: string;
  /** Persistent unit rendered inside the control (e.g. "%", "bpm"). Never placeholder-only. */
  unit?: string;
  /** Helper text below the control; recolored on error per BoardUI. */
  helper?: ReactNode;
  /** Use for validation messages set on blur/submit. */
  error?: boolean;
  /** Inline error message shown below the field when invalid.
   *  Mirrors Input's errorMessage pattern: shown in place of helper, via React Aria's FieldError. */
  errorMessage?: AriaFieldErrorProps["children"];
  ref?: Ref<HTMLInputElement>;
  /** Input type for numeric fields (pass "number" + min/max/step via ...props). */
  type?: "text" | "number" | "decimal";
  /** Native validation attributes passed straight to InputBase. */
  min?: number;
  max?: number;
  step?: number;
  /** Input mode for mobile keyboards ("numeric" | "decimal"). */
  inputMode?: "numeric" | "decimal";
  /** Placeholder text (colored via BoardUI's text-text-placeholder). */
  placeholder?: string;
}

export function TriageLabeledInput({
  label,
  unit,
  helper,
  error = false,
  errorMessage,
  className,
  ref,
  disabled,
  type = "text",
  min,
  max,
  step,
  inputMode,
  placeholder,
  ...props
}: TriageLabeledInputProps) {
  const autoId = useId();
  const id = props.id ?? `triage-input-${autoId}`;
  const helperId = `triage-input-helper-${autoId}`;

  return (
    <TextField
      isRequired={false}
      // Don't forward the unit/min/max/step — they go to InputBase
      className={className}
      aria-label={undefined}
    >
      {({ isRequired, isInvalid }) => (
        <>
          <Label isRequired={isRequired} isInvalid={isInvalid || error}>
            {label}
          </Label>
          <InputBase
            type={type}
            min={min}
            max={max}
            step={step}
            inputMode={inputMode}
            placeholder={placeholder}
            ref={ref}
            id={id}
            disabled={disabled}
            aria-invalid={error || isInvalid || undefined}
            aria-describedby={helper ? helperId : undefined}
            trailingAddon={unit ? (
              <span aria-hidden="true" className="px-2 text-body-regular text-text-secondary">
                {unit}
              </span>
            ) : undefined}
          />
          {(isInvalid || error) && errorMessage != null ? (
            <AriaFieldError className={hintTextClassName(true)}>
              {errorMessage}
            </AriaFieldError>
          ) : (isInvalid || error) ? (
            <AriaFieldError className={hintTextClassName(true)}>
              {helper ?? "Invalid value"}
            </AriaFieldError>
          ) : helper ? (
            <HintText isInvalid={false}>{helper}</HintText>
          ) : null}
        </>
      )}
    </TextField>
  );
}