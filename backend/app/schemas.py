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
from app.models import (
    AdministrationOutcome,
    InvestigationState,
    MedicationOrderStatus,
    Role,
    Sex,
    TaskStatus,
)
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
#: A Medication Order's transcribed instruction: the drug, dose, route and the
#: free-text name of the doctor who gave it. Required and non-blank; the lengths
#: match the model's columns so a stored value is never silently truncated. There
#: is no controlled drug or route vocabulary in scope, so nothing here validates
#: a value as a coded concept (ADR 0011).
_DRUG = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
_DOSE = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
_ROUTE = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
_INSTRUCTED_BY = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
#: An Investigation's optional free-text requester: the doctor is not a user of
#: this system, so who requested the test is text. Optional, so it may be absent.
_OPTIONAL_INSTRUCTED_BY = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=200)
]
#: A round-frequency key. Checked against the fixed vocabulary in ``app.medications``
#: by the route, so an unknown frequency — or one the ticket deliberately does not
#: cover — is refused with a ``422`` rather than silently stored.
_FREQUENCY_KEY = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
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


class MedicationFrequencyResponse(BaseModel):
    """One round frequency and the clock times of day it maps to.

    The times are the provisional ward convention held in ``app.medications``,
    shown to the user so nobody mistakes them for clinical advice. They are
    ``HH:MM`` strings, in the order the doses fall through the day.
    """

    key: str
    label: str
    times: list[str]


class RoundTimesResponse(BaseModel):
    """The frequency-to-round-times convention, so a client can show it."""

    frequencies: list[MedicationFrequencyResponse]


class MedicationOrderCreateRequest(BaseModel):
    """Transcribe one medication instruction a doctor already gave.

    ``drug``, ``dose``, ``route`` and ``frequency`` are the instruction's clinical
    fields; ``start_at`` is when the schedule begins; ``instructed_by`` is the
    doctor's name as text, because the doctor is not a user of this system. An
    unknown key is refused rather than ignored. The order records nothing the
    system decided: it is a transcription, not a prescription (ADR 0011).
    """

    model_config = ConfigDict(extra="forbid")

    drug: _DRUG
    dose: _DOSE
    route: _ROUTE
    frequency: _FREQUENCY_KEY
    start_at: datetime
    instructed_by: _INSTRUCTED_BY


class MedicationOrderResponse(BaseModel):
    """One Medication Order, active or stopped.

    ``status`` is derived from ``stopped_at`` rather than stored: active while the
    instant is null, stopped once it is set. A stopped order is still returned in
    full, and it produces no further due doses. ``instructed_by`` is the doctor's
    name as text; the Clinical user who transcribed the order is not carried here,
    because the order is the instruction rather than the act of recording it.
    """

    id: int
    admission_id: int
    drug: str
    dose: str
    route: str
    frequency: str
    start_at: UtcDatetime
    instructed_by: str
    status: MedicationOrderStatus
    stopped_at: UtcDatetime | None = None


class MedicationOrderListResponse(BaseModel):
    """One Admission's Medication Orders, oldest first, including stopped ones."""

    orders: list[MedicationOrderResponse]


class DueDoseResponse(BaseModel):
    """One dose due in the window, derived at read time from an active order.

    ``due_at`` is the round time the dose falls at and ``overdue`` is whether it
    is past the server's clock at the moment of the read. Nothing is stored for a
    dose: it is computed from the order's frequency and start time and the round
    times. ``patient`` is the Admission's Patient, rendered exactly as anywhere
    else, so a dose carries who it is for without a second read.
    """

    order_id: int
    admission_id: int
    patient: PatientResponse
    drug: str
    dose: str
    route: str
    due_at: UtcDatetime
    overdue: bool


class DueListResponse(BaseModel):
    """Every dose due in the window across the ward, sorted by due time."""

    doses: list[DueDoseResponse]


#: A Medication Administration's outcome and reason keys: short snake_case
#: identifiers matching the fixed vocabularies in ``app.administrations``. The
#: schema carries the shape (a non-blank key); the vocabulary decides which keys
#: exist and the route refuses an unknown one with a ``422``, the same discipline
#: the round-frequency key follows.
_OUTCOME_KEY = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
]
_REASON_KEY = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]


