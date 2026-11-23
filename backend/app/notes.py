"""Nursing notes and the Note Template vocabulary.

A nurse writes a Nursing Note from a Note Template rather than from a blank page,
and the note starts with the patient's latest vitals already in it. This module
owns both halves of that:

* the **template vocabulary** — the five templates are a fixed set of named
  fields defined here in code, served by ``GET /api/ward/note-templates``. Adding
  a field to a template is a code change with no schema change and no client
  change (ADR 0013), because the note stores one row per field rather than one
  column per field (``app.models.NursingNoteField``).
* the **prefill** — a new note is seeded from the patient's latest Observation,
  so the numbers the system already holds are there to confirm or amend rather
  than to retype. The prefill is visible: the free text names where each number
  came from and the route returns the source Observation beside it.

The templates are designed from standard nursing documentation practice, because
the hospital has not supplied its chart yet; they are expected to be revised once
the real forms arrive. Keep the field lists short: a template with twenty fields
will not be filled in.

Field values are free text. There is no controlled clinical terminology in scope,
so nothing here interprets a value (CONTEXT.md, "Nursing Note"; ADR 0013).

The functions that stage a note never commit: the route commits, so the note, its
fields and its single audit entry land in one transaction (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ward
from app.models import Admission, NursingNote, NursingNoteField, Observation, User
from app.schemas import (
    ActorResponse,
    NoteTemplateFieldResponse,
    NoteTemplateResponse,
    NursingNoteFieldPayload,
    NursingNoteFieldResponse,
    NursingNoteResponse,
)
from app.timeutils import as_utc, utc_now

#: The field key every template carries for the prefilled readings.
VITAL_SIGNS_KEY = "vital_signs"

#: The label for that field. "Latest readings" rather than "Vital signs": the
#: prefill carries pain and illness duration as well, which are not vital signs,
#: so the label names what is actually in the field. The key stays
#: ``vital_signs`` so the stored shape and the client contract do not move with
#: the wording.
VITAL_SIGNS_LABEL = "Latest readings"

#: The one template that may be written on a stay that has already been
#: discharged. A discharge summary records the stay and the state at leaving, so
#: it follows the discharge rather than being refused by it.
DISCHARGE_SUMMARY_KEY = "discharge_summary"

#: The template a Ward Round Entry is written from. A round entry is what raises
#: Tasks, so the key is named here and the Tasks module reads it rather than
#: repeating the string (ticket 33).
WARD_ROUND_ENTRY_KEY = "ward_round_entry"

UNKNOWN_TEMPLATE_DETAIL = "Unknown note template"

#: Raised when a supplied field key is not one the named template defines, so a
#: typo is refused rather than silently stored as a field no one can read back.
UNKNOWN_FIELD_DETAIL = "Unknown field for this note template"

#: Raised when a field key is supplied more than once: the note would otherwise
#: hold two rows for one field and read back ambiguously.
DUPLICATE_FIELD_DETAIL = "A note field key may appear only once"

#: Raised when a note omits a field its template defines. The stored shape is one
#: row per template field, so a missing key is refused rather than left absent; a
#: blank value is still allowed, so a free-text field remains optional to fill in.
MISSING_FIELD_DETAIL = "A note must carry every field of its template"

#: Raised when a correction names a template other than the corrected note's. A
#: correction restates the same document, so changing its shape would make the two
#: read as different things.
CORRECTION_TEMPLATE_MISMATCH_DETAIL = (
    "A correction must use the same template as the note it corrects"
)

NOTE_NOT_FOUND_DETAIL = "Note not found"
CORRECTION_OTHER_ADMISSION_DETAIL = (
    "A correction must reference a note on the same Admission"
)
ALREADY_CORRECTED_DETAIL = "This note has already been corrected"


@dataclass(frozen=True)
class NoteField:
    """One named field of a template: its key and the label a reader sees."""

    key: str
    label: str


@dataclass(frozen=True)
class NoteTemplate:
    """One template of the fixed vocabulary: a key, a label and its fields."""

    key: str
    label: str
    fields: tuple[NoteField, ...]


#: The five templates, in the order they are served. Each is a starting shape for
#: a common nursing document, with a short ``vital_signs`` field the prefill
#: lands in. The field sets are drawn from standard nursing documentation and are
#: expected to be revised once the hospital supplies its chart.
TEMPLATES: tuple[NoteTemplate, ...] = (
    NoteTemplate(
        key="shift_assessment",
        label="Shift Assessment",
        fields=(
            NoteField(key=VITAL_SIGNS_KEY, label=VITAL_SIGNS_LABEL),
            NoteField(key="general_condition", label="General condition"),
            NoteField(key="mobility", label="Mobility"),
            NoteField(key="skin", label="Skin integrity"),
            NoteField(key="pain", label="Pain"),
            NoteField(key="intake_output", label="Intake and output"),
        ),
    ),
    NoteTemplate(
        key=WARD_ROUND_ENTRY_KEY,
        label="Ward Round Entry",
        # The round entry is adjacent to the Intervention Record: one records what
        # was asked for, the other what was done. Its fields are kept easy to map
        # onto a Task (ticket 33), so ``plan`` and ``review_due`` name the work and
        # when it is wanted.
        fields=(
            NoteField(key=VITAL_SIGNS_KEY, label=VITAL_SIGNS_LABEL),
            NoteField(key="current_issue", label="Current issue"),
            NoteField(key="findings", label="Findings"),
            NoteField(key="plan", label="Plan"),
            NoteField(key="review_due", label="Review due"),
        ),
    ),
    NoteTemplate(
        key="intervention_record",
        label="Intervention Record",
        fields=(
            NoteField(key=VITAL_SIGNS_KEY, label=VITAL_SIGNS_LABEL),
            NoteField(key="intervention", label="Intervention"),
            NoteField(key="indication", label="Indication"),
            NoteField(key="response", label="Response"),
        ),
    ),
    NoteTemplate(
        key="handover_entry",
        label="Handover Entry",
        fields=(
            NoteField(key=VITAL_SIGNS_KEY, label=VITAL_SIGNS_LABEL),
            NoteField(key="situation", label="Situation"),
            NoteField(key="background", label="Background"),
            NoteField(key="current_state", label="Current state"),
            NoteField(key="watch", label="What to watch"),
        ),
    ),
    NoteTemplate(
        key="discharge_summary",
        label="Discharge Summary",
        fields=(
            NoteField(key=VITAL_SIGNS_KEY, label=VITAL_SIGNS_LABEL),
            NoteField(key="stay_summary", label="Stay summary"),
            NoteField(key="treatment_given", label="Treatment given"),
            NoteField(key="state_at_discharge", label="State at discharge"),
            NoteField(key="follow_up", label="Follow-up"),
        ),
    ),
)

_BY_KEY: dict[str, NoteTemplate] = {template.key: template for template in TEMPLATES}


def templates() -> tuple[NoteTemplate, ...]:
    """The whole template vocabulary, in the order it is served."""
    return TEMPLATES


def template_for(key: str) -> NoteTemplate | None:
    """The template a key names, or None when the vocabulary has no such key."""
    return _BY_KEY.get(key)


def resolve_template(key: str) -> NoteTemplate:
    """The template a key names, refusing an unknown key with a ``422``.

    The key names a member of a fixed vocabulary, so an unknown one is a bad
    request rather than a missing resource.
    """
    template = template_for(key)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{UNKNOWN_TEMPLATE_DETAIL}: {key}",
        )
    return template


def validate_fields(
    template: NoteTemplate, fields: list[NursingNoteFieldPayload]
) -> None:
    """Refuse a field set that is not exactly the template's fields.

    A template is a vocabulary, not a form with validation, so the *values* are
    never checked — an empty string is a legitimate value, which keeps a
    free-text field optional to fill in. The *keys* are checked so the stored
    shape stays stable: exactly one row per template field, no more and no fewer.
    An unknown key is a typo, a repeated key would store two rows for one field,
    and a missing key would leave the note a different shape from its template.
    """
    allowed = [field.key for field in template.fields]
    allowed_set = set(allowed)
    seen: set[str] = set()
    for field in fields:
        if field.key not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{UNKNOWN_FIELD_DETAIL}: {field.key}",
            )
        if field.key in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{DUPLICATE_FIELD_DETAIL}: {field.key}",
            )
        seen.add(field.key)
    missing = [key for key in allowed if key not in seen]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{MISSING_FIELD_DETAIL}: {', '.join(missing)}",
        )


def render_vital_signs(observation: Observation) -> str:
    """The latest Observation as labelled free text, with its source stamped.

    The numbers are exactly the recorded values, each labelled — pain and illness
    duration are included, so the text is a set of readings rather than only
    clinical vital signs — and the text says when the set was taken and who took
    it. Keeping the stamp in the text means the provenance travels with the note
    once it is saved, not only in the response that offered the prefill
    (CONTEXT.md, "Observation"; ADR 0010: the values are never altered).
    """
    readings = (
        ("Temperature", f"{observation.temperature_c} C"),
        ("Heart rate", f"{observation.heart_rate_bpm} bpm"),
        ("Respiratory rate", f"{observation.respiratory_rate_bpm} /min"),
        (
            "Blood pressure",
            f"{observation.systolic}/{observation.diastolic} mmHg",
        ),
        ("Oxygen saturation", f"{observation.oxygen_saturation_percent} %"),
        ("Pain", f"{observation.pain_level}/10"),
        ("Illness duration", f"{observation.illness_duration_hours} h"),
    )
    body = ", ".join(f"{label} {value}" for label, value in readings)
    taken_at = as_utc(observation.taken_at).isoformat()
    return f"{body} (recorded {taken_at} by {observation.actor.display_name})"


def prefill(
    session: Session, admission: Admission, template: NoteTemplate
) -> tuple[dict[str, str], Observation | None]:
    """The values to start a note with, and the Observation they came from.

    A Patient's Observations are one time series across every visit and stay
    (ADR 0008), so the prefill reads the Patient's most recent set, exactly as
    the Ward Board shows it. When nothing is charted the values are empty and the
    source is None, so an empty prefill is never mistaken for a set of zeroes.
    Only the ``vital_signs`` field is prefilled, and only when the template has
    one.
    """
    observation = ward.latest_observation(session, admission)
    if observation is None:
        return {}, None
    values: dict[str, str] = {}
    if any(field.key == VITAL_SIGNS_KEY for field in template.fields):
        values[VITAL_SIGNS_KEY] = render_vital_signs(observation)
    return values, observation


def stage_note(
    session: Session,
    *,
    admission: Admission,
    actor: User,
    template: NoteTemplate,
    fields: list[NursingNoteFieldPayload],
    corrects: NursingNote | None = None,
) -> NursingNote:
    """Build one Nursing Note and its fields, and add it, without committing.

    ``corrects`` is the note this one corrects on a correction, or None on an
    original. The rows are added in template order so they read back in the
    template's order; the caller commits, so the note, its fields and its audit
    entry land in one transaction.
    """
    note = NursingNote(
        admission=admission,
        template_key=template.key,
        author=actor,
        recorded_at=utc_now(),
        corrects=corrects,
    )
    for field in fields:
        note.fields.append(NursingNoteField(key=field.key, value=field.value))
    session.add(note)
    return note


def corrected_by(session: Session, note: NursingNote) -> int | None:
    """The id of the note that corrects ``note``, or None.

    The link is one-directional, so this is derived rather than stored: the
    corrected note is never edited. At most one correction points at a note,
    which the route enforces, so the answer is a single id.
    """
    return session.scalar(
        select(NursingNote.id)
        .where(NursingNote.corrects_note_id == note.id)
        .order_by(NursingNote.id)
        .limit(1)
    )


def notes_for_admission(session: Session, admission: Admission) -> list[NursingNote]:
    """One Admission's notes in time order, oldest first, so a shift reads back."""
    return list(
        session.scalars(
            select(NursingNote)
            .where(NursingNote.admission_id == admission.id)
            .order_by(NursingNote.recorded_at, NursingNote.id)
        ).all()
    )


