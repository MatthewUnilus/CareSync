import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type { Encounter, Intake, Sex } from "./api";

const SEX_OPTIONS: { value: Sex; label: string }[] = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "unspecified", label: "Unspecified" },
];

interface FormState {
  fullName: string;
  age: string;
  sex: Sex | "";
  phone: string;
  email: string;
  complaint: string;
  painLevel: string;
  durationHours: string;
  temperatureC: string;
  heartRate: string;
  systolic: string;
  diastolic: string;
  oxygenSaturation: string;
  notes: string;
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

interface Notice {
  kind: "success" | "error";
  text: string;
}

function buildIntake(form: FormState): Intake {
  return {
    presenting_complaint: form.complaint.trim(),
    pain_level: Number(form.painLevel),
    illness_duration_hours: Number(form.durationHours),
    temperature_c: Number(form.temperatureC),
    heart_rate_bpm: Number(form.heartRate),
    blood_pressure: {
      systolic: Number(form.systolic),
      diastolic: Number(form.diastolic),
    },
    oxygen_saturation_percent: Number(form.oxygenSaturation),
    notes: form.notes.trim() ? form.notes.trim() : null,
  };
}

function intakeFields(intake: Intake): Partial<FormState> {
  return {
    complaint: intake.presenting_complaint,
    painLevel: String(intake.pain_level),
    durationHours: String(intake.illness_duration_hours),
    temperatureC: String(intake.temperature_c),
    heartRate: String(intake.heart_rate_bpm),
    systolic: String(intake.blood_pressure.systolic),
    diastolic: String(intake.blood_pressure.diastolic),
    oxygenSaturation: String(intake.oxygen_saturation_percent),
    notes: intake.notes ?? "",
  };
}

function sexLabel(sex: Sex): string {
  return SEX_OPTIONS.find((option) => option.value === sex)?.label ?? sex;
}

function formatInstant(value: string): string {
  return new Date(value).toLocaleString();
}

export default function IntakeScreen() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [target, setTarget] = useState<Encounter | null>(null);
  const [savedEncounter, setSavedEncounter] = useState<Encounter | null>(null);
  const [recent, setRecent] = useState<Encounter[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pending, setPending] = useState(false);

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
    setTarget(null);
    setSavedEncounter(null);
    setNotice(null);
  }

  function startCorrection(encounter: Encounter) {
    setTarget(encounter);
    setSavedEncounter(null);
    setNotice(null);
    setForm((current) => ({ ...current, ...intakeFields(encounter.intake) }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setPending(true);
    try {
      if (target) {
        const corrected = await api.correctIntake(target.id, buildIntake(form));
        setTarget(corrected);
        setNotice({
          kind: "success",
          text: `Intake corrected for Encounter #${corrected.id}.`,
        });
      } else {
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
      }
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

  return (
    <>
      <section className="card">
        <h2>
          {target
            ? `Correct intake for Encounter #${target.id}`
            : "Register Patient and open Encounter"}
        </h2>
        <p className="muted">
          Fields marked <span className="required-mark">*</span> are required
          before an assessment can run. Notes are optional.
        </p>

        <form className="stack" onSubmit={handleSubmit}>
          {target ? (
            <dl className="facts">
              <div>
                <dt>Patient</dt>
                <dd>{target.patient.full_name}</dd>
              </div>
              <div>
                <dt>Age</dt>
                <dd>{target.patient.age}</dd>
              </div>
              <div>
                <dt>Sex</dt>
                <dd>{sexLabel(target.patient.sex)}</dd>
              </div>
              <div>
                <dt>Contact</dt>
                <dd>{target.patient.contact_phone}</dd>
              </div>
              <div>
                <dt>Arrived</dt>
                <dd>{formatInstant(target.arrived_at)}</dd>
              </div>
            </dl>
          ) : (
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
          )}

          <fieldset className="intake-fieldset">
            <legend>Intake</legend>
            <div className="intake-grid">
              <label className="span-all">
                Presenting complaint <span className="required-mark">*</span>
                <textarea
                  required
                  rows={3}
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
                Illness duration (hours){" "}
                <span className="required-mark">*</span>
                <input
                  type="number"
                  required
                  min={0}
                  max={8760}
                  step={0.5}
                  inputMode="decimal"
                  value={form.durationHours}
                  onChange={(event) =>
                    update("durationHours", event.target.value)
                  }
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
                  onChange={(event) =>
                    update("temperatureC", event.target.value)
                  }
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
                Blood pressure systolic{" "}
                <span className="required-mark">*</span>
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
                Blood pressure diastolic{" "}
                <span className="required-mark">*</span>
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
                  onChange={(event) =>
                    update("oxygenSaturation", event.target.value)
                  }
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

          <div className="row">
            <button type="submit" disabled={pending}>
              {pending
                ? "Saving…"
                : target
                  ? "Save correction"
                  : "Open Encounter"}
            </button>
            {target ? (
              <button type="button" className="secondary" onClick={reset}>
                Cancel correction
              </button>
            ) : null}
            {!target && savedEncounter ? (
              <>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => startCorrection(savedEncounter)}
                >
                  Correct this intake
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

      <section className="card">
        <h2>Recent Encounters</h2>
        <p className="muted">
          Intake is locked once the Encounter's Triage Assessment exists, which
          is as soon as the Encounter opens. This list is by arrival, not the
          Queue.
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
                  onClick={() => startCorrection(encounter)}
                >
                  Correct intake
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
