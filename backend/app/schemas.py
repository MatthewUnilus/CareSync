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


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    age: int
    sex: Sex
    contact_phone: str
    contact_email: str | None
    registered_at: UtcDatetime


class BloodPressure(BaseModel):
    systolic: int = Field(ge=50, le=300)
    diastolic: int = Field(ge=20, le=200)

    @model_validator(mode="after")
    def _systolic_above_diastolic(self) -> "BloodPressure":
        if self.systolic <= self.diastolic:
            raise ValueError("systolic must be greater than diastolic")
        return self


class IntakePayload(BaseModel):
    """The full intake an Observation is charted from, kept for ticket 30.

    A visit no longer holds vital signs; every set of vitals is its own
    Observation (ADR 0008). This is the validated shape and the bounds the
    Observation chart will accept (pain 1-10, temperature 30-45, heart rate
    20-300, respiratory rate 0-80, systolic 50-300, diastolic 20-200 and greater
    than diastolic, saturation 50-100). No visit route accepts it yet, so a
    visit's own payload is the reason-only ``VisitReasonPayload`` below.
    """

    presenting_complaint: _TEXT
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
    """Open a visit: the Patient, and the reason for the visit.

    The reason travels under the ``intake`` wrapper the client already sends, but
    its shape is reason-only, so vitals posted here are refused until the
    Observation chart exists.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(gt=0)
    intake: VisitReasonPayload


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


class PatientSearchResponse(BaseModel):
    """Patients matching a search fragment.

    A discovery result, not an identity decision: several records may come
    back for one query, and the caller chooses. ``app.patients`` documents why
    a name alone never matches an identity, and that rule is untouched here.
    """

    patients: list[PatientResponse]


class PatientHistoryResponse(BaseModel):
    """One Patient's Encounters over time, oldest first.

    Each Encounter is rendered exactly as anywhere else, so a visit reads the
    same in a history as it does from a lookup.
    """

    patient: PatientResponse
    encounters: list[EncounterResponse]


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
