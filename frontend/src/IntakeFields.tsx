import type { ReactNode } from "react";
import { FieldError as AriaFieldError } from "react-aria-components";
import { hintTextClassName } from "@/components/base/input/hint-text";

import { InputBase, TextField } from "@/components/base/input/input";
import { Label } from "@/components/base/input/label";
import { Textarea } from "@/components/base/textarea/textarea";

import type { IntakeFormValues } from "./intakeForm";

/**
 * Numeric intake field built from Input's own pieces. The composed `Input`
 * cannot carry `min`/`max`/`step` (React Aria's TextField props do not
 * include them), so this composes TextField → Label → InputBase, which passes
 * the range attributes straight to the native input and keeps native
 * validation working exactly as before.
 *
 * Extended with optional `error` and `errorMessage` props for inline validation
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

export interface IntakeFieldsErrors {
  complaint?: string;
  painLevel?: string;
  durationHours?: string;
  temperatureC?: string;
  heartRate?: string;
  respiratoryRate?: string;
  systolic?: string;
  diastolic?: string;
  oxygenSaturation?: string;
  notes?: string;
}

/**
 * Vitals fieldset — core physiological measurements.
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
  errors?: IntakeFieldsErrors;
}) {
  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    onChange({ [key]: value } as Partial<IntakeFormValues>);
  }

  return (
    <fieldset className="grid min-w-0 gap-3">
      <legend className="pb-1 text-caption-1-medium text-text-secondary">
        Vitals
      </legend>
      <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
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
 * Complaint fieldset — subjective presentation.
 */
export function ComplaintFields({
  form,
  onChange,
  errors,
  complaintRows = 2,
}: {
  form: Pick<
    IntakeFormValues,
    "complaint" | "painLevel" | "durationHours" | "notes"
  >;
  onChange: (next: Partial<IntakeFormValues>) => void;
  errors?: IntakeFieldsErrors;
  complaintRows?: number;
}) {
  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    onChange({ [key]: value } as Partial<IntakeFormValues>);
  }

  return (
    <fieldset className="grid min-w-0 gap-3">
      <legend className="pb-1 text-caption-1-medium text-text-secondary">
        Complaint
      </legend>
      <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
        <Textarea
          className="col-span-full"
          label="Presenting complaint"
          isRequired
          rows={complaintRows}
          value={form.complaint}
          onChange={(value) => update("complaint", value)}
          isInvalid={!!errors?.complaint}
          errorMessage={errors?.complaint}
        />
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
          value={form.notes}
          onChange={(value) => update("notes", value)}
          isInvalid={!!errors?.notes}
          errorMessage={errors?.notes}
        />
      </div>
    </fieldset>
  );
}

/**
 * The intake fields, shared by intake capture and Re-assessment.
 *
 * Both flows send exactly the same shape and the same numeric conversions
 * (`intakeForm.ts`); keeping the markup in one place means a field can never be
 * added to one form and silently omitted from the other.
 */
export default function IntakeFields({
  form,
  onChange,
  complaintRows = 2,
  errors,
}: {
  form: IntakeFormValues;
  onChange: (next: Partial<IntakeFormValues>) => void;
  complaintRows?: number;
  errors?: IntakeFieldsErrors;
}) {
  // Wrap the partial update to match VitalsFields/ComplaintFields' onChange signature
  const handlePartialChange = (next: Partial<IntakeFormValues>) => {
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-6">
      <VitalsFields
        form={{
          temperatureC: form.temperatureC,
          heartRate: form.heartRate,
          respiratoryRate: form.respiratoryRate,
          systolic: form.systolic,
          diastolic: form.diastolic,
          oxygenSaturation: form.oxygenSaturation,
        }}
        onChange={handlePartialChange}
        errors={errors}
      />
      <ComplaintFields
        form={{
          complaint: form.complaint,
          painLevel: form.painLevel,
          durationHours: form.durationHours,
          notes: form.notes,
        }}
        onChange={handlePartialChange}
        errors={errors}
        complaintRows={complaintRows}
      />
    </div>
  );
}