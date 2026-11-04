import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type { Encounter, Sex } from "./api";
import IntakeFields from "./IntakeFields";
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

interface Notice {
  kind: "success" | "error";
  text: string;
}

function sexLabel(sex: Sex): string {
  return SEX_OPTIONS.find((option) => option.value === sex)?.label ?? sex;
}

function formatInstant(value: string): string {
  return new Date(value).toLocaleString();
}

export default function IntakeScreen() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [savedEncounter, setSavedEncounter] = useState<Encounter | null>(null);
  const [recent, setRecent] = useState<Encounter[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
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
    setNotice(null);
  }

  function startReassessment(encounter: Encounter) {
    setReassessing(encounter);
    setReassessForm(intakeFormValues(encounter.intake));
    setNotice(null);
  }

  function cancelReassessment() {
    setReassessing(null);
    setNotice(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setPending(true);
    try {
      if (form.sex === "") {
        setNotice({ kind: "error", text: "Select the Patient's sex." });
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
      setNotice({
        kind: "success",
        text:
          status === 201
            ? `New Patient ${patient.full_name} registered — Encounter #${encounter.id} opened.`
            : `Existing Patient record for ${patient.full_name} reused — Encounter #${encounter.id} opened.`,
      });
      await refreshRecent();
    } catch (caught) {
      setNotice({
        kind: "error",
        text:
          caught instanceof ApiError
            ? caught.message
            : "Unable to reach the server.",
      });
    } finally {
      setPending(false);
    }
  }

  async function handleReassess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reassessing) {
      return;
    }
    setNotice(null);
    setReassessPending(true);
    try {
      const { body: updated } = await api.reassessEncounter(
        reassessing.id,
        buildIntake(reassessForm),
      );
      setReassessing(updated);
      setReassessForm(intakeFormValues(updated.intake));
      setNotice({
        kind: "success",
        text: `Re-assessment recorded for Encounter #${updated.id}. The new Assessment now governs the Queue.`,
      });
      await refreshRecent();
    } catch (caught) {
      setNotice({
        kind: "error",
        text:
          caught instanceof ApiError
            ? caught.message
            : "Unable to reach the server.",
      });
    } finally {
      setReassessPending(false);
    }
  }

  return (
    <>
      <section className="card">
        <h2>Register Patient and open Encounter</h2>
        <p className="muted">
          Fields marked <span className="required-mark">*</span> are required
          before an assessment can run. Notes are optional.
        </p>

        <form className="stack" onSubmit={handleSubmit}>
          <fieldset className="intake-fieldset">
            <legend>Patient</legend>
            <div className="intake-grid">
              <label className="span-all">
                Full name <span className="required-mark">*</span>
                <input
                  required
                  autoComplete="name"
                  value={form.fullName}
                  onChange={(event) => update("fullName", event.target.value)}
                />
              </label>
              <label>
                Age in years <span className="required-mark">*</span>
                <input
                  type="number"
                  required
                  min={0}
                  max={120}
                  step={1}
                  value={form.age}
                  onChange={(event) => update("age", event.target.value)}
                />
              </label>
              <label>
                Sex <span className="required-mark">*</span>
                <select
                  required
                  value={form.sex}
                  onChange={(event) =>
                    update("sex", event.target.value as Sex | "")
                  }
                >
                  <option value="" disabled>
                    Select…
                  </option>
                  {SEX_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-all">
                Contact phone <span className="required-mark">*</span>
                <input
                  required
                  type="tel"
                  autoComplete="tel"
                  placeholder="07700 900123"
                  value={form.phone}
                  onChange={(event) => update("phone", event.target.value)}
                />
              </label>
              <label className="span-all">
                Contact email
                <input
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                />
              </label>
            </div>
            <p className="muted">
              Registering the same name and phone number again reuses the
              existing Patient record.
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

          <div className="row">
            <button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Open Encounter"}
            </button>
            {savedEncounter ? (
              <>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => startReassessment(savedEncounter)}
                >
                  Re-assess this Encounter
                </button>
                <button type="button" className="secondary" onClick={reset}>
                  Start a new Encounter
                </button>
              </>
            ) : null}
          </div>

          {notice ? (
            <p className={`notice notice-${notice.kind}`} role="status">
              {notice.text}
            </p>
          ) : null}
        </form>
      </section>

      {reassessing ? (
        <section className="card">
          <h2>Re-assess Encounter #{reassessing.id}</h2>
          <p className="muted">
            Intake is frozen once its Triage Assessment exists. To correct a
            typo, record the Encounter&rsquo;s current condition here: this
            appends a new Assessment and the earlier one stays on record.
          </p>
          <dl className="facts">
            <div>
              <dt>Patient</dt>
              <dd>{reassessing.patient.full_name}</dd>
            </div>
            <div>
              <dt>Age</dt>
              <dd>{reassessing.patient.age}</dd>
            </div>
            <div>
              <dt>Sex</dt>
              <dd>{sexLabel(reassessing.patient.sex)}</dd>
            </div>
            <div>
              <dt>Arrived</dt>
              <dd>{formatInstant(reassessing.arrived_at)}</dd>
            </div>
          </dl>

          <form className="stack" onSubmit={handleReassess}>
            <IntakeFields
              legend="Current intake"
              form={reassessForm}
              onChange={setReassessForm}
            />
            <div className="row">
              <button type="submit" disabled={reassessPending}>
                {reassessPending ? "Re-assessing…" : "Save and re-assess"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={cancelReassessment}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="card">
        <h2>Recent Encounters</h2>
        <p className="muted">
          Intake is locked once the Encounter&rsquo;s Triage Assessment exists,
          which is as soon as the Encounter opens. A correction is therefore an
          explicit Re-assessment, prefilled with the current intake. This list is
          by arrival, not the Queue.
        </p>
        {recent.length === 0 ? (
          <p className="muted">No Encounters yet.</p>
        ) : (
          <ul className="encounter-list">
            {recent.map((encounter) => (
              <li key={encounter.id} className="encounter-item">
                <div className="encounter-text">
                  <strong>{encounter.patient.full_name}</strong>
                  <p className="muted">
                    Encounter #{encounter.id} · arrived{" "}
                    {formatInstant(encounter.arrived_at)}
                  </p>
                  <p className="encounter-complaint">
                    {encounter.intake.presenting_complaint}
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => startReassessment(encounter)}
                >
                  Re-assess
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