def note_response(
    session: Session, note: NursingNote, *, corrected_by_note_id: int | None = None
) -> NursingNoteResponse:
    """Render one note, deriving the note that corrects it unless supplied.

    The caller may pass ``corrected_by_note_id`` when it already holds the whole
    admission's notes, so a list is rendered without a query per note.
    """
    return _render(
        note,
        corrected_by_note_id=(
            corrected_by(session, note)
            if corrected_by_note_id is None
            else corrected_by_note_id
        ),
    )


def notes_response(session: Session, admission: Admission) -> list[NursingNoteResponse]:
    """Render one Admission's notes in time order, oldest first."""
    notes = notes_for_admission(session, admission)
    corrections: dict[int, int] = {}
    for note in notes:
        if note.corrects_note_id is not None:
            corrections.setdefault(note.corrects_note_id, note.id)
    return [
        _render(note, corrected_by_note_id=corrections.get(note.id))
        for note in notes
    ]


def _ordered_fields(note: NursingNote) -> list[NursingNoteField]:
    """A note's fields in its template's order, with any stray field last.

    A note written before a template was revised may carry a key the current
    template no longer defines; it is still returned, after the known fields, so
    a revision never hides a value that was recorded.
    """
    stored = list(note.fields)
    template = template_for(note.template_key)
    if template is None:
        return stored
    order = {field.key: index for index, field in enumerate(template.fields)}
    return sorted(stored, key=lambda field: (order.get(field.key, len(order)), field.id))


def _render(
    note: NursingNote, *, corrected_by_note_id: int | None
) -> NursingNoteResponse:
    return NursingNoteResponse(
        id=note.id,
        admission_id=note.admission_id,
        template_key=note.template_key,
        author=ActorResponse(
            id=note.author.id,
            display_name=note.author.display_name,
        ),
        recorded_at=note.recorded_at,
        corrects_note_id=note.corrects_note_id,
        corrected_by_note_id=corrected_by_note_id,
        fields=[
            NursingNoteFieldResponse(key=field.key, value=field.value)
            for field in _ordered_fields(note)
        ],
    )


def template_responses() -> list[NoteTemplateResponse]:
    """The vocabulary as the API serves it, keys and labels only."""
    return [
        NoteTemplateResponse(
            key=template.key,
            label=template.label,
            fields=[
                NoteTemplateFieldResponse(key=field.key, label=field.label)
                for field in template.fields
            ],
        )
        for template in TEMPLATES
    ]
