import type { ReactNode } from "react";
import { FieldError as AriaFieldError } from "react-aria-components";
import { hintTextClassName } from "@/components/base/input/hint-text";

import { InputBase, TextField } from "@/components/base/input/input";
import { Label } from "@/components/base/input/label";
import { Textarea } from "@/components/base/textarea/textarea";

import type { IntakeFormValues, ObservationFieldErrors } from "./intakeForm";
import { NOTES_MAX_LENGTH } from "./intakeForm";

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

const fieldsetClass = "grid min-w-0 gap-3";
const legendClass = "pb-1 text-caption-1-medium text-text-secondary";
const gridClass = "grid gap-x-4 gap-y-4 sm:grid-cols-2";

/**
 * The six instrument readings that form the core of a set of vitals.
 *
 * Reused as they stand by both the intake form and the Observation chart, so a
 * reading can never be charted with one bound at intake and another on the
 * ward. The bounds are the server's, mirrored here only so the native input
 * refuses a value the server would reject anyway.
 */
export function VitalsFields({
  form,
  onChange,
  errors,
}: {
  form: Pick<
    IntakeFormValues,
    | "temperatureC"
    | "heartRate"
    | "respiratoryRate"
    | "systolic"
    | "diastolic"
    | "oxygenSaturation"
  >;
  onChange: (next: Partial<IntakeFormValues>) => void;
  errors?: ObservationFieldErrors;
}) {
  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    onChange({ [key]: value } as Partial<IntakeFormValues>);
  }

  return (
    <fieldset className={fieldsetClass}>
      <legend className={legendClass}>Vitals</legend>
      <div className={gridClass}>
        <NumberField
          label="Temperature (°C)"
          min={30}
          max={45}
          step={0.1}
          inputMode="decimal"
          value={form.temperatureC}
          onChange={(value) => update("temperatureC", value)}
          error={!!errors?.temperatureC}
          errorMessage={errors?.temperatureC}
        />
        <NumberField
          label="Heart rate (bpm)"
          min={20}
          max={300}
          step={1}
          inputMode="numeric"
          value={form.heartRate}
          onChange={(value) => update("heartRate", value)}
          error={!!errors?.heartRate}
          errorMessage={errors?.heartRate}
        />
        <NumberField
          label="Respiratory rate (bpm)"
          min={0}
          max={80}
          step={1}
          inputMode="numeric"
          value={form.respiratoryRate}
          onChange={(value) => update("respiratoryRate", value)}
          error={!!errors?.respiratoryRate}
          errorMessage={errors?.respiratoryRate}
        />
        <NumberField
          label="Blood pressure systolic"
          min={50}
          max={300}
          step={1}
          inputMode="numeric"
          value={form.systolic}
          onChange={(value) => update("systolic", value)}
          error={!!errors?.systolic}
          errorMessage={errors?.systolic}
        />
        <NumberField
          label="Blood pressure diastolic"
          min={20}
          max={200}
          step={1}
          inputMode="numeric"
          value={form.diastolic}
          onChange={(value) => update("diastolic", value)}
          error={!!errors?.diastolic}
          errorMessage={errors?.diastolic}
        />
        <NumberField
          label="Oxygen saturation (%)"
          min={50}
          max={100}
          step={1}
          inputMode="numeric"
          value={form.oxygenSaturation}
          onChange={(value) => update("oxygenSaturation", value)}
          error={!!errors?.oxygenSaturation}
          errorMessage={errors?.oxygenSaturation}
        />
      </div>
    </fieldset>
  );
}

/**
 * A whole set of vitals as a form section: the readings, the pain level and
 * illness duration that belong with them, and an optional note.
 *
 * Shared by intake (where it charts a visit's first Observation) and the chart
 * (where it charts a later one), so both send exactly the same shape.
 */
export function ObservationFields({
  form,
  onChange,
  errors,
}: {
  form: IntakeFormValues;
  onChange: (next: Partial<IntakeFormValues>) => void;
  errors?: ObservationFieldErrors;
}) {
  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    onChange({ [key]: value } as Partial<IntakeFormValues>);
  }

  return (
    <fieldset className={fieldsetClass}>
      <legend className={legendClass}>Vitals and observation</legend>
      <VitalsFields form={form} onChange={onChange} errors={errors} />
      <div className={gridClass}>
        <NumberField
          label="Pain level (1–10)"
          min={1}
          max={10}
          step={1}
          inputMode="numeric"
          value={form.painLevel}
          onChange={(value) => update("painLevel", value)}
          error={!!errors?.painLevel}
          errorMessage={errors?.painLevel}
        />
        <NumberField
          label="Illness duration (hours)"
          min={0}
          max={8760}
          step={0.5}
          inputMode="decimal"
          value={form.durationHours}
          onChange={(value) => update("durationHours", value)}
          error={!!errors?.durationHours}
          errorMessage={errors?.durationHours}
        />
        <Textarea
          className="col-span-full"
          label="Notes (optional)"
          rows={2}
          maxLength={NOTES_MAX_LENGTH}
          showCount
          value={form.notes}
          onChange={(value) => update("notes", value)}
          isInvalid={!!errors?.notes}
          errorMessage={errors?.notes}
        />
      </div>
    </fieldset>
  );
}
