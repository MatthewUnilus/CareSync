from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
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

from app.audit_actions import AuditAction
from app.db import Base
from app.override_reasons import OverrideReason
from app.timeutils import utc_now


_OVERRIDE_REASON_VALUES = ", ".join(
    f"'{reason.value}'" for reason in OverrideReason
)

_AUDIT_ACTION_VALUES = ", ".join(
    f"'{action.value}'" for action in AuditAction
)


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
    the recommendation was made from. The one exception is an explicit
    Re-assessment, which captures the Encounter's current condition and freezes
    it into a new Assessment; every earlier snapshot is left untouched.

    An Encounter is **awaiting** while ``departed_at`` is null, and **departed**
    once the Departure action records the instant. The Queue is every awaiting
    Encounter, sorted; it is never a stored sequence. There is no second status
    column: the condition is derived from this one nullable instant.
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
            "respiratory_rate_bpm >= 0 AND respiratory_rate_bpm <= 80",
            name="ck_encounters_respiratory_rate",
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

    # Set only when this Encounter is a stored row of a named evaluation run.
    # Such rows are real Patients/Encounters/Assessments, scored through the
    # engine, but they are measurement scaffolding: the Queue and the activity
    # Reports exclude them. Live Encounters leave this null.
    evaluation_run_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )

    presenting_complaint: Mapped[str] = mapped_column(String(2000))
    pain_level: Mapped[int] = mapped_column(Integer)
    illness_duration_hours: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    heart_rate_bpm: Mapped[int] = mapped_column(Integer)
    # Live intake always writes this (``apply_intake``), the Assessment snapshot
    # always carries it, and ``evaluation/materialise.py`` writes the corpus's
    # real rate. The default exists only so a direct construction that omits it
    # (a test, say) need not repeat it; the engine treats zero as a rate below
    # every tachypnoea threshold, so an omitted value is inert rather than
    # dangerous.
    respiratory_rate_bpm: Mapped[int] = mapped_column(Integer, default=0)
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
    Queue and starts equal to the Machine Recommendation. An Override may
    change the Final Decision, which is why only the recommendation and the
    captured inputs are frozen here.

    An Encounter may hold several rows: a Re-assessment appends a new one and
    points ``supersedes_assessment_id`` at the row it replaced. The most recent
    row is the one that governs.

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
            "ground_truth_level IS NULL OR "
            "ground_truth_level IN ('High', 'Medium', 'Low')",
            name="ck_triage_assessments_ground_truth_level",
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
    # Carried on every snapshot the engine factory writes; the default mirrors
    # ``Encounter.respiratory_rate_bpm`` and exists only for a direct
    # construction that omits it.
    respiratory_rate_bpm: Mapped[int] = mapped_column(Integer, default=0)
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

    # Independent ground truth, present only on an evaluation-run row. It is
    # deliberately a separate column from ``machine_recommendation`` and
    # ``final_decision`` so the rubric label can never be confused with either.
    # Null on every live Assessment.
    ground_truth_level: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )

    # True only when the complaint matched no Symptom Group and the fallback
    # provider was unavailable or exceeded its timeout, so the recommendation
    # came from the safety layer's documented default. Frozen with the rest of
    # the Assessment; it is not the same signal as an Override.
    unclassified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Set by a Re-assessment: the Assessment it replaced. Null on the first.
    supersedes_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("triage_assessments.id"), nullable=True
    )

    encounter: Mapped[Encounter] = relationship(back_populates="assessments")
    overrides: Mapped[list["Override"]] = relationship(
        back_populates="assessment",
        order_by="Override.id",
    )


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
    "respiratory_rate_bpm",
    "systolic_bp",
    "diastolic_bp",
    "oxygen_saturation_percent",
    "notes",
    "recognised_symptom_groups",
    "machine_recommendation",
    "ground_truth_level",
    "unclassified",
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


