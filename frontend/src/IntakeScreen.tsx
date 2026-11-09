import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Select, SelectItem } from "@/components/base/select/select";
import { toast } from "@/components/base/toast/toast";

import { api, ApiError } from "./api";
import type { Encounter, Sex } from "./api";
import { cardClass } from "./design";
import IntakeFields, { NumberField } from "./IntakeFields";
import { buildIntake, intakeFormValues } from "./intakeForm";
import type { IntakeFormValues } from "./intakeForm";

const SEX_OPTIONS: { value: Sex; label: string }[] = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "unspecified", label: "Unspecified" },
];

interface FormState extends IntakeFormValues {
  fullName: string;
  age: string;
  sex: Sex | "";
  phone: string;
  email: string;
}

const EMPTY_FORM: FormState = {
  fullName: "",
  age: "",
  sex: "",
  phone: "",
  email: "",
  complaint: "",
  painLevel: "",
  durationHours: "",
  temperatureC: "",
  heartRate: "",
  systolic: "",
  diastolic: "",
  oxygenSaturation: "",
  notes: "",
};

const EMPTY_REASSESS_FORM: IntakeFormValues = {
  complaint: "",
  painLevel: "",
  durationHours: "",
  temperatureC: "",
  heartRate: "",
  systolic: "",
  diastolic: "",
  oxygenSaturation: "",
  notes: "",
};

function sexLabel(sex: Sex): string {
  return SEX_OPTIONS.find((option) => option.value === sex)?.label ?? sex;
}

function formatInstant(value: string): string {
  return new Date(value).toLocaleString();
}

function errorText(caught: unknown): string {
  return caught instanceof ApiError
    ? caught.message
    : "Unable to reach the server.";
}

const fieldsetClass = "grid min-w-0 gap-3";
const legendClass = "pb-1 text-caption-1-medium text-text-tertiary";
const gridClass = "grid gap-x-4 gap-y-4 sm:grid-cols-2";

export default function IntakeScreen() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [savedEncounter, setSavedEncounter] = useState<Encounter | null>(null);
  const [recent, setRecent] = useState<Encounter[]>([]);
  const [pending, setPending] = useState(false);

  // A correction to captured intake is expressed as a Re-assessment. The
  // intake on an existing Assessment is frozen; a new Assessment records the
  // corrected values and becomes the one that governs the Queue.
  const [reassessing, setReassessing] = useState<Encounter | null>(null);
  const [reassessForm, setReassessForm] = useState<IntakeFormValues>(
    EMPTY_REASSESS_FORM,
  );
  const [reassessPending, setReassessPending] = useState(false);

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
    setReassessing(null);
  }

  function startReassessment(encounter: Encounter) {
    setReassessing(encounter);
    setReassessForm(intakeFormValues(encounter.intake));
  }

  function cancelReassessment() {
    setReassessing(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      if (form.sex === "") {
        toast.error("Select the Patient's sex.");
        return;
      }
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
      toast.error(errorText(caught));
    } finally {
      setPending(false);
    }
  }

  async function handleReassess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reassessing) {
      return;
    }
    setReassessPending(true);
    try {
      const { body: updated } = await api.reassessEncounter(
        reassessing.id,
        buildIntake(reassessForm),
      );
      setReassessing(updated);
      setReassessForm(intakeFormValues(updated.intake));
      toast.success(
        `Re-assessment recorded for encounter #${updated.id}. The new assessment now governs the queue.`,
      );
      await refreshRecent();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setReassessPending(false);
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
          required before an assessment can run. Notes are optional.
        </p>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
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
              />
              <NumberField
                label="Age in years"
                min={0}
                max={120}
                step={1}
                inputMode="numeric"
                value={form.age}
                onChange={(value) => update("age", value)}
              />
              <Select
                label="Sex"
                isRequired
                placeholder="Select…"
                className="w-full"
                selectedKey={form.sex === "" ? null : form.sex}
                onSelectionChange={(key) =>
                  update("sex", (key as Sex | null) ?? "")
                }
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

          <IntakeFields
            legend="Intake"
            form={form}
            onChange={(next) =>
              setForm((current) => ({ ...current, ...next }))
            }
            complaintRows={3}
          />

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Open encounter"}
            </Button>
            {savedEncounter ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() => startReassessment(savedEncounter)}
                >
                  Re-assess this encounter
                </Button>
                <Button variant="secondary" onClick={reset}>
                  Start a new encounter
                </Button>
              </>
            ) : null}
          </div>
        </form>
      </section>

      {reassessing ? (
        <section className={cardClass}>
          <h2 className="text-title-3-medium text-text-primary">
            Re-assess encounter #{reassessing.id}
          </h2>
          <p className="text-body-regular text-text-secondary">
            Intake is frozen once its triage assessment exists. To correct a
            typo, record the encounter&rsquo;s current condition here: this
            appends a new assessment and the earlier one stays on record.
          </p>
          <dl className="grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-x-4 gap-y-3">
            <div>
              <dt className={legendClass}>Patient</dt>
              <dd className="text-body-semibold text-text-primary wrap-anywhere">
                {reassessing.patient.full_name}
              </dd>
            </div>
            <div>
              <dt className={legendClass}>Age</dt>
              <dd className="text-body-semibold text-text-primary">
                {reassessing.patient.age}
              </dd>
            </div>
            <div>
              <dt className={legendClass}>Sex</dt>
              <dd className="text-body-semibold text-text-primary">
                {sexLabel(reassessing.patient.sex)}
              </dd>
            </div>
            <div>
              <dt className={legendClass}>Arrived</dt>
              <dd className="text-body-semibold text-text-primary">
                {formatInstant(reassessing.arrived_at)}
              </dd>
            </div>
          </dl>

          <form className="flex flex-col gap-4" onSubmit={handleReassess}>
            <IntakeFields
              legend="Current intake"
              form={reassessForm}
              onChange={setReassessForm}
            />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={reassessPending}>
                {reassessPending ? "Re-assessing…" : "Save and re-assess"}
              </Button>
              <Button variant="secondary" onClick={cancelReassessment}>
                Cancel
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      <section className={cardClass}>
        <h2 className="text-title-3-medium text-text-primary">
          Recent encounters
        </h2>
        <p className="text-body-regular text-text-secondary">
          Intake is locked once the encounter&rsquo;s triage assessment exists,
          which is as soon as the encounter opens. A correction is therefore an
          explicit re-assessment, prefilled with the current intake. This list
          is by arrival, not the queue.
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
                  <p className="text-body-2-regular text-text-secondary">
                    Encounter #{encounter.id} · arrived{" "}
                    {formatInstant(encounter.arrived_at)}
                  </p>
                  <p className="text-body-regular text-text-primary wrap-anywhere">
                    {encounter.intake.presenting_complaint}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="small"
                  onClick={() => startReassessment(encounter)}
                >
                  Re-assess
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
