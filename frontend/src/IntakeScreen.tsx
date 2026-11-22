import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";

import { api, errorText } from "./api";
import type { Encounter, Sex } from "./api";
import { cardClass, noticeClass } from "./design";
import { NumberField } from "./IntakeFields";
import { buildIntake } from "./intakeForm";
import type { IntakeFormValues } from "./intakeForm";
import { SEX_OPTIONS, formatInstant, sexLabel } from "./queueDisplay";

interface FormState extends IntakeFormValues {
  fullName: string;
  age: string;
  sex: Sex;
  phone: string;
  email: string;
}

/**
 * Per-field validation messages. Each key names the field it belongs beside,
 * so one error can never stand in for another or be overwritten by the next
 * check.
 */
interface FormErrors {
  fullName?: string;
  age?: string;
  sex?: string;
  phone?: string;
  complaint?: string;
}

const EMPTY_FORM: FormState = {
  fullName: "",
  age: "",
  sex: "unspecified",
  phone: "",
  email: "",
  complaint: "",
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
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setServerError(null);

    // Validate required fields. Every error is written to the field it belongs
    // to, so a later check can never mask an earlier one.
    const errors: FormErrors = {};
    if (form.fullName.trim() === "") errors.fullName = "Full name is required";
    if (form.age.trim() === "") errors.age = "Age is required";
    if (form.sex === "unspecified") errors.sex = "Sex is required";
    if (form.phone.trim() === "") errors.phone = "Contact phone is required";
    if (form.complaint.trim() === "") {
      errors.complaint = "Presenting complaint is required";
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
        age: Number(form.age),
        sex: form.sex,
        contact_phone: form.phone.trim(),
        contact_email: form.email.trim() ? form.email.trim() : null,
      });
      const encounter = await api.openEncounter(patient.id, buildIntake(form));
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
              existing patient record
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
                   * Age and sex sit beside the name so two patients who share a
                   * name are still distinguishable at the point of selection.
                   * There is no medical record number in scope, so this is the
                   * identity the prototype can honestly show.
                   */}
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
