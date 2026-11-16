"""Patient registration and the Patient matching rule.

A Patient is a person, not a visit. Registering the same person again must
reuse the existing record so that their Encounter history stays in one place.
The rule is deliberately conservative:

    a Patient is the same Patient when the normalised full name **and** the
    normalised contact phone number are both equal.

Requiring both means two different people who happen to share a name are never
collapsed into one record. The cost is that a returning Patient who gives a new
phone number registers as a new record; that is preferred over merging two
people, because a merge cannot be undone and a duplicate can.

Normalisation:

- name: surrounding whitespace trimmed, internal whitespace collapsed to one
  space, case-folded (``"  Ada   LOVELACE "`` -> ``"ada lovelace"``)
- phone: non-digits dropped, a leading ``+`` kept (``"0770-090 0123"`` ->
  ``"07700900123"``, ``"+44 20 7946 0958"`` -> ``"+442079460958"``)

The rule is enforced by a unique constraint on ``(name_key, contact_key)``, so a
concurrent double submission cannot create two rows either.
"""

import re

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Patient, Sex

_WHITESPACE = re.compile(r"\s+")
_NON_DIGITS = re.compile(r"\D")


def normalise_name(name: str) -> str:
    return _WHITESPACE.sub(" ", name.strip()).casefold()


def normalise_contact(phone: str) -> str:
    digits = _NON_DIGITS.sub("", phone)
    return f"+{digits}" if phone.strip().startswith("+") else digits


def find_or_create_patient(
    session: Session,
    *,
    full_name: str,
    age: int,
    sex: Sex,
    contact_phone: str,
    contact_email: str | None,
) -> tuple[Patient, bool]:
    """Return the matching Patient, or create one. The flag says which happened."""
    name_key = normalise_name(full_name)
    contact_key = normalise_contact(contact_phone)

    existing = _find(session, name_key, contact_key)
    if existing is not None:
        return existing, False

    patient = Patient(
        full_name=full_name.strip(),
        name_key=name_key,
        age=age,
        sex=sex.value,
        contact_phone=contact_phone.strip(),
        contact_key=contact_key,
        contact_email=contact_email,
    )
    session.add(patient)
    try:
        session.commit()
    except IntegrityError:
        # Another request registered the same person between the lookup and
        # the insert; the unique constraint caught it, so reuse that row.
        session.rollback()
        existing = _find(session, name_key, contact_key)
        if existing is None:
            raise
        return existing, False
    return patient, True


def search_patients(
    session: Session, *, query: str, limit: int
) -> list[Patient]:
    """Find Patients by a fragment of their name or their contact number.

    This is a discovery aid, deliberately looser than the matching rule above.
    ``find_or_create_patient`` treats two records as one person only when the
    whole normalised name **and** the whole normalised phone are both equal;
    that rule is untouched, and nothing here decides identity. A search may
    match part of a name, or part of a number, and returns several candidates
    for a human to choose between — collapsing the two would let a partial
    name merge two people, which is exactly what the matching rule forbids.

    A blank or whitespace-only query returns nothing rather than every Patient,
    so the search cannot be used as a bulk export of the table.

    The query is normalised the same way stored values are, so ``"  ADA "``
    and ``"ada"`` search alike, and a number typed with spaces or dashes still
    matches the digits as stored. Each predicate is applied only when its
    normalised form is non-empty: a query with no digits must not run an empty
    contact ``LIKE``, which would match every row.
    """
    name_key = normalise_name(query)
    if not name_key:
        return []

    conditions = [Patient.name_key.contains(name_key, autoescape=True)]
    contact_key = normalise_contact(query)
    if contact_key:
        conditions.append(
            Patient.contact_key.contains(contact_key, autoescape=True)
        )

    return list(
        session.scalars(
            select(Patient)
            .where(or_(*conditions))
            .order_by(Patient.name_key, Patient.id)
            .limit(limit)
        ).all()
    )


def _find(session: Session, name_key: str, contact_key: str) -> Patient | None:
    return session.scalar(
        select(Patient).where(
            Patient.name_key == name_key,
            Patient.contact_key == contact_key,
        )
    )
