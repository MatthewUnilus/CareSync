import re
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.admissions import AdmissionStatus
from app.audit_actions import AuditAction
from app.departures import EncounterStatus
from app.models import Role, Sex
from app.timeutils import as_utc

_NAME = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
_TEXT = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
_OPTIONAL_TEXT = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
]
_EMAIL = Annotated[str, StringConstraints(strip_whitespace=True, max_length=320)]
_HOSPITAL_NUMBER = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=64)
]
#: Where an Admission is: a ward and a bed or location, both required and
#: non-blank. The lengths match the model's columns so a stored value is never
#: silently truncated.
_WARD = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
_BED = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
#: A note template key and the key of one of its fields: short snake_case
#: identifiers, matching the vocabulary in ``app.notes``. The key is stored as
#: written; the vocabulary, not the schema, decides which keys exist (ADR 0013).
_NOTE_KEY = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
#: A note field's value: free text. There is no controlled clinical terminology
#: in scope, so a value is never validated as a coded concept; it may be blank.
_NOTE_VALUE = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000)
]

# SQLite round-trips aware timestamps as naive; responses always speak UTC.
UtcDatetime = Annotated[datetime, BeforeValidator(as_utc)]


class LoginRequest(BaseModel):
    email: str
    password: str


class UnlockRequest(BaseModel):
    """Resume a locked session: the credential that signs the holder back in.

    Only the password is asked for. The session is already named by the cookie,
    so asking for the email would imply the lock starts a new sign-in, which it
    deliberately does not.
    """

    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: Role


class RoleDescriptor(BaseModel):
    value: Role
    label: str


