from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit_actions import AuditAction
from app.db import Base
from app.timeutils import utc_now


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
    text as it was entered (``full_name``, ``contact_phone``,
    ``hospital_number``) and the normalised keys used for matching
    (``name_key``, ``contact_key``, ``hospital_number_key``).

    Identity turns on the hospital number first, because on a ward several
    inpatients can share a surname and a family phone number is entered for more
    than one of them:

    * equal hospital numbers mean the same Patient;
    * different hospital numbers mean different Patients;
    * with neither number present, the earlier rule still applies — a Patient
      matches when the normalised name *and* the normalised contact phone are
      both equal. Name alone is never enough, so two people who share a name
      stay separate.

    Both halves are enforced by the data layer rather than by a lookup
    convention, each as a partial unique index so a concurrent double submission
    cannot create two rows either:

    * ``uq_patients_hospital_number`` is unique over ``hospital_number_key``
      where that key is not null, so a number can belong to one Patient only;
    * ``uq_patients_identity`` is unique over ``(name_key, contact_key)`` where
      ``hospital_number_key`` is null, so the name-and-phone rule governs the
      Patients that carry no number and does not apply to the numbered ones.

    Each index states its predicate for SQLite and Postgres (``sqlite_where``
    and ``postgresql_where`` on one ``Index``), so the model layer stays a single
    definition across both dialects (ADR 0001). ``hospital_number_key`` is
    nullable and carries no plain index of its own: the unique index above is
    the index a number is looked up through.

    See ``app.patients`` for the normalisation and README "Patient matching".
    """

    __tablename__ = "patients"
    __table_args__ = (
        Index(
            "uq_patients_identity",
            "name_key",
            "contact_key",
            unique=True,
            sqlite_where=text("hospital_number_key IS NULL"),
            postgresql_where=text("hospital_number_key IS NULL"),
        ),
        Index(
            "uq_patients_hospital_number",
            "hospital_number_key",
            unique=True,
            sqlite_where=text("hospital_number_key IS NOT NULL"),
            postgresql_where=text("hospital_number_key IS NOT NULL"),
        ),
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
    # The hospital number as entered, and the normalised key used for matching.
    # Optional: a walk-in with no number is still registrable, and a number may
    # be attached later to one chosen record without merging it with another.
    hospital_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hospital_number_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    encounters: Mapped[list["Encounter"]] = relationship(
        back_populates="patient",
        order_by="Encounter.arrived_at",
    )


class Encounter(Base):
    """One visit by one Patient, with a reason and an end.

    ``arrived_at`` is written once, at creation, and is never updated. The visit
    ends when the end-of-visit action records ``ended_at``. There is no second
    status column: the two conditions are derived from this one nullable
    instant, open while it is null and ended once it is set.

    Vital signs no longer live here. The engine's columns and the intake block
    are gone, so the visit carries only a reason for the visit; every set of
    vitals is its own Observation (ADR 0008).
    """

    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    arrived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    reason_for_visit: Mapped[str] = mapped_column(String(2000))

    patient: Mapped[Patient] = relationship(
        back_populates="encounters",
        lazy="joined",
    )


class AuditEntry(Base):
    """One attributable record of a clinical mutation.

    Every state-changing clinical act appends exactly one of these: registering
    a Patient, opening an Encounter, and correcting the reason for a visit. The
    entry names the actor as a foreign key rather than a copied name, so a
    renamed account is reported consistently everywhere, and exposes the name
    through the ``actor`` relationship.

    The subject references are nullable because the actions do not all have the
    same scope: registration touches only a Patient, while opening an Encounter
    also names that Encounter. Keeping one column per subject — rather than a
    polymorphic pair — means a filter to one Encounter is a plain indexed lookup
    and the row stays reconstructable without a join through whatever type it
    happened to point at.

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
    # flush (registration and open-encounter both stage one).
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patients.id"), nullable=True, index=True
    )
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.id"), nullable=True, index=True
    )

    actor: Mapped[User] = relationship(lazy="joined")
    patient: Mapped[Patient | None] = relationship()
    encounter: Mapped[Encounter | None] = relationship()


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
