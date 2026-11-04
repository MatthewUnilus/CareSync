import type { IntakeFormValues } from "./intakeForm";

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
    <fieldset className="intake-fieldset">
      <legend>{legend}</legend>
      <div className="intake-grid">
        <label className="span-all">
          Presenting complaint <span className="required-mark">*</span>
          <textarea
            required
            rows={complaintRows}
            value={form.complaint}
            onChange={(event) => update("complaint", event.target.value)}
          />
        </label>
        <label>
          Pain level (1–10) <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={1}
            max={10}
            step={1}
            value={form.painLevel}
            onChange={(event) => update("painLevel", event.target.value)}
          />
        </label>
        <label>
          Illness duration (hours) <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={0}
            max={8760}
            step={0.5}
            inputMode="decimal"
            value={form.durationHours}
            onChange={(event) => update("durationHours", event.target.value)}
          />
        </label>
        <label>
          Temperature (°C) <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={30}
            max={45}
            step={0.1}
            inputMode="decimal"
            value={form.temperatureC}
            onChange={(event) => update("temperatureC", event.target.value)}
          />
        </label>
        <label>
          Heart rate (bpm) <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={20}
            max={300}
            step={1}
            inputMode="numeric"
            value={form.heartRate}
            onChange={(event) => update("heartRate", event.target.value)}
          />
        </label>
        <label>
          Blood pressure systolic <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={50}
            max={300}
            step={1}
            inputMode="numeric"
            value={form.systolic}
            onChange={(event) => update("systolic", event.target.value)}
          />
        </label>
        <label>
          Blood pressure diastolic <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={20}
            max={200}
            step={1}
            inputMode="numeric"
            value={form.diastolic}
            onChange={(event) => update("diastolic", event.target.value)}
          />
        </label>
        <label>
          Oxygen saturation (%) <span className="required-mark">*</span>
          <input
            type="number"
            required
            min={50}
            max={100}
            step={1}
            inputMode="numeric"
            value={form.oxygenSaturation}
            onChange={(event) => update("oxygenSaturation", event.target.value)}
          />
        </label>
        <label className="span-all">
          Notes (optional)
          <textarea
            rows={2}
            value={form.notes}
            onChange={(event) => update("notes", event.target.value)}
          />
        </label>
      </div>
    </fieldset>
  );
}
