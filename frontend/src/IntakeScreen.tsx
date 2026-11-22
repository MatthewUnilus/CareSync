import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";

import { api, errorText } from "./api";
import type { Encounter, Sex } from "./api";
import { cardClass, figureClass, mutedTextClass, noticeClass } from "./design";
import { NumberField, ObservationFields } from "./IntakeFields";
import {
  buildIntake,
  buildReasonOnlyIntake,
  emptyIntakeFormValues,
  validateObservationForm,
} from "./intakeForm";
import type { IntakeFormValues, ObservationFieldErrors } from "./intakeForm";
import ObservationChart from "./ObservationChart";
import { SEX_OPTIONS, formatInstant, sexLabel } from "./queueDisplay";

interface FormState extends IntakeFormValues {
  fullName: string;
  hospitalNumber: string;
  age: string;
  sex: Sex;
  phone: string;
  email: string;
}

/**
 * Per-field validation messages. Each key names the field it belongs beside,
 * so one error can never stand in for another or be overwritten by the next
 * check. The reading fields are shared with the chart through
 * `ObservationFieldErrors`.
 */
interface FormErrors extends ObservationFieldErrors {
  fullName?: string;
  age?: string;
  sex?: string;
  phone?: string;
  complaint?: string;
}

const EMPTY_FORM: FormState = {
  ...emptyIntakeFormValues(),
  fullName: "",
  hospitalNumber: "",
  age: "",
  sex: "unspecified",
  phone: "",
  email: "",
};

const fieldsetClass = "grid min-w-0 gap-3";
const legendClass = "pb-1 text-caption-1-medium text-text-secondary";
const gridClass = "grid gap-x-4 gap-y-4 sm:grid-cols-2";