class FallbackCacheEntry(Base):
    """One cached answer from the runtime fallback provider.

    The key is the SHA-256 of the complaint text exactly as stored, so identical
    wording always resolves to the same provider answer, including after a
    process restart. Only the provider's complaint-only level is cached: the
    safety layer is applied to it on every resolve, because the same words can
    belong to a patient with different vitals. A degraded (unclassified) answer
    is never cached, so a transient outage does not stick in the record.

    The column is ``urgency_level``, not ``machine_recommendation``: this is the
    external provider's answer to the complaint alone, before the safety layer
    and before the engine produces a Machine Recommendation.
    """

    __tablename__ = "fallback_cache"
    __table_args__ = (
        CheckConstraint(
            "urgency_level IN ('High', 'Medium', 'Low')",
            name="ck_fallback_cache_urgency_level",
        ),
    )

    complaint_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    presenting_complaint: Mapped[str] = mapped_column(String(2000))
    urgency_level: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Override(Base):
    """One human act of disagreeing with a Machine Recommendation.

    The Override records *who* performed it and *why*, alongside the Assessment
    it applies to. It never carries a decision of its own: the decision lives
    in ``TriageAssessment.final_decision``, which this act changes while the
    Machine Recommendation stays untouched.

    Reasons are stored as validated strings (ADR 0001), constrained to the
    fixed set in ``app.override_reasons``. Free text is only ever present for
    the ``other`` reason, enforced at the request boundary.
    """

    __tablename__ = "overrides"
    __table_args__ = (
        CheckConstraint(
            f"reason IN ({_OVERRIDE_REASON_VALUES})",
            name="ck_overrides_reason",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("triage_assessments.id"), index=True
    )
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(64))
    free_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    assessment: Mapped[TriageAssessment] = relationship(
        back_populates="overrides"
    )
    actor: Mapped[User] = relationship(lazy="joined")


class AuditEntry(Base):
    """One attributable record of a clinical mutation.

    Every state-changing clinical act appends exactly one of these: registration,
    opening an Encounter, correcting intake, an Override, a Re-assessment and a
    Departure. The entry names the actor as a foreign key rather than a copied
    name, so a renamed account is reported consistently everywhere, and exposes
    the name through the ``actor`` relationship exactly as ``Override`` does.

    The subject references are nullable because the six actions do not all have
    the same scope: registration touches only a Patient, while opening an
    Encounter also produces its first Assessment. Keeping one column per subject
    — rather than a polymorphic pair — means a filter to one Encounter is a plain
    indexed lookup and the row stays reconstructable without a join through
    whatever type it happened to point at.

    Rows are append-only, enforced in the application layer (see the guard
    below), because ADR 0001 forbids database triggers. An audit record that can
    be silently edited after the fact is not an audit record.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            f"action IN ({_AUDIT_ACTION_VALUES})",
            name="ck_audit_log_action",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    # The subjects this act touched. Nullable because not every action reaches
    # every subject; indexed because "one Encounter's history" is the read the
    # Administrator surface offers. The relationships are set rather than the
    # ids so an entry can reference a subject that is still pending in the same
    # flush (registration and open-encounter both stage one), exactly as
    # ``Override`` sets ``assessment`` rather than ``assessment_id``.
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True, index=True
    )
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id"), nullable=True, index=True
    )
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("triage_assessments.id"), nullable=True, index=True
    )

    actor: Mapped[User] = relationship(lazy="joined")
    patient: Mapped[Patient | None] = relationship()
    encounter: Mapped[Encounter | None] = relationship()
    assessment: Mapped[TriageAssessment | None] = relationship()


@event.listens_for(AuditEntry, "before_update")
def _refuse_editing_an_audit_entry(_mapper, _connection, _target) -> None:
    """Application-layer append-only guarantee (ADR 0001, no DB triggers).

    The guard refuses *any* in-place change, not a fixed field list: an audit
    entry has no field that is ever legitimately updated, so the whole row is
    frozen rather than a chosen subset of it.
    """
    raise ValueError(
        "An Audit Entry is append-only; it cannot be edited after it is written"
    )


class UserSession(Base):
    """One signed-in session on one device.

    The row is the single source of truth for "may this session act". Expiry
    lives here, and beside it the lock state a shared ward tablet needs: an
    inactivity lock that hides patient data without ending the session, the
    last time the session was seen, and the failed-unlock counters that stop a
    locked tablet becoming an unattended guessing surface.

    ``locked_at`` is nullable: null means unlocked. It is a deliberate act
    (a nurse locks the tablet) or a derived one (the idle window lapsed when a
    request arrived); either way the session survives, because unlocking is a
    credential check on this same row rather than a fresh sign-in.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Last time an authenticated request was seen. Drives the inactivity lock.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    # Null while unlocked; set to the instant the lock took effect.
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Wrong-password attempts since the session locked, and the instant past
    # which a new attempt is refused. Both reset on a successful unlock; the
    # counter is application-layer state, not a database constraint.
    unlock_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    unlock_blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="sessions", lazy="joined")