class MedicationAdministrationReasonResponse(BaseModel):
    """One key of the fixed administration-reason vocabulary.

    ``requires_text`` tells the client whether the free text is required for this
    key; it is true for ``other`` alone, so the reason set stays reportable rather
    than becoming free commentary (the pattern the deleted Override Reason used).
    """

    key: str
    label: str
    requires_text: bool


class MedicationAdministrationReasonsResponse(BaseModel):
    """The fixed administration-reason vocabulary, so a client can show it."""

    reasons: list[MedicationAdministrationReasonResponse]


class MedicationAdministrationCreateRequest(BaseModel):
    """Record one dose from a Medication Order as given, or not given.

    ``due_at`` names the round-time slot this answers; ``outcome`` is one of the
    fixed outcomes and ``reason_key`` and ``reason_text`` explain a dose that was
    not given. An unknown key is refused rather than ignored. The record is a
    nurse's attestation: no dose is calculated and no value is interpreted (ADR
    0011's position, restated for the administration).
    """

    model_config = ConfigDict(extra="forbid")

    due_at: datetime
    outcome: _OUTCOME_KEY
    reason_key: _REASON_KEY | None = None
    reason_text: _OPTIONAL_TEXT | None = None


class AdministrationReasonResponse(BaseModel):
    """The reason on a recorded administration: its key, its human label and any
    free text. ``text`` is present only for the ``other`` key."""

    key: str
    label: str
    text: str | None = None


class MedicationAdministrationResponse(BaseModel):
    """One recorded administration: what was due, what happened, when and by whom.

    ``due_at`` is the slot this row answers and ``outcome`` is what the nurse
    recorded; ``reason`` is null when the dose was given and otherwise names the
    reason. ``late`` is a display mark, true when it was recorded after the due
    instant: a dose given after its round time is marked late rather than refused.
    ``recorded_at`` is when it was recorded and ``actor`` is the Clinical user who
    did so.
    """

    id: int
    order_id: int
    admission_id: int
    drug: str
    dose: str
    route: str
    due_at: UtcDatetime
    outcome: AdministrationOutcome
    reason: AdministrationReasonResponse | None = None
    recorded_at: UtcDatetime
    actor: ActorResponse
    late: bool


class AdministrationGridOrderResponse(BaseModel):
    """The order a grid is charted for, without the transcription's actor.

    The clinical fields and the derived condition are shown so the grid reads like
    the paper chart it replaces; ``instructed_by`` is omitted because the grid is
    about the doses, not the instruction's author.
    """

    id: int
    admission_id: int
    drug: str
    dose: str
    route: str
    frequency: str
    start_at: UtcDatetime
    status: MedicationOrderStatus
    stopped_at: UtcDatetime | None = None


class AdministrationGridSlotResponse(BaseModel):
    """One due slot on the grid.

    ``state`` is a recorded outcome (given, withheld, refused or unavailable) or,
    where nothing is recorded, the slot's relation to the clock at read time:
    ``overdue`` past its round time, ``due`` within the window just after it, or
    ``pending`` further ahead. ``administration`` is the record where one exists,
    so the grid carries both what was due and what happened.
    """

    due_at: UtcDatetime
    state: str
    administration: MedicationAdministrationResponse | None = None


class MedicationAdministrationGridResponse(BaseModel):
    """One order's doses over a window, as the paper chart reads."""

    order: AdministrationGridOrderResponse
    slots: list[AdministrationGridSlotResponse]


class AdmissionAdministrationSlotResponse(BaseModel):
    """One due slot in an Admission's administration history.

    Across an Admission's orders the history reads what was due, what happened,
    when and by whom: ``state`` is the recorded outcome or the slot's relation to
    the clock, and ``administration`` carries who recorded it and when.
    """

    order_id: int
    drug: str
    dose: str
    route: str
    due_at: UtcDatetime
    state: str
    administration: MedicationAdministrationResponse | None = None


