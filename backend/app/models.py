from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.timeutils import utc_now


class Role(str, Enum):
    clinical = "clinical"
    administrator = "administrator"


ROLE_LABELS: dict[Role, str] = {
    Role.clinical: "Clinical",
    Role.administrator: "Administrator",
}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('clinical', 'administrator')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Sex(str, Enum):
    female = "female"
    male = "male"
    other = "other"
    unspecified = "unspecified"


class Patient(Base):
    """A person, independent of any visit.

    Registering the same person twice reuses this row. The row carries both the
    text as it was entered (``full_name``, ``contact_phone``) and the normalised
    keys used for matching (``name_key``, ``contact_key``). The unique
    constraint over those two keys is the matching rule, enforced by the data
    layer rather than by a lookup convention:

    a Patient is the same Patient when the normalised name *and* the normalised
    contact phone are both equal. Name alone is never enough, so two different
    people who share a name stay separate.

    See ``app.patients`` for the normalisation and README "Patient matching".
    """

    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("name_key", "contact_key", name="uq_patients_identity"),
        CheckConstraint(
            "sex IN ('female', 'male', 'other', 'unspecified')",
            name="ck_patients_sex",
        ),
        CheckConstraint("age >= 0 AND age <= 120", name="ck_patients_age"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), index=True)
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(16))
    contact_phone: Mapped[str] = mapped_column(String(40))
    contact_key: Mapped[str] = mapped_column(String(40), index=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    encounters: Mapped[list["Encounter"]] = relationship(
        back_populates="patient",
        order_by="Encounter.arrived_at",
    )


class Encounter(Base):
    """One visit by one Patient. Holds the intake a Triage Assessment runs on.

    ``arrived_at`` is written once, at creation, and is never updated. Intake
    values may be corrected only until the first Triage Assessment exists, at
    which point the Assessment's snapshot becomes the durable record of what
    the recommendation was made from.

    An Encounter is **awaiting** while ``departed_at`` is null, and **departed**
    once ticket 11 records the departure instant. The Queue is every awaiting
    Encounter, sorted; it is never a stored sequence.
    """

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint(
            "pain_level >= 1 AND pain_level <= 10",
            name="ck_encounters_pain_level",
        ),
        CheckConstraint(
            "temperature_c >= 30 AND temperature_c <= 45",
            name="ck_encounters_temperature",
        ),
        CheckConstraint(
            "heart_rate_bpm >= 20 AND heart_rate_bpm <= 300",
            name="ck_encounters_heart_rate",
        ),
        CheckConstraint(
            "systolic_bp >= 50 AND systolic_bp <= 300",
            name="ck_encounters_systolic",
        ),
        CheckConstraint(
            "diastolic_bp >= 20 AND diastolic_bp <= 200",
            name="ck_encounters_diastolic",
        ),
        CheckConstraint(
            "systolic_bp > diastolic_bp",
            name="ck_encounters_blood_pressure_order",
        ),
        CheckConstraint(
            "oxygen_saturation_percent >= 50 AND oxygen_saturation_percent <= 100",
            name="ck_encounters_oxygen_saturation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    arrived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    departed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    presenting_complaint: Mapped[str] = mapped_column(String(2000))
    pain_level: Mapped[int] = mapped_column(Integer)
    illness_duration_hours: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    heart_rate_bpm: Mapped[int] = mapped_column(Integer)
    systolic_bp: Mapped[int] = mapped_column(Integer)
    diastolic_bp: Mapped[int] = mapped_column(Integer)
    oxygen_saturation_percent: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    patient: Mapped[Patient] = relationship(
        back_populates="encounters",
        lazy="joined",
    )
    assessments: Mapped[list["TriageAssessment"]] = relationship(
        back_populates="encounter",
        order_by="TriageAssessment.id",
    )


class TriageAssessment(Base):
    """One urgency decision, plus the inputs it was made from.

    Rows are append-only. ``machine_recommendation`` is the engine's output and
    is protected from later updates; ``final_decision`` is what governs the
    Queue and starts equal to the Machine Recommendation. Ticket 09 adds the
    Override that may change the Final Decision, which is why only the
    recommendation and the captured inputs are frozen here.

    The snapshot is stored as columns rather than a JSON blob so the data layer
    stays dialect-neutral (ADR 0001). It includes the Patient's age because age
    is an engine input even though it lives on the Patient.
    """

    __tablename__ = "triage_assessments"
    __table_args__ = (
        CheckConstraint(
            "machine_recommendation IN ('High', 'Medium', 'Low')",
            name="ck_triage_assessments_machine_recommendation",
        ),
        CheckConstraint(
            "final_decision IN ('High', 'Medium', 'Low')",
            name="ck_triage_assessments_final_decision",
        ),
        CheckConstraint(
            "pain_level >= 1 AND pain_level <= 10",
            name="ck_triage_assessments_pain_level",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id"), index=True
    )
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    # Immutable snapshot of the inputs the recommendation was made from.
    patient_age: Mapped[int] = mapped_column(Integer)
    presenting_complaint: Mapped[str] = mapped_column(String(2000))
    pain_level: Mapped[int] = mapped_column(Integer)
    illness_duration_hours: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    heart_rate_bpm: Mapped[int] = mapped_column(Integer)
    systolic_bp: Mapped[int] = mapped_column(Integer)
    diastolic_bp: Mapped[int] = mapped_column(Integer)
    oxygen_saturation_percent: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Comma-separated canonical Symptom Groups. Ticket 05 fills this; until
    # then the recognised set is empty, which is not the same as "not run".
    recognised_symptom_groups: Mapped[str] = mapped_column(
        String(1000), default=""
    )

    machine_recommendation: Mapped[str] = mapped_column(String(16))
    final_decision: Mapped[str] = mapped_column(String(16))

    # Ticket 10 links a Re-assessment back to the assessment it supersedes.
    supersedes_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("triage_assessments.id"), nullable=True
    )

    encounter: Mapped[Encounter] = relationship(back_populates="assessments")


# Fields that must never change after the row is written. ``final_decision`` is
# deliberately absent: ticket 09's Override changes it and leaves the Machine
# Recommendation untouched.
_ASSESSMENT_FROZEN_FIELDS = (
    "encounter_id",
    "assessed_at",
    "patient_age",
    "presenting_complaint",
    "pain_level",
    "illness_duration_hours",
    "temperature_c",
    "heart_rate_bpm",
    "systolic_bp",
    "diastolic_bp",
    "oxygen_saturation_percent",
    "notes",
    "recognised_symptom_groups",
    "machine_recommendation",
    "supersedes_assessment_id",
)


@event.listens_for(TriageAssessment, "before_update")
def _refuse_rewriting_an_assessment(_mapper, _connection, target) -> None:
    """Application-layer append-only guarantee (ADR 0001, no DB triggers)."""
    state = sa_inspect(target)
    changed = [
        name
        for name in _ASSESSMENT_FROZEN_FIELDS
        if state.attrs[name].history.has_changes()
    ]
    if changed:
        raise ValueError(
            "A Triage Assessment's captured inputs and Machine Recommendation "
            f"are immutable; refused to change {', '.join(changed)}"
        )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(back_populates="sessions", lazy="joined")
