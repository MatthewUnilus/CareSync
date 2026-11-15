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

from app.accuracy import FallbackMode, RunSource
from app.departures import EncounterStatus
from app.models import Role, Sex
from app.override_reasons import OverrideReason, allows_free_text
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


class OverrideActorResponse(BaseModel):
    id: int
    display_name: str


class OverrideRecordResponse(BaseModel):
    """The human act behind a Final Decision that differs from the machine's."""

    reason: OverrideReason
    free_text: str | None
    performed_at: UtcDatetime
    performed_by: OverrideActorResponse


class RedFlagResponse(BaseModel):
    """One red-flag rule that fired for an Assessment's captured inputs.

    Exposed so the board can show *why* a presentation reached High, and mark
    the abnormal vital it keyed on. Derived from the same cited rule set the
    safety layer runs (``app.red_flags``); it is a read-only explanation, not a
    new decision.
    """

    id: str
    finding: str
    citation: str
    # Intake field names this rule keyed on (empty when it keyed on a
    # recognised Symptom Group instead of a measured value).
    vitals: list[str]


class AssessmentResponse(BaseModel):
    id: int
    assessed_at: UtcDatetime
    machine_recommendation: UrgencyLevel
    final_decision: UrgencyLevel
    recognised_symptom_groups: list[str]
    # True when the complaint matched no Symptom Group and the fallback
    # provider was unavailable or timed out. A separate signal from an
    # Override, which is represented by ``override`` and ``override_flag``.
    unclassified: bool = False
    # Every red flag that fired on this Assessment's frozen inputs.
    red_flags: list[RedFlagResponse] = Field(default_factory=list)
    override: OverrideRecordResponse | None = None
    snapshot: AssessmentSnapshot
    # Set by a Re-assessment: the governing Assessment it replaced. Null on a
    # first Assessment, so the history reconstructs the whole sequence.
    supersedes_assessment_id: int | None = None