class AdmissionAdministrationHistoryResponse(BaseModel):
    """One Admission's doses over a window, across its orders, sorted by due time."""

    slots: list[AdmissionAdministrationSlotResponse]


class TaskCreateRequest(BaseModel):
    """Raise one Task by hand against an Admission.

    ``description`` is the work as free text; ``due_at`` is optional, so work with
    a deadline is distinguishable from work without one; ``assignee_user_id`` is
    optional, so both an assigned caseload and a shared ward work. An unknown key
    is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    description: _TEXT
    due_at: datetime | None = None
    assignee_user_id: int | None = Field(default=None, gt=0)


class WardRoundTaskPayload(BaseModel):
    """One Task to raise from a Ward Round Entry: the same shape as a hand-raised
    Task, because a round instruction and a hand-raised one are the same thing."""

    model_config = ConfigDict(extra="forbid")

    description: _TEXT
    due_at: datetime | None = None
    assignee_user_id: int | None = Field(default=None, gt=0)


class WardRoundTasksRequest(BaseModel):
    """Raise several Tasks from one saved Ward Round Entry.

    ``note_id`` names the round entry the Tasks came from: it must be a saved
    Ward Round Entry on the same Admission, and a round entry may raise several
    Tasks in one go, because a round gives several instructions in one
    conversation. At least one Task is required, or the request is a no-op rather
    than a round. An unknown key is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    note_id: int = Field(gt=0)
    tasks: list[WardRoundTaskPayload] = Field(min_length=1)


class AssignTaskRequest(BaseModel):
    """Assign a Task to a Clinical user, or leave it unassigned with null.

    Null clears the assignee, so a Task can go back to the shared ward; there is
    no separate unassign route, because clearing and setting are the same act.
    """

    model_config = ConfigDict(extra="forbid")

    assignee_user_id: int | None = Field(default=None, gt=0)


class TaskResponse(BaseModel):
    """One Task, open or done.

    The Admission is named by id and its Patient is inlined exactly as anywhere
    else, so a Task carries who it is for without a second read. ``assignee`` is
    null when the Task is unassigned; ``status`` is derived from ``completed_at``
    rather than stored, open while the instant is null and done once it is set,
    and ``completed_by`` and ``completed_at`` record who marked it done and when.

    ``overdue`` is a display mark only, measured against the server's clock at
    the moment of the read: an open Task past its due time. Nothing acts on it
    (CONTEXT.md, "Task"). ``note_id`` names the Ward Round Entry the Task came
    from, or null when it was raised by hand.
    """

    id: int
    admission_id: int
    patient: PatientResponse
    description: str
    due_at: UtcDatetime | None = None
    assignee: ActorResponse | None = None
    author: ActorResponse
    status: TaskStatus
    completed_by: ActorResponse | None = None
    completed_at: UtcDatetime | None = None
    overdue: bool
    note_id: int | None = None


class TaskListResponse(BaseModel):
    """One Admission's Tasks, or the ward's open Tasks across patients."""

    tasks: list[TaskResponse]


class WardRoundTasksResponse(BaseModel):
    """The Tasks one Ward Round Entry raised, in the order they were given."""

    tasks: list[TaskResponse]


class StaffMemberResponse(BaseModel):
    """One Clinical user, as the optional-assignee list shows them."""

    id: int
    display_name: str


class StaffResponse(BaseModel):
    """The Clinical staff a Task may be assigned to. Administrators are not
    clinical, so they are not offered as an assignee."""

    users: list[StaffMemberResponse]


