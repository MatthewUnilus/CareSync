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

from sqlalchemy import select
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
    """Return the matching Patient, or stage one for insertion.

    The flag says which happened. This function deliberately does **not** commit:
    the caller does, so a registration and its audit entry share one transaction
    (see ``app.audit``). It flushes only, because the flush is what surfaces the
    unique-constraint race below.

    A concurrent double submission is still handled here: when two requests pass
    the lookup together, the unique constraint on ``(name_key, contact_key)``
    rejects the second insert at flush time, so this rolls back its own attempt
    and reuses the row the winner created.
    """
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
        session.flush()
    except IntegrityError:
        # Another request registered the same person between the lookup and
        # the insert; the unique constraint caught it, so reuse that row.
        session.rollback()
        existing = _find(session, name_key, contact_key)
        if existing is None:
            raise
        return existing, False
    return patient, True


def _find(session: Session, name_key: str, contact_key: str) -> Patient | None:
    return session.scalar(
        select(Patient).where(
            Patient.name_key == name_key,
            Patient.contact_key == contact_key,
        )
    )
