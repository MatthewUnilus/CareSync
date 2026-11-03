import re
from datetime import datetime
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

from app.models import Role, Sex
from app.prioritisation import UrgencyLevel
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
    """The intake captured for an Encounter, as sent and as returned.

    Every field except ``notes`` is required: these are the inputs a Triage
    Assessment runs on, so an Encounter cannot be opened without them.
    """

    presenting_complaint: _TEXT
    pain_level: int = Field(ge=1, le=10)
    illness_duration_hours: float = Field(ge=0, le=8760)
    temperature_c: float = Field(ge=30, le=45)
    heart_rate_bpm: int = Field(ge=20, le=300)
    blood_pressure: BloodPressure
    oxygen_saturation_percent: int = Field(ge=50, le=100)
    notes: _OPTIONAL_TEXT | None = None

    @field_validator("notes")
    @classmethod
    def _blank_notes_are_absent(cls, value: str | None) -> str | None:
        return value or None


class EncounterCreateRequest(BaseModel):
    patient_id: int = Field(gt=0)
    intake: IntakePayload


class AssessmentSnapshot(BaseModel):
    """The immutable inputs captured when the Assessment ran."""

    presenting_complaint: str
    age: int
    pain_level: int
    illness_duration_hours: float
    temperature_c: float
    heart_rate_bpm: int
    blood_pressure: BloodPressure
    oxygen_saturation_percent: int
    notes: str | None


class AssessmentResponse(BaseModel):
    id: int
    assessed_at: UtcDatetime
    machine_recommendation: UrgencyLevel
    final_decision: UrgencyLevel
    recognised_symptom_groups: list[str]
    snapshot: AssessmentSnapshot


class EncounterResponse(BaseModel):
    id: int
    arrived_at: UtcDatetime
    patient: PatientResponse
    intake: IntakePayload
    assessment: AssessmentResponse | None = None


class EncounterListResponse(BaseModel):
    encounters: list[EncounterResponse]


class QueueEntryResponse(BaseModel):
    """One compact card's worth of data, plus everything the expansion shows."""

    encounter_id: int
    arrived_at: UtcDatetime
    waiting_seconds: int
    urgency_level: UrgencyLevel
    patient: PatientResponse
    intake: IntakePayload
    assessment: AssessmentResponse


class QueueResponse(BaseModel):
    as_of: UtcDatetime
    entries: list[QueueEntryResponse]