class OverrideRequest(BaseModel):
    """Set a Final Decision different from the Machine Recommendation.

    ``machine_recommendation`` is deliberately not a field, and unknown fields
    are refused, so this path cannot be used to write the engine's output.
    """

    model_config = ConfigDict(extra="forbid")

    assessment_id: int = Field(gt=0)
    final_decision: UrgencyLevel
    reason: OverrideReason
    free_text: _OPTIONAL_TEXT | None = None

    @field_validator("free_text")
    @classmethod
    def _blank_free_text_is_absent(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _free_text_only_for_other(self) -> "OverrideRequest":
        if not allows_free_text(self.reason) and self.free_text is not None:
            raise ValueError(
                "free_text is accepted only when reason is 'other'"
            )
        return self


class OverrideReasonsResponse(BaseModel):
    """The fixed Override Reason set, in glossary order."""

    reasons: list[OverrideReason]


class EncounterResponse(BaseModel):
    """One Encounter, awaiting or departed.

    ``status`` is derived from ``departed_at`` rather than stored: awaiting
    while the instant is null, departed once it is set. A departed Encounter
    is still returned in full, with its Patient, intake, Assessment and
    Override intact.

    ``assessment`` is the governing (most recent) Assessment. ``assessments``
    is the whole history oldest-first, so a Re-assessed Encounter stays
    readable back to its first decision; the earlier rows keep their own
    snapshots and Overrides.
    """

    id: int
    arrived_at: UtcDatetime
    departed_at: UtcDatetime | None = None
    status: EncounterStatus
    patient: PatientResponse
    intake: IntakePayload
    assessment: AssessmentResponse | None = None
    assessments: list[AssessmentResponse] = Field(default_factory=list)


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
    override_flag: bool
    # Its own state, not a reuse of override_flag: the fallback provider could
    # not classify the complaint, so the recommendation needs clinical review.
    unclassified_flag: bool


class QueueResponse(BaseModel):
    as_of: UtcDatetime
    entries: list[QueueEntryResponse]


class AdministratorQueueEntryResponse(BaseModel):
    """One row of the Administrator's dense Queue table."""

    encounter_id: int
    arrived_at: UtcDatetime
    waiting_seconds: int
    urgency_level: UrgencyLevel
    patient_name: str
    presenting_complaint: str
    machine_recommendation: UrgencyLevel
    final_decision: UrgencyLevel
    final_decision_differs: bool


class AdministratorQueueResponse(BaseModel):
    as_of: UtcDatetime
    entries: list[AdministratorQueueEntryResponse]


class DailyQueueReportResponse(BaseModel):
    """One UTC day's arrival volume, departure throughput, and backlog."""

    day: date
    starts_at: UtcDatetime
    ends_at: UtcDatetime
    volume: int
    throughput: int
    awaiting: int


class UrgencyLevelCountResponse(BaseModel):
    urgency_level: UrgencyLevel
    encounters: int


class UrgencyDistributionReportResponse(BaseModel):
    total: int
    levels: list[UrgencyLevelCountResponse]


class PerformanceEntryResponse(BaseModel):
    encounter_id: int
    arrived_at: UtcDatetime
    assessed_at: UtcDatetime
    departed_at: UtcDatetime
    waiting_seconds: int
    processing_seconds: int


class PerformanceReportResponse(BaseModel):
    completed: int
    average_waiting_seconds: float
    average_processing_seconds: float
    entries: list[PerformanceEntryResponse]


class AccuracyGroundTruthSourceResponse(BaseModel):
    """Where the labels came from. Shown in the UI so the standard is named."""

    name: str
    version: str
    citation: str
    document: str | None


class AccuracyConfusionCellResponse(BaseModel):
    machine_recommendation: UrgencyLevel
    ground_truth: UrgencyLevel
    assessments: int


class AccuracyLevelMetricsResponse(BaseModel):
    urgency_level: UrgencyLevel
    ground_truth_count: int
    predicted_count: int
    correct: int
    precision: float | None
    recall: float | None


class AccuracyPriorityErrorRateResponse(BaseModel):
    count: int
    denominator: int
    rate: float | None


class AccuracyLevelRecallResponse(BaseModel):
    count: int
    denominator: int
    rate: float | None


class AccuracyRunVariantResponse(BaseModel):
    """A secondary scoring, explicitly not a Machine Recommendation."""

    description: str
    total: int
    correct: int
    accuracy: float
    macro_f1: float
    false_high_priority: AccuracyPriorityErrorRateResponse
    false_low_priority: AccuracyPriorityErrorRateResponse
    high_class_recall: AccuracyLevelRecallResponse


class AccuracyRunSampleResponse(BaseModel):
    labelled_cases: int
    resolved_assessments: int
    missing_assessments: list[int]
    inconsistent_recommendations: list[int]


class AccuracyFallbackCoverageResponse(BaseModel):
    enabled: bool
    fallback_used: int
    unclassified: int
    coverage: float | None
    unclassified_rate: float | None


class AccuracyMajorityBaselineResponse(BaseModel):
    majority_class: UrgencyLevel
    accuracy: float
    model_minus_baseline: float
    beats_baseline: bool


class AccuracyRunResponse(BaseModel):
    run_id: str
    run_mode: str
    source: RunSource
    primary: bool
    mode: FallbackMode
    dataset: str | None
    engine_artefact: str | None
    ground_truth: AccuracyGroundTruthSourceResponse
    sample: AccuracyRunSampleResponse
    confusion_matrix: list[AccuracyConfusionCellResponse]
    levels: list[AccuracyLevelMetricsResponse]
    total: int
    correct: int
    accuracy: float | None
    macro_f1: float | None
    majority_baseline: AccuracyMajorityBaselineResponse | None
    false_high_priority: AccuracyPriorityErrorRateResponse
    false_low_priority: AccuracyPriorityErrorRateResponse
    high_class_recall: AccuracyLevelRecallResponse
    fallback: AccuracyFallbackCoverageResponse
    classifier_only: AccuracyRunVariantResponse | None


class AccuracyOverrideReasonCountResponse(BaseModel):
    reason: OverrideReason
    overrides: int
    share: float | None


class AccuracyOverrideMetricsResponse(BaseModel):
    assessments: int
    overridden_assessments: int
    overrides: int
    rate: float | None
    reasons: list[AccuracyOverrideReasonCountResponse]


class AccuracyEvaluationReportResponse(BaseModel):
    available: bool
    empty_reason: str | None
    runs: list[AccuracyRunResponse]
    overrides: AccuracyOverrideMetricsResponse