class InvestigationCreateRequest(BaseModel):
    """Record a test the doctor requested against an Admission.

    ``test_name`` is free text, because a controlled test vocabulary is out of
    scope and the free text absorbs the variation. ``instructed_by`` is the
    doctor who requested it as free text: the doctor is not a user of this
    system, so who requested it is recorded as text alongside the Clinical user
    who transcribed it. An unknown key is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    test_name: _NAME
    instructed_by: _OPTIONAL_INSTRUCTED_BY | None = None

    @field_validator("instructed_by")
    @classmethod
    def _blank_instructed_by_is_absent(cls, value: str | None) -> str | None:
        """A blank instruction is no instruction, the same rule an Observation's
        blank notes follow."""
        return value or None


class InvestigationResultRequest(BaseModel):
    """Record a result for an Investigation, as the laboratory gave it.

    ``result_note`` is free text, required and non-blank, and stored verbatim:
    the system never reads a value, flags an abnormal one or suggests anything
    from it, so there is nothing to validate it against (ADR 0012). An unknown
    key is refused rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    result_note: _TEXT


class InvestigationResponse(BaseModel):
    """One Investigation, its progress derived from its instants.

    ``state`` is derived from the instants rather than stored: requested, then
    sample taken, then result available, then reviewed. ``requested_by`` is the
    Clinical user who recorded it and ``instructed_by`` the doctor who requested
    it as free text. ``result_note`` is the result as the laboratory gave it,
    free text with no value parsed from it; ``reviewed_by`` and ``reviewed_at``
    record the accountable act. Nothing here marks a result overdue or otherwise
    reads a clinical meaning into its arrival: the states carry the progress and
    no threshold is applied.
    """

    id: int
    admission_id: int
    patient: PatientResponse
    test_name: str
    instructed_by: str | None = None
    requested_at: UtcDatetime
    requested_by: ActorResponse
    state: InvestigationState
    sample_taken_at: UtcDatetime | None = None
    result_available_at: UtcDatetime | None = None
    result_note: str | None = None
    reviewed_at: UtcDatetime | None = None
    reviewed_by: ActorResponse | None = None


class InvestigationListResponse(BaseModel):
    """One Admission's Investigations, or one of the ward's two worklists."""

    investigations: list[InvestigationResponse]


# Ward Operations Dashboard Reports


class WardCensusReportResponse(BaseModel):
    """Current ward census by location."""

    total_patients: int
    by_ward: dict[str, int]
    by_bed: dict[str, int]


class LengthOfStayDistributionItem(BaseModel):
    admission_id: int
    patient: str
    ward: str
    bed: str
    seconds: float
    days: float


class LengthOfStayReportResponse(BaseModel):
    """Length of stay for current inpatients."""

    average_seconds: float
    distribution: list[LengthOfStayDistributionItem]


class MedicationTimelinessReportResponse(BaseModel):
    """Doses recorded on time, late, and not given over a period."""

    on_time: int
    late: int
    not_given: int
    total: int
    on_time_pct: float


class InvestigationReviewReportResponse(BaseModel):
    """Results awaiting review and oldest wait time."""

    awaiting_review_count: int
    oldest_wait_seconds: int | None


class TaskCompletionReportResponse(BaseModel):
    """Tasks completed vs raised over a period."""

    raised: int
    completed: int
    completion_pct: float


# Study Instrumentation (ticket 40)


class StudyTaskRunCreateRequest(BaseModel):
    """Start a timed study task run.

    ``task_label`` names the task being timed (e.g. "handover_sheet",
    "medication_round", "ward_worklist"). ``participant_id`` is the
    anonymised study identifier (e.g. "P01", "P02") — never the nurse's
    name or user id.
    """

    model_config = ConfigDict(extra="forbid")

    task_label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    participant_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class StudyTaskRunEndRequest(BaseModel):
    """End a timed study task run.

    ``participant_id`` must match the run being ended.
    """

    model_config = ConfigDict(extra="forbid")

    participant_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class StudyTaskRunAbandonRequest(BaseModel):
    """Abandon a timed study task run.

    ``participant_id`` must match the run being abandoned.
    """

    model_config = ConfigDict(extra="forbid")

    participant_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class StudyTaskRunResponse(BaseModel):
    """One study task run, as read back for export."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_label: str
    participant_id: str
    started_at: UtcDatetime
    ended_at: UtcDatetime | None = None
    status: str


class StudyTaskRunListResponse(BaseModel):
    """All study task runs for export."""

    runs: list[StudyTaskRunResponse]
