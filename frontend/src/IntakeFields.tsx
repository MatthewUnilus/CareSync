import type { ReactNode } from "react";

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
 */
export function NumberField({
  label,
  min,
  max,
  step,
  inputMode,
  value,
  onChange,
}: {
  label: ReactNode;
  min: number;
  max: number;
  step: number;
  inputMode?: "numeric" | "decimal";
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <TextField isRequired value={value} onChange={onChange}>
      {({ isRequired }) => (
        <>
          <Label isRequired={isRequired}>{label}</Label>
          <InputBase
            type="number"
            min={min}
            max={max}
            step={step}
            inputMode={inputMode}
          />
        </>
      )}
    </TextField>
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
  legend,
  form,
  onChange,
  complaintRows = 2,
}: {
  legend: string;
  form: IntakeFormValues;
  onChange: (next: IntakeFormValues) => void;
  complaintRows?: number;
}) {
  function update<K extends keyof IntakeFormValues>(
    key: K,
    value: IntakeFormValues[K],
  ) {
    onChange({ ...form, [key]: value });
  }

  return (
    <fieldset className="grid min-w-0 gap-3">
      <legend className="pb-1 text-caption-1-medium text-text-secondary">
        {legend}
      </legend>
      <div className="grid gap-x-4 gap-y-4 sm:grid-cols-2">
        <Textarea
          className="col-span-full"
          label="Presenting complaint"
          isRequired
          rows={complaintRows}
          value={form.complaint}
          onChange={(value) => update("complaint", value)}
        />
        <NumberField
          label="Pain level (1–10)"
          min={1}
          max={10}
          step={1}
          inputMode="numeric"
          value={form.painLevel}
          onChange={(value) => update("painLevel", value)}
        />
        <NumberField
          label="Illness duration (hours)"
          min={0}
          max={8760}
          step={0.5}
          inputMode="decimal"
          value={form.durationHours}
          onChange={(value) => update("durationHours", value)}
        />
        <NumberField
          label="Temperature (°C)"
          min={30}
          max={45}
          step={0.1}
          inputMode="decimal"
          value={form.temperatureC}
          onChange={(value) => update("temperatureC", value)}
        />
        <NumberField
          label="Heart rate (bpm)"
          min={20}
          max={300}
          step={1}
          inputMode="numeric"
          value={form.heartRate}
          onChange={(value) => update("heartRate", value)}
        />
        <NumberField
          label="Blood pressure systolic"
          min={50}
          max={300}
          step={1}
          inputMode="numeric"
          value={form.systolic}
          onChange={(value) => update("systolic", value)}
        />
        <NumberField
          label="Blood pressure diastolic"
          min={20}
          max={200}
          step={1}
          inputMode="numeric"
          value={form.diastolic}
          onChange={(value) => update("diastolic", value)}
        />
        <NumberField
          label="Oxygen saturation (%)"
          min={50}
          max={100}
          step={1}
          inputMode="numeric"
          value={form.oxygenSaturation}
          onChange={(value) => update("oxygenSaturation", value)}
        />
        <Textarea
          className="col-span-full"
          label="Notes (optional)"
          rows={2}
          value={form.notes}
          onChange={(value) => update("notes", value)}
        />
      </div>
    </fieldset>
  );
}