class RolesResponse(BaseModel):
    roles: list[RoleDescriptor]


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class PatientRegistrationRequest(BaseModel):
    full_name: _NAME
    age: int = Field(ge=0, le=120)
    sex: Sex
    contact_phone: Annotated[str, StringConstraints(max_length=40)]
    contact_email: _EMAIL | None = None
    hospital_number: _HOSPITAL_NUMBER | None = None

    @field_validator("contact_phone")
    @classmethod
    def _phone_has_digits(cls, value: str) -> str:
        value = value.strip()
        if len(re.sub(r"\D", "", value)) < 5:
            raise ValueError("contact_phone must contain at least 5 digits")
        return value

    @field_validator("contact_email")
    @classmethod
    def _email_is_shaped(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("contact_email must be an email address")
        return value

    @field_validator("hospital_number")
    @classmethod
    def _blank_hospital_number_is_absent(cls, value: str | None) -> str | None:
        """A blank or whitespace-only number is absent, not an empty one.

        The number is optional, so a walk-in with none is registrable; an empty
        field must read as "no number" rather than a number that is the empty
        string, which would be a key of its own.
        """
        return value or None


class HospitalNumberRequest(BaseModel):
    """The hospital number to attach to an existing, numbered-less Patient.

    Blank or whitespace-only input is normalised to absent, exactly as in
    registration; the attach route then refuses it, because attaching "no
    number" is not a change. A number is optional at registration but required
    to attach one later.
    """

    hospital_number: _HOSPITAL_NUMBER | None = None

    @field_validator("hospital_number")
    @classmethod
    def _blank_hospital_number_is_absent(cls, value: str | None) -> str | None:
        return value or None


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    age: int
    sex: Sex
    contact_phone: str
    contact_email: str | None
    hospital_number: str | None = None
    registered_at: UtcDatetime


class BloodPressure(BaseModel):
    systolic: int = Field(ge=50, le=300)
    diastolic: int = Field(ge=20, le=200)

    @model_validator(mode="after")
    def _systolic_above_diastolic(self) -> "BloodPressure":
        if self.systolic <= self.diastolic:
            raise ValueError("systolic must be greater than diastolic")
        return self


class ObservationPayload(BaseModel):
    """One set of vital signs, as charted against a visit or a stay.

    The bounds are the intake bounds, unchanged: pain 1-10, illness duration
    0-8760 hours, temperature 30-45, heart rate 20-300, respiratory rate 0-80,
    systolic 50-300, diastolic 20-200 with systolic greater than diastolic, and
    saturation 50-100. ``IntakePayload`` extends this with the reason for the
    visit, so there is one definition of the bounds rather than two that could
    drift.

    An unknown key is refused rather than ignored: a misspelled reading would
    otherwise be silently dropped and the client left believing it was charted.
    ``extra='forbid'`` turns that into a ``422``.
    """

    model_config = ConfigDict(extra="forbid")

    pain_level: int = Field(ge=1, le=10)
    illness_duration_hours: float = Field(ge=0, le=8760)
    temperature_c: float = Field(ge=30, le=45)
    heart_rate_bpm: int = Field(ge=20, le=300)
    respiratory_rate_bpm: int = Field(ge=0, le=80)
    blood_pressure: BloodPressure
    oxygen_saturation_percent: int = Field(ge=50, le=100)
    notes: _OPTIONAL_TEXT | None = None

    @field_validator("notes")
    @classmethod
    def _blank_notes_are_absent(cls, value: str | None) -> str | None:
        return value or None


class IntakePayload(ObservationPayload):
    """The full intake a visit is opened with: the reason and the first vitals.

    A visit no longer holds vital signs; every set of vitals is its own
    Observation (ADR 0008). Opening a visit with this full payload records the
    reason on the Encounter and the first Observation in the same transaction.
    Its readings are validated by ``ObservationPayload``, so the chart and the
    intake accept identical bounds.
    """

    presenting_complaint: _TEXT


class VisitReasonPayload(BaseModel):
    """The reason for a visit, as sent when a visit is opened or corrected.

    Vital signs and notes are refused rather than ignored: before the Observation
    chart (ticket 30) a visit has nowhere to keep them, and silently accepting a
    posted set of vitals would let the client believe they were recorded.
    ``extra='forbid'`` turns that into a ``422``.
    """

    model_config = ConfigDict(extra="forbid")

    presenting_complaint: _TEXT


class EncounterCreateRequest(BaseModel):
    """Open a visit: the Patient, and either a reason or a full intake.

    The reason travels under the ``intake`` wrapper the client already sends.
    It is reason-only for a visit opened from the reason alone, and the full
    ``IntakePayload`` when the first set of vitals is captured at the same
    time. A partial set matches neither shape and is refused, so a posted set
    of vitals is never silently dropped to a reason-only visit.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(gt=0)
    intake: VisitReasonPayload | IntakePayload


class ActorResponse(BaseModel):
    """A User as an actor, wherever an action's performer is shown.

    The same shape serves an Audit Entry's ``actor``, so a name reads identically
    wherever it appears.
    """

    id: int
    display_name: str


class EncounterResponse(BaseModel):
    """One Encounter, open or ended.

    ``status`` is derived from ``ended_at`` rather than stored: open while the
    instant is null, ended once it is set. An ended Encounter is still returned
    in full, with its Patient and the reason for the visit.
    """

    id: int
    arrived_at: UtcDatetime
    ended_at: UtcDatetime | None = None
    status: EncounterStatus
    patient: PatientResponse
    reason_for_visit: str


class EncounterListResponse(BaseModel):
    encounters: list[EncounterResponse]


class AdmissionCreateRequest(BaseModel):
    """Admit a Patient: where they are, and the visit that led here.

    ``encounter_id`` is optional and nullable: a direct admission has no prior
    visit, while an admission from a visit links the Encounter so the two read
    as one history. An unknown key is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(gt=0)
    ward: _WARD
    bed: _BED
    encounter_id: int | None = Field(default=None, gt=0)


class AdmissionMoveRequest(BaseModel):
    """Move a stay to another ward and bed. Both are required and non-blank."""

    model_config = ConfigDict(extra="forbid")

    ward: _WARD
    bed: _BED


class NursingNoteFieldPayload(BaseModel):
    """One named field of a note to write, its value free text.

    The key is checked by the route against the named template; the value is
    stored as written, with no coded meaning and no clinical validation (ADR
    0013). An unknown key in the object is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    key: _NOTE_KEY
    value: _NOTE_VALUE


class NursingNoteCreateRequest(BaseModel):
    """Write a note against an Admission from a template.

    ``template_key`` names one of the fixed templates. ``fields`` carry the note's
    field values, one per template field. ``corrects_note_id`` is null on an
    original and names the note this one corrects on a correction; the corrected
    note is left untouched. An unknown key is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    template_key: _NOTE_KEY
    fields: list[NursingNoteFieldPayload]
    corrects_note_id: int | None = Field(default=None, gt=0)


class AdmissionResponse(BaseModel):
    """One Admission, open or discharged.

    ``status`` is derived from ``discharged_at`` rather than stored: open while
    the instant is null, discharged once it is set. A discharged Admission is
    still returned in full, with its Patient and the Encounter it came from.
    """

    id: int
    patient: PatientResponse
    ward: str
    bed: str
    admitted_at: UtcDatetime
    discharged_at: UtcDatetime | None = None
    encounter_id: int | None = None
    status: AdmissionStatus


class AdmissionListResponse(BaseModel):
    admissions: list[AdmissionResponse]


class NoteTemplateFieldResponse(BaseModel):
    """One field of a note template: its key and the label a reader sees."""

    key: str
    label: str


class NoteTemplateResponse(BaseModel):
    """One template of the fixed vocabulary, served to build a note from.

    The definitions live in code (ADR 0013), so this is a plain read of the
    vocabulary: a change to a template field needs no schema change here and no
    client change.
    """

    key: str
    label: str
    fields: list[NoteTemplateFieldResponse]


class NoteTemplatesResponse(BaseModel):
    """The whole Note Template vocabulary."""

    templates: list[NoteTemplateResponse]


class NotePrefillSourceResponse(BaseModel):
    """The Observation a note's prefilled values came from, so the source shows.

    The nurse who cannot see where the numbers came from would retype them, so
    the instant the set was taken and the Clinical user who took it travel with
    the prefill.
    """

    taken_at: UtcDatetime
    actor: ActorResponse


class NotePrefillResponse(BaseModel):
    """The values to start a note with, and where they came from.

    ``fields`` maps a template field key to the prefilled free text; it holds the
    ``vital_signs`` field drawn from the patient's latest Observation, or is
    empty when none is charted. ``source_observation`` is the Observation the
    values came from, or null when there was none. The prefill is a starting
    point, never a stored interpretation: the nurse confirms or amends it and the
    values are written into the note as ordinary free text.
    """

    fields: dict[str, str]
    source_observation: NotePrefillSourceResponse | None = None


class NursingNoteFieldResponse(BaseModel):
    """One named field of a note, its value as written."""

    key: str
    value: str


class NursingNoteResponse(BaseModel):
    """One Nursing Note, as written and read back.

    ``author`` is a shared actor shape, so an author reads the same wherever
    shown. ``corrects_note_id`` names the note this one corrects, or null on an
    original; ``corrected_by_note_id`` names the note that corrects this one, or
    null, derived at read time so the corrected note is never edited. ``fields``
    is in template order.
    """

    id: int
    admission_id: int
    template_key: str
    author: ActorResponse
    recorded_at: UtcDatetime
    corrects_note_id: int | None = None
    corrected_by_note_id: int | None = None
    fields: list[NursingNoteFieldResponse]


class NursingNoteListResponse(BaseModel):
    """One Admission's notes in time order, oldest first."""

    notes: list[NursingNoteResponse]


class PatientSearchResponse(BaseModel):
    """Patients matching a search fragment.

    A discovery result, not an identity decision: several records may come
    back for one query, and the caller chooses. ``app.patients`` documents the
    identity rule — a hospital number when one is present, otherwise the whole
    name together with the whole phone — and that rule is untouched here: the
    search merely matches part of a name, a contact number or a hospital number.
    """

    patients: list[PatientResponse]


class PatientHistoryResponse(BaseModel):
    """One Patient's Encounters over time, oldest first.

    Each Encounter is rendered exactly as anywhere else, so a visit reads the
    same in a history as it does from a lookup.
    """

    patient: PatientResponse
    encounters: list[EncounterResponse]


class ObservationReadings(BaseModel):
    """The readings of one Observation, with the instant they were taken.

    This is the shape ``previous`` carries: a reading's preceding value and the
    time it was taken, so the chart can show the direction of travel and compare
    the two instants without reading back to the row.
    """

    taken_at: UtcDatetime
    pain_level: int
    illness_duration_hours: float
    temperature_c: float
    heart_rate_bpm: int
    respiratory_rate_bpm: int
    blood_pressure: BloodPressure
    oxygen_saturation_percent: int
    notes: str | None


class ObservationResponse(BaseModel):
    """One set of vitals, as read back from a Patient's chart.

    Exactly one of ``encounter_id`` and ``admission_id`` is set. ``taken_at`` is
    the server instant the reading was charted and ``actor`` is the Clinical
    user who took it. ``abnormal_fields`` names each reading outside its adult
    resting reference interval, for display only (ADR 0010): the values are
    returned unchanged and nothing is scored. ``reference_range_applies`` is
    false for a patient under 18, whose readings are not marked against the
    adult intervals; ``reference_range_note`` is the note the interface shows in
    that case and null when the ranges apply. ``previous`` is the preceding set
    of readings for the same Patient, or null when this is the first.
    """

    id: int
    encounter_id: int | None
    admission_id: int | None
    taken_at: UtcDatetime
    actor: ActorResponse
    pain_level: int
    illness_duration_hours: float
    temperature_c: float
    heart_rate_bpm: int
    respiratory_rate_bpm: int
    blood_pressure: BloodPressure
    oxygen_saturation_percent: int
    notes: str | None
    abnormal_fields: list[str]
    reference_range_applies: bool
    reference_range_note: str | None
    previous: ObservationReadings | None


class PatientObservationsResponse(BaseModel):
    """One Patient's Observation chart, newest first.

    An empty chart returns an empty list rather than a row of zeros.
    """

    observations: list[ObservationResponse]


class AuditEntryResponse(BaseModel):
    """One attributable record of a clinical mutation.

    The subject ids are nullable because the actions do not all reach the same
    subjects: registration names only a Patient, while opening an Encounter also
    names that Encounter. ``actor`` is a shared shape, so an actor reads the same
    wherever it appears. ``action`` is the machine key the log filters on;
    ``action_label`` is its human read, computed server-side beside the enum so
    the client holds no copy of the mapping.
    """

    id: int
    action: AuditAction
    action_label: str
    detail: str | None
    recorded_at: UtcDatetime
    actor: ActorResponse
    patient_id: int | None
    encounter_id: int | None
    admission_id: int | None = None


class AuditLogResponse(BaseModel):
    """The log oldest-first, optionally narrowed to one Encounter."""

    entries: list[AuditEntryResponse]


class DailyVisitsReportResponse(BaseModel):
    """One UTC day's arrival volume, end-of-visit throughput, and backlog."""

    day: date
    starts_at: UtcDatetime
    ends_at: UtcDatetime
    volume: int
    throughput: int
    awaiting: int


class PerformanceEntryResponse(BaseModel):
    encounter_id: int
    arrived_at: UtcDatetime
    ended_at: UtcDatetime
    waiting_seconds: int


class PerformanceReportResponse(BaseModel):
    completed: int
    average_waiting_seconds: float
    entries: list[PerformanceEntryResponse]


class WardBoardEntryResponse(BaseModel):
    """One open Admission on the Ward Board, with its outstanding work.

    The Admission fields are inlined so a board row is a single object, matching
    ``AdmissionResponse`` field-for-field. ``latest_observation`` is the
    Patient's most recent Observation, rendered exactly as the chart renders it,
    or null when none is charted. The counts are what the record shows is
    outstanding; each is zero where the later feature does not exist yet, and
    none is a score or a judgement (CONTEXT.md, "Ward Board").
    """

    id: int
    patient: PatientResponse
    ward: str
    bed: str
    admitted_at: UtcDatetime
    discharged_at: UtcDatetime | None = None
    encounter_id: int | None = None
    status: AdmissionStatus
    latest_observation: ObservationResponse | None = None
    outstanding_medication_count: int
    overdue_medication_count: int
    due_medication_count: int
    open_task_count: int
    unreviewed_result_count: int


class WardBoardResponse(BaseModel):
    """The ward's open Admissions, ordered by outstanding work."""

    admissions: list[WardBoardEntryResponse]
