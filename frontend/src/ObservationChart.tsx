import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type { Observation, ObservationReading } from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
  tableCaptionClass,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableRowClass,
} from "./design";
import { ObservationFields } from "./IntakeFields";
import {
  buildObservationPayload,
  emptyIntakeFormValues,
  validateObservationForm,
} from "./intakeForm";
import type { IntakeFormValues, ObservationFieldErrors } from "./intakeForm";
import { formatInstant } from "./queueDisplay";

/**
 * The Observation chart: one Patient's vital signs as a time series.
 *
 * Each set of vitals is listed newest first, beside the set that preceded it, so
 * the direction of travel is visible without reading back through the record
 * (ADR 0008). The time a set was taken and the actor who took it are shown with
 * it. A reading outside its reference range is marked as abnormal, and the mark
 * is display only: nothing is scored, escalated or reordered, and no aggregate
 * early-warning figure is computed (ADR 0010). The client renders the abnormal
 * mark from the server's `abnormal_fields`; it never re-derives the thresholds,
 * so the reference ranges live in exactly one place.
 *
 * The component is embeddable rather than a page of its own: a ward board
 * reaches it without a search (ticket 31), and Patient history embeds it for the
 * Patient already selected. When a subject to chart against is supplied — an
 * Encounter or an Admission — the chart also carries the form that writes a new
 * set, which the server stores as an append-only Observation.
 */
