import type { ReactNode } from "react";
import { FieldError as AriaFieldError } from "react-aria-components";
import { hintTextClassName } from "@/components/base/input/hint-text";

import { InputBase, TextField } from "@/components/base/input/input";
import { Label } from "@/components/base/input/label";

/**
 * Numeric field built from Input's own pieces. The composed `Input` cannot
 * carry `min`/`max`/`step` (React Aria's TextField props do not include them),
 * so this composes TextField → Label → InputBase, which passes the range
 * attributes straight to the native input and keeps native validation working
 * exactly as before.
 *
 * Carries optional `error` and `errorMessage` props for inline validation
 * display, mirroring the composed Input/Select/Textarea error pattern.
 */
export function NumberField({
  label,
  min,
  max,
  step,
  inputMode,
  value,
  onChange,
  error = false,
  errorMessage,
}: {
  label: ReactNode;
  min: number;
  max: number;
  step: number;
  inputMode?: "numeric" | "decimal";
  value: string;
  onChange: (value: string) => void;
  error?: boolean;
  errorMessage?: ReactNode;
}) {
  return (
    <TextField isRequired value={value} onChange={onChange} isInvalid={error}>
      {({ isRequired, isInvalid }) => (
        <>
          <Label isRequired={isRequired} isInvalid={isInvalid}>
            {label}
          </Label>
          <InputBase
            type="number"
            min={min}
            max={max}
            step={step}
            inputMode={inputMode}
            aria-invalid={isInvalid}
          />
          {isInvalid && errorMessage != null ? (
            <AriaFieldError className={hintTextClassName(true)}>
              {errorMessage}
            </AriaFieldError>
          ) : null}
        </>
      )}
    </TextField>
  );
}