export default function IntakeScreen() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [savedEncounter, setSavedEncounter] = useState<Encounter | null>(null);
  const [recent, setRecent] = useState<Encounter[]>([]);
  const [pending, setPending] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  // A visit may be opened before any vitals are measured. This is a deliberate
  // opt-out, off by default: the ordinary path charts the first set at intake.
  const [vitalsNotMeasured, setVitalsNotMeasured] = useState(false);

  const refreshRecent = useCallback(async () => {
    try {
      const { encounters } = await api.recentEncounters();
      setRecent(encounters);
    } catch {
      // The recency list is a convenience; failing to load it must not block intake.
    }
  }, []);

  useEffect(() => {
    void refreshRecent();
  }, [refreshRecent]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function reset() {
    setForm(EMPTY_FORM);
    setSavedEncounter(null);
    setFieldErrors({});
    setServerError(null);
    setVitalsNotMeasured(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setServerError(null);

    // Validate required fields. Every error is written to the field it belongs
    // to, so a later check can never mask an earlier one. The readings are
    // validated by the same helper the chart uses, so intake and chart agree on
    // every bound — but only when the full intake is being sent: a reason-only
    // visit is opened without vitals, and no partial vital payload is sent.
    const errors: FormErrors = {};
    if (form.fullName.trim() === "") errors.fullName = "Full name is required";
    if (form.age.trim() === "") errors.age = "Age is required";
    if (form.sex === "unspecified") errors.sex = "Sex is required";
    if (form.phone.trim() === "") errors.phone = "Contact phone is required";
    if (form.complaint.trim() === "") {
      errors.complaint = "Presenting complaint is required";
    }
    if (!vitalsNotMeasured) {
      Object.assign(errors, validateObservationForm(form));
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setPending(false);
      return;
    }
    setFieldErrors({});

    try {
      const { body: patient, status } = await api.registerPatient({
        full_name: form.fullName.trim(),
        // A blank hospital number is sent as `null`, so a walk-in with no
        // number registers exactly as before.
        hospital_number: form.hospitalNumber.trim()
          ? form.hospitalNumber.trim()
          : null,
        age: Number(form.age),
        sex: form.sex,
        contact_phone: form.phone.trim(),
        contact_email: form.email.trim() ? form.email.trim() : null,
      });
      const encounter = await api.openEncounter(
        patient.id,
        // Reason-only when vitals are not yet measured; the full intake (reason
        // and the first set of vitals) otherwise, so opening the visit charts its
        // first Observation.
        vitalsNotMeasured
          ? buildReasonOnlyIntake(form)
          : buildIntake(form),
      );
      setSavedEncounter(encounter);
      toast.success(
        status === 201
          ? `New patient ${patient.full_name} registered — encounter #${encounter.id} opened`
          : `Existing patient record for ${patient.full_name} reused — encounter #${encounter.id} opened`,
      );
      await refreshRecent();
    } catch (caught) {
      setServerError(errorText(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Register patient and open encounter
        </h2>
        <p className="text-body-regular text-text-secondary">
          Fields marked <span className="text-text-error-primary">*</span> are
          required before an encounter can open.
        </p>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          {serverError && (
            <p className={noticeClass.error} role="alert">
              {serverError}
            </p>
          )}
          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Patient</legend>
            <div className={gridClass}>
              <Input
                className="col-span-full"
                label="Full name"
                isRequired
                autoComplete="name"
                value={form.fullName}
                onChange={(value) => update("fullName", value)}
                isInvalid={!!fieldErrors.fullName}
                errorMessage={fieldErrors.fullName}
              />
              <Input
                className="col-span-full"
                label="Hospital number"
                hint="Optional — a walk-in without a number can still be registered"
                value={form.hospitalNumber}
                onChange={(value) => update("hospitalNumber", value)}
              />
              <NumberField
                label="Age in years"
                min={0}
                max={120}
                step={1}
                inputMode="numeric"
                value={form.age}
                onChange={(value) => update("age", value)}
                error={!!fieldErrors.age}
                errorMessage={fieldErrors.age}
              />
              <Select
                label="Sex"
                triggerClassName="min-h-11"
                isRequired
                placeholder="Select…"
                className="w-full"
                selectedKey={form.sex === "unspecified" ? null : form.sex}
                onSelectionChange={(key) =>
                  update("sex", (key as Sex | null) ?? "unspecified")
                }
                isInvalid={!!fieldErrors.sex}
                errorMessage={fieldErrors.sex}
              >
                {SEX_OPTIONS.map((option) => (
                  <SelectItem
                    key={option.value}
                    id={option.value}
                    textValue={option.label}
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </Select>
              <Input
                className="col-span-full"
                label="Contact phone"
                isRequired
                type="tel"
                autoComplete="tel"
                placeholder="07700 900123"
                value={form.phone}
                onChange={(value) => update("phone", value)}
                isInvalid={!!fieldErrors.phone}
                errorMessage={fieldErrors.phone}
              />
              <Input
                className="col-span-full"
                label="Contact email"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={(value) => update("email", value)}
              />
            </div>
            <p className="text-body-2-regular text-text-secondary">
              Registering the same name and phone number again reuses the
              existing patient record. Entering a new hospital number here
              registers a distinct record: it does not add the number to an
              existing patient who has none. To attach a number to an existing
              record, open that patient in patient history.
            </p>
          </fieldset>

          <fieldset className={fieldsetClass}>
            <legend className={legendClass}>Reason for visit</legend>
            <Textarea
              label="Presenting complaint"
              isRequired
              rows={3}
              value={form.complaint}
              onChange={(value) => update("complaint", value)}
              isInvalid={!!fieldErrors.complaint}
              errorMessage={fieldErrors.complaint}
            />
          </fieldset>

          <Checkbox
            isSelected={vitalsNotMeasured}
            onChange={setVitalsNotMeasured}
          >
            Vitals not measured yet — open the visit with the reason only
          </Checkbox>

          {vitalsNotMeasured ? (
            <p className={mutedTextClass}>
              No vitals are sent with this visit. They can be charted from the
              patient&rsquo;s chart below and in patient history once they are
              taken.
            </p>
          ) : (
            <ObservationFields
              form={form}
              onChange={(next) =>
                setForm((current) => ({ ...current, ...next }))
              }
              errors={fieldErrors}
            />
          )}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" className="min-h-11" disabled={pending}>
              {pending ? "Saving…" : "Open encounter"}
            </Button>
            {savedEncounter ? (
              <Button
                variant="secondary"
                className="min-h-11"
                onClick={reset}
              >
                Start a new encounter
              </Button>
            ) : null}
          </div>
        </form>
      </section>

      {savedEncounter ? (
        // Keyed by the encounter so a second visit for the same patient remounts
        // the chart, re-reading the new visit's first Observation and starting
        // the form blank.
        <ObservationChart
          key={savedEncounter.id}
          patientId={savedEncounter.patient.id}
          encounterId={savedEncounter.id}
          title={`Vitals for encounter #${savedEncounter.id}`}
        />
      ) : null}

      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Recent encounters
        </h2>
        <p className="text-body-regular text-text-secondary">
          The most recently opened encounters, by arrival.
        </p>
        {recent.length === 0 ? (
          <p className="text-body-regular text-text-secondary">
            No encounters yet
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {recent.map((encounter) => (
              <li
                key={encounter.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-separator-border bg-background-secondary-default p-4"
              >
                <div className="min-w-0 flex-1 basis-48">
                  <p className="text-body-medium font-medium text-text-primary">
                    {encounter.patient.full_name}
                  </p>
                  {/*
                   * The hospital number, and failing that age and sex, sit
                   * beside the name so two patients who share a name are still
                   * distinguishable at the point of selection.
                   */}
                  {encounter.patient.hospital_number ? (
                    <p className="text-body-2-regular text-text-secondary">
                      hospital number{" "}
                      <span className={figureClass}>
                        {encounter.patient.hospital_number}
                      </span>
                    </p>
                  ) : null}
                  <p className="text-body-2-regular text-text-secondary">
                    age {encounter.patient.age} ·{" "}
                    {sexLabel(encounter.patient.sex)} · encounter #
                    {encounter.id} · arrived{" "}
                    {formatInstant(encounter.arrived_at)}
                  </p>
                  <p className="text-body-regular text-text-primary wrap-anywhere">
                    {encounter.reason_for_visit}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