export default function ObservationChart({
  patientId,
  encounterId,
  admissionId,
  title = "Observation chart",
}: {
  patientId: number;
  /** The Encounter a newly charted set attaches to. */
  encounterId?: number;
  /** The Admission a newly charted set attaches to. */
  admissionId?: number;
  title?: string;
}) {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [form, setForm] = useState<IntakeFormValues>(emptyIntakeFormValues);
  const [fieldErrors, setFieldErrors] = useState<ObservationFieldErrors>({});
  const [pending, setPending] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  // The chart the view is allowed to show. Every fetch takes the next token and,
  // once it resolves, writes nothing unless it is still the newest — so a slow
  // reply for a previous Patient, or one still in flight as this chart unmounts,
  // can never land its readings under another Patient's heading.
  const requestIdRef = useRef(0);

  const load = useCallback(async (id: number) => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    try {
      const { observations } = await api.patientObservations(id);
      if (requestIdRef.current !== requestId) {
        return;
      }
      setObservations(observations);
      setLoadError(null);
    } catch (caught) {
      if (requestIdRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, []);

  // Re-read the chart whenever the Patient changes. The cleanup retires any
  // in-flight fetch, so a reply that resolves after the Patient changed — or
  // after this chart unmounted — is dropped rather than shown.
  useEffect(() => {
    void load(patientId);
    return () => {
      requestIdRef.current += 1;
    };
  }, [patientId, load]);

  // Start the form blank whenever the Patient or the charting subject changes,
  // so a value charted for one patient or visit can never be posted against
  // another.
  useEffect(() => {
    setForm(emptyIntakeFormValues());
    setFieldErrors({});
    setServerError(null);
  }, [patientId, encounterId, admissionId]);

  function update(next: Partial<IntakeFormValues>) {
    setForm((current) => ({ ...current, ...next }));
  }

  // Charting writes against an encounter or an admission, never both. A caller
  // that supplies both is a mistake, not a choice to make silently: the chart
  // refuses to pick one and says so. With no subject supplied the chart is
  // read-only and carries no form.
  const subjectError =
    encounterId != null && admissionId != null
      ? "Supply either an encounter or an admission to chart against, never both."
      : null;
  const subject: "encounter" | "admission" | null =
    subjectError !== null
      ? null
      : encounterId != null
        ? "encounter"
        : admissionId != null
          ? "admission"
          : null;

  async function chartNewSet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Without a subject there is nothing to chart against: never report success.
    if (subject === null) {
      return;
    }
    const errors = validateObservationForm(form);
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setServerError(null);
    setPending(true);
    try {
      const payload = buildObservationPayload(form);
      if (subject === "encounter" && encounterId != null) {
        await api.chartEncounterObservation(encounterId, payload);
      } else if (subject === "admission" && admissionId != null) {
        await api.chartAdmissionObservation(admissionId, payload);
      }
      toast.success("Observation charted.");
      setForm(emptyIntakeFormValues());
      // Re-read so the new set, and every earlier set's "previous", come back
      // from the server rather than being reconstructed here.
      await load(patientId);
    } catch (caught) {
      setServerError(errorText(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">{title}</h3>
      <p className={mutedTextClass}>
        Each set of vitals, newest first, beside the set before it. Ranges are
        the published adult reference ranges: a reading outside its range is
        marked for display only, and nothing is scored, escalated or reordered.
        Where the adult ranges do not apply — a child — no reading is marked.
      </p>

      {!loading &&
      observations.length > 0 &&
      observations[0].reference_range_applies === false ? (
        <p className={sectionLabelClass}>
          The adult reference ranges do not apply to this patient, so no reading
          is marked.
        </p>
      ) : null}

      {loading ? (
        <p className={mutedTextClass}>Loading observations…</p>
      ) : loadError !== null ? (
        <p className={noticeClass.error} role="alert">
          {loadError}
        </p>
      ) : observations.length === 0 ? (
        <p className={mutedTextClass}>
          No observations charted for this patient yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {observations.map((observation) => (
            <li key={observation.id} className={cardClass}>
              <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <time
                  className={cx(
                    "text-body-semibold text-text-primary",
                    figureClass,
                  )}
                  dateTime={observation.taken_at}
                >
                  {formatInstant(observation.taken_at)}
                </time>
                <small className="text-body-2-regular text-text-secondary">
                  taken by <bdi>{observation.actor.display_name}</bdi>
                </small>
                {observation.encounter_id != null ||
                observation.admission_id != null ? (
                  <small className="text-body-2-regular text-text-secondary">
                    {observation.encounter_id != null
                      ? `encounter #${observation.encounter_id}`
                      : `admission #${observation.admission_id}`}
                  </small>
                ) : null}
              </header>

              <table className={tableClass}>
                <caption className={tableCaptionClass}>
                  Observation #{observation.id}, readings beside the previous set
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className={tableHeadCellClass}>
                      Reading
                    </th>
                    <th scope="col" className={tableHeadCellClass}>
                      This set
                    </th>
                    <th scope="col" className={tableHeadCellClass}>
                      Previous
                      {observation.previous !== null &&
                      observation.previous.taken_at ? (
                        <time
                          className="block text-caption-1-regular font-normal text-text-secondary"
                          dateTime={observation.previous.taken_at}
                        >
                          {formatInstant(observation.previous.taken_at)}
                        </time>
                      ) : null}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {readingsFor(observation).map((reading) => (
                    <tr key={reading.key} className={tableRowClass}>
                      <th scope="row" className={tableCellClass}>
                        {reading.label}
                      </th>
                      <td className={tableCellClass}>
                        <strong
                          className={cx(figureClass, "text-text-primary")}
                        >
                          {reading.value}
                        </strong>
                        {observation.reference_range_applies !== false &&
                        reading.abnormal ? (
                          <Chip
                            variant="caption"
                            color="yellow"
                            className="ms-2 align-middle"
                          >
                            Abnormal
                          </Chip>
                        ) : null}
                      </td>
                      <td className={cx(tableCellClass, mutedTextClass)}>
                        {reading.previous != null ? (
                          <small
                            className={cx(figureClass, "text-body-regular")}
                          >
                            {reading.previous}
                          </small>
                        ) : (
                          <small className={sectionLabelClass}>
                            first reading
                          </small>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {observation.notes ? (
                <p className="text-body-regular text-text-primary wrap-anywhere">
                  {observation.notes}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {subjectError !== null ? (
        <p className={noticeClass.error} role="alert">
          {subjectError}
        </p>
      ) : null}

      {subject !== null ? (
        <form className="flex flex-col gap-4" onSubmit={chartNewSet}>
          <h4 className="text-body-semibold text-text-primary">
            Chart a new set of vitals
          </h4>
          {serverError !== null ? (
            <p className={noticeClass.error} role="alert">
              {serverError}
            </p>
          ) : null}
          <ObservationFields
            form={form}
            onChange={update}
            errors={fieldErrors}
          />
          <footer className="flex flex-wrap gap-2">
            <Button type="submit" className="min-h-11" disabled={pending}>
              {pending ? "Charting…" : "Chart this set"}
            </Button>
          </footer>
          <p className={mutedTextClass}>
            A charted set is unchangeable; a correction is a new set, never an
            edit.
          </p>
        </form>
      ) : null}
    </section>
  );
}

interface ReadingRow {
  key: string;
  label: string;
  value: string;
  previous: string | null;
  abnormal: boolean;
}

// The names the server uses to mark a reading abnormal. A blood pressure is
// marked whole or per figure depending on where the server draws the line, so
// the mark is read from any of the three names rather than assuming one.
function isMarked(fields: string[], ...names: string[]): boolean {
  return names.some((name) => fields.includes(name));
}

function readingValue(reading: ObservationReading) {
  return {
    pain: `${reading.pain_level} / 10`,
    duration: `${reading.illness_duration_hours} h`,
    temperature: `${reading.temperature_c} °C`,
    heartRate: `${reading.heart_rate_bpm} bpm`,
    respiratoryRate: `${reading.respiratory_rate_bpm} bpm`,
    bloodPressure: `${reading.blood_pressure.systolic} / ${reading.blood_pressure.diastolic} mmHg`,
    oxygenSaturation: `${reading.oxygen_saturation_percent}%`,
  };
}

/**
 * One Observation as rows of label, current value and previous value. The
 * abnormal mark is read from the server's `abnormal_fields`; the client never
 * decides what is abnormal.
 */
function readingsFor(observation: Observation): ReadingRow[] {
  const fields = observation.abnormal_fields;
  const current = readingValue(observation);
  const previous = observation.previous
    ? readingValue(observation.previous)
    : null;

  return [
    {
      key: "pain",
      label: "Pain level",
      value: current.pain,
      previous: previous?.pain ?? null,
      abnormal: isMarked(fields, "pain_level"),
    },
    {
      key: "duration",
      label: "Illness duration",
      value: current.duration,
      previous: previous?.duration ?? null,
      abnormal: isMarked(fields, "illness_duration_hours"),
    },
    {
      key: "temperature",
      label: "Temperature",
      value: current.temperature,
      previous: previous?.temperature ?? null,
      abnormal: isMarked(fields, "temperature_c"),
    },
    {
      key: "heart-rate",
      label: "Heart rate",
      value: current.heartRate,
      previous: previous?.heartRate ?? null,
      abnormal: isMarked(fields, "heart_rate_bpm"),
    },
    {
      key: "respiratory-rate",
      label: "Respiratory rate",
      value: current.respiratoryRate,
      previous: previous?.respiratoryRate ?? null,
      abnormal: isMarked(fields, "respiratory_rate_bpm"),
    },
    {
      key: "blood-pressure",
      label: "Blood pressure",
      value: current.bloodPressure,
      previous: previous?.bloodPressure ?? null,
      abnormal: isMarked(fields, "blood_pressure", "systolic", "diastolic"),
    },
    {
      key: "oxygen-saturation",
      label: "Oxygen saturation",
      value: current.oxygenSaturation,
      previous: previous?.oxygenSaturation ?? null,
      abnormal: isMarked(fields, "oxygen_saturation_percent"),
    },
  ];
}
