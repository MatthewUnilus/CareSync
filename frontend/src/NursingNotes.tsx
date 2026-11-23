import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type {
  NotePrefill,
  NoteTemplate,
  NursingNote,
  NursingNoteField,
  NursingNotePayload,
} from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
} from "./design";
import { formatInstant } from "./queueDisplay";
import { WardRoundTasks } from "./TaskList";

/**
 * Nursing notes for one Admission: a nurse writes a note from a template rather
 * than from a blank page, and the note starts with the patient's latest vitals
 * already filled in so the numbers the system already holds are not retyped.
 *
 * The templates are the server's fixed vocabulary (ADR 0013): this view asks for
 * them and builds the form from whatever fields come back, so adding a field is
 * a server change with no client change, and no clinical normal is computed here.
 * The vitals prefill is shown with its source, not applied silently — a nurse who
 * cannot see that the numbers came from the last observation will retype them
 * anyway. A note is append-only: correcting one writes a new note that points at
 * the note it corrects, and the corrected note stays in the record, marked.
 *
 * The component is embeddable rather than a page of its own: the ward board
 * mounts it against an Admission from the row, the same shape the Observation
 * chart is reached without a search (ticket 31).
 */
export default function NursingNotes({
  admissionId,
  title = "Nursing notes",
  onTasksRaised,
}: {
  admissionId: number;
  title?: string;
  /** Called after Tasks are raised from a round entry, so the board's counts refresh. */
  onTasksRaised?: () => Promise<void> | void;
}) {
  const [templates, setTemplates] = useState<NoteTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const [notes, setNotes] = useState<NursingNote[] | null>(null);
  const [notesError, setNotesError] = useState<string | null>(null);

  // The composer. `templateKey` is the chosen template, `values` its fields as
  // free text, and `prefill` the server's prefill for that template (with where
  // its values came from). `correcting` is the note being corrected, if any.
  const [templateKey, setTemplateKey] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [prefill, setPrefill] = useState<NotePrefill | null>(null);
  const [prefillLoading, setPrefillLoading] = useState(false);
  const [prefillError, setPrefillError] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<NursingNote | null>(null);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Every fetch takes the next token and, once it resolves, writes nothing
  // unless it is still the newest — so a slow reply for a previously chosen
  // template, a reply for a previous Admission, or one still in flight as this
  // view unmounts, can never land its values under another template's fields or
  // another patient's notes.
  const templatesRequestRef = useRef(0);
  const prefillRequestRef = useRef(0);
  const notesRequestRef = useRef(0);

  const loadTemplates = useCallback(async () => {
    const requestId = ++templatesRequestRef.current;
    setTemplatesError(null);
    try {
      const { templates: loaded } = await api.noteTemplates();
      if (templatesRequestRef.current !== requestId) {
        return;
      }
      setTemplates(loaded);
    } catch (caught) {
      if (templatesRequestRef.current !== requestId) {
        return;
      }
      setTemplatesError(errorText(caught));
    }
  }, []);

  const loadNotes = useCallback(async (id: number) => {
    const requestId = ++notesRequestRef.current;
    setNotesError(null);
    try {
      const { notes: loaded } = await api.admissionNotes(id);
      if (notesRequestRef.current !== requestId) {
        return;
      }
      setNotes(loaded);
    } catch (caught) {
      if (notesRequestRef.current !== requestId) {
        return;
      }
      setNotesError(errorText(caught));
    }
  }, []);

  // Clear the composer back to nothing: no template, no values, no prefill and
  // no correction. Retires any in-flight prefill so a late reply cannot refill a
  // composer that has since been reset.
  const resetComposer = useCallback(() => {
    prefillRequestRef.current += 1;
    setCorrecting(null);
    setTemplateKey(null);
    setValues({});
    setPrefill(null);
    setPrefillLoading(false);
    setPrefillError(null);
    setSaveError(null);
  }, []);

  // The templates are a global vocabulary, read once, and again on retry.
  useEffect(() => {
    void loadTemplates();
    return () => {
      templatesRequestRef.current += 1;
    };
  }, [loadTemplates]);

  // A change of Admission is a change of patient. Reset the composer so nothing
  // written or prefilled for the previous patient can survive under the new one,
  // even when this view is reused in place rather than remounted on the new id.
  useEffect(() => {
    resetComposer();
  }, [admissionId, resetComposer]);

  // Re-read the notes whenever the Admission changes. The cleanup retires any
  // in-flight fetch, so a reply that resolves after the Admission changed — or
  // after this view unmounted — is dropped rather than shown.
  useEffect(() => {
    void loadNotes(admissionId);
    return () => {
      notesRequestRef.current += 1;
    };
  }, [admissionId, loadNotes]);

  // Start a fresh note: pick the template, seed its fields blank, then ask the
  // server to prefill from the patient's latest observation. The prefill is kept
  // with its source so the view can name where the values came from.
  async function selectTemplate(key: string) {
    const template = templateFor(templates, key);
    setCorrecting(null);
    setSaveError(null);
    setPrefill(null);
    setPrefillError(null);
    setTemplateKey(key);
    setValues(template ? blankValues(template) : {});

    const requestId = ++prefillRequestRef.current;
    setPrefillLoading(true);
    try {
      const loaded = await api.admissionNotePrefill(admissionId, key);
      if (prefillRequestRef.current !== requestId) {
        return;
      }
      setPrefill(loaded);
      if (template) {
        setValues(seedValues(template, loaded.fields));
      }
    } catch (caught) {
      if (prefillRequestRef.current !== requestId) {
        return;
      }
      setPrefillError(errorText(caught));
    } finally {
      if (prefillRequestRef.current === requestId) {
        setPrefillLoading(false);
      }
    }
  }

  // Correcting a note seeds the composer from the note itself, so the nurse
  // amends what went wrong instead of retyping the whole note. The template is
  // fixed to the corrected note's own, and saving appends a linked note.
  function startCorrection(note: NursingNote) {
    // Corrections build their form from the template; without it the new note
    // would carry no fields. The button is disabled and the view says why in
    // this state, but guard here too so a correction cannot start empty.
    if (templates === null) {
      return;
    }
    prefillRequestRef.current += 1;
    const template = templateFor(templates, note.template_key);
    const seeded: Record<string, string> = {};
    for (const field of note.fields) {
      seeded[field.key] = field.value;
    }
    if (template) {
      for (const field of template.fields) {
        if (!(field.key in seeded)) {
          seeded[field.key] = "";
        }
      }
    }
    setCorrecting(note);
    setTemplateKey(note.template_key);
    setPrefill(null);
    setPrefillLoading(false);
    setPrefillError(null);
    setSaveError(null);
    setValues(seeded);
  }

  const selectedTemplate = templateFor(templates, templateKey);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const template = selectedTemplate;
    if (template === null) {
      setSaveError("Choose a template to write a note from.");
      return;
    }
    const fields: NursingNoteField[] = template.fields.map((field) => ({
      key: field.key,
      value: values[field.key] ?? "",
    }));
    const payload: NursingNotePayload = {
      template_key: template.key,
      // A correction points at the note it corrects; a fresh note points at
      // nothing. The link is one-directional, the server's to record.
      corrects_note_id: correcting !== null ? correcting.id : null,
      fields,
    };
    setSaving(true);
    setSaveError(null);
    try {
      await api.writeAdmissionNote(admissionId, payload);
      toast.success(correcting !== null ? "Correction saved." : "Note saved.");
      resetComposer();
      // Re-read so the new note comes back from the server, in time order with
      // the rest, rather than being reconstructed here.
      await loadNotes(admissionId);
    } catch (caught) {
      setSaveError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">{title}</h3>
      <p className={mutedTextClass}>
        A note is written from a template and starts with this patient&rsquo;s
        latest observation filled in, so the vitals are there to confirm or amend
        rather than to retype. The templates follow standard nursing
        documentation and are provisional: the hospital has not supplied its
        chart yet, so expect them to change, and the fields are free text. A
        correction is a new note that points at the one it corrects; the
        corrected note stays in the record.
      </p>

      {templatesError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {templatesError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void loadTemplates()}
            >
              Retry loading templates
            </Button>
          </footer>
        </section>
      ) : templates === null ? (
        <p className={mutedTextClass}>Loading note templates…</p>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={save}>
          <h4 className="text-body-semibold text-text-primary">
            {correcting !== null
              ? `Correct note #${correcting.id}`
              : "Write a note"}
          </h4>

          {correcting !== null ? (
            <p className={mutedTextClass}>
              Correcting the note by <bdi>{correcting.author.display_name}</bdi>{" "}
              recorded{" "}
              <time
                dateTime={correcting.recorded_at}
                className={figureClass}
              >
                {formatInstant(correcting.recorded_at)}
              </time>
              . Saving appends a new note that points at it; the original stays in
              the record and is shown as corrected.
            </p>
          ) : null}

          <Select
            label="Template"
            className="w-full sm:w-80"
            triggerClassName="min-h-11"
            placeholder="Choose a template"
            selectedKey={templateKey}
            isDisabled={correcting !== null}
            onSelectionChange={(key) => {
              if (typeof key === "string") {
                void selectTemplate(key);
              }
            }}
          >
            {templates.map((template) => (
              <SelectItem
                key={template.key}
                id={template.key}
                textValue={template.label}
              >
                {template.label}
              </SelectItem>
            ))}
          </Select>

          {prefillLoading ? (
            <p className={mutedTextClass}>Loading the latest vitals…</p>
          ) : prefillError !== null ? (
            <p className={noticeClass.error} role="alert">
              {prefillError}
            </p>
          ) : prefill !== null ? (
            <p className="text-body-2-regular text-text-secondary">
              {prefill.source_observation !== null ? (
                <>
                  Vitals prefilled from the observation taken{" "}
                  <time
                    dateTime={prefill.source_observation.taken_at}
                    className={figureClass}
                  >
                    {formatInstant(prefill.source_observation.taken_at)}
                  </time>{" "}
                  by <bdi>{prefill.source_observation.actor.display_name}</bdi>.
                  Confirm or amend before saving.
                </>
              ) : (
                "No values were prefilled for this template; enter them by hand."
              )}
            </p>
          ) : null}

          {selectedTemplate !== null ? (
            <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2">
              <legend className={sectionLabelClass}>
                {selectedTemplate.label}
              </legend>
              {selectedTemplate.fields.map((field) => {
                // The "from vitals" mark is shown only while the value still
                // matches the prefill, so an amended figure is not mislabelled.
                const fromVitals =
                  prefill !== null &&
                  prefill.fields[field.key] !== undefined &&
                  values[field.key] === prefill.fields[field.key];
                return (
                  <Textarea
                    key={field.key}
                    rows={2}
                    label={
                      fromVitals ? (
                        <>
                          {field.label}{" "}
                          <Chip
                            variant="caption"
                            color="blue"
                            className="align-middle"
                          >
                            from vitals
                          </Chip>
                        </>
                      ) : (
                        field.label
                      )
                    }
                    value={values[field.key] ?? ""}
                    isDisabled={saving || prefillLoading}
                    onChange={(next) =>
                      setValues((current) => ({
                        ...current,
                        [field.key]: next,
                      }))
                    }
                  />
                );
              })}
            </fieldset>
          ) : (
            <p className={mutedTextClass}>
              Choose a template to start a note.
            </p>
          )}

          {saveError !== null ? (
            <p className={noticeClass.error} role="alert">
              {saveError}
            </p>
          ) : null}

          <footer className="flex flex-wrap gap-2">
            <Button
              type="submit"
              className="min-h-11"
              disabled={saving || selectedTemplate === null || prefillLoading}
            >
              {saving
                ? "Saving…"
                : correcting !== null
                  ? "Save correction"
                  : "Save note"}
            </Button>
            {correcting !== null || templateKey !== null ? (
              <Button
                type="button"
                variant="secondary"
                className="min-h-11"
                disabled={saving}
                onClick={resetComposer}
              >
                Cancel
              </Button>
            ) : null}
          </footer>
        </form>
      )}

      <section className="flex flex-col gap-3">
        <h4 className={sectionLabelClass}>Recorded notes</h4>
        <p className="text-body-2-regular text-text-secondary">
          In time order, so the shift reads back front to back. A correction sits
          beside the note it corrects, which stays in the record and is marked.
        </p>

        {notesError !== null ? (
          <p className={noticeClass.error} role="alert">
            {notesError}
          </p>
        ) : null}

        {notes === null ? (
          notesError !== null ? null : (
            <p className={mutedTextClass}>Loading notes…</p>
          )
        ) : notes.length === 0 ? (
          <p className={mutedTextClass}>
            No nursing notes recorded for this admission yet.
          </p>
        ) : (
          <ol className="flex flex-col gap-4">
            {notes.map((note) => (
              <li
                key={note.id}
                className={cx(cardClass, "gap-2")}
              >
                <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <time
                    className={cx(
                      "text-body-semibold text-text-primary",
                      figureClass,
                    )}
                    dateTime={note.recorded_at}
                  >
                    {formatInstant(note.recorded_at)}
                  </time>
                  <small className="text-body-2-regular text-text-secondary">
                    by <bdi>{note.author.display_name}</bdi>
                  </small>
                  <Chip variant="caption" color="soft">
                    {labelForTemplate(templates, note.template_key)}
                  </Chip>
                  {note.corrects_note_id !== null ? (
                    <Chip variant="caption" color="neutral">
                      corrects note #{note.corrects_note_id}
                    </Chip>
                  ) : null}
                  {note.corrected_by_note_id !== null ? (
                    <Chip variant="bold" color="yellow">
                      corrected by note #{note.corrected_by_note_id}
                    </Chip>
                  ) : null}
                </header>

                <ul className="flex flex-wrap gap-x-6 gap-y-2">
                  {note.fields.map((field) => (
                    <li key={field.key} className="flex min-w-0 basis-56 flex-col gap-0.5">
                      <p className={sectionLabelClass}>
                        {labelForField(
                          templates,
                          note.template_key,
                          field.key,
                        )}
                      </p>
                      <p className="text-body-regular text-text-primary wrap-anywhere">
                        {field.value}
                      </p>
                    </li>
                  ))}
                </ul>

                {note.corrected_by_note_id === null ? (
                  <footer className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      className="min-h-11"
                      disabled={saving || templates === null}
                      onClick={() => startCorrection(note)}
                    >
                      Correct this note
                    </Button>
                    {templates === null ? (
                      <small className="text-body-2-regular text-text-secondary">
                        Correcting a note needs the note templates, which are not
                        available right now. Retry above.
                      </small>
                    ) : null}
                  </footer>
                ) : null}

                {note.template_key === "ward_round_entry" ? (
                  <WardRoundTasks
                    admissionId={note.admission_id}
                    noteId={note.id}
                    seedDescription={
                      note.fields.find((field) => field.key === "plan")?.value ??
                      ""
                    }
                    dueHint={
                      note.fields.find((field) => field.key === "review_due")
                        ?.value ?? ""
                    }
                    onTasksRaised={onTasksRaised}
                  />
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}

// The template a key names, or null. The client never invents a template: an
// unknown key falls back to the key itself in the label helpers below.
function templateFor(
  templates: NoteTemplate[] | null,
  key: string | null,
): NoteTemplate | null {
  if (key === null || templates === null) {
    return null;
  }
  return templates.find((template) => template.key === key) ?? null;
}

// The human label for a template, falling back to its key so a note is never
// rendered without a heading.
function labelForTemplate(
  templates: NoteTemplate[] | null,
  key: string,
): string {
  return templateFor(templates, key)?.label ?? key;
}

// The human label for a field, falling back to its key.
function labelForField(
  templates: NoteTemplate[] | null,
  templateKey: string,
  fieldKey: string,
): string {
  const template = templateFor(templates, templateKey);
  return template?.fields.find((field) => field.key === fieldKey)?.label ?? fieldKey;
}

function blankValues(template: NoteTemplate): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of template.fields) {
    values[field.key] = "";
  }
  return values;
}

function seedValues(
  template: NoteTemplate,
  prefilled: Record<string, string>,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of template.fields) {
    values[field.key] = prefilled[field.key] ?? "";
  }
  return values;
}
