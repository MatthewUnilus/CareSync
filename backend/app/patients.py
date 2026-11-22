"""Patient registration and the Patient matching rule.

A Patient is a person, not a visit. Registering the same person again must
reuse the existing record so that their Encounter history stays in one place,
but only when the two really are the same person. The rule turns on the
hospital number first:

    equal hospital numbers mean the same Patient; different hospital numbers
    mean different Patients; with neither number present, a Patient matches
    when the normalised full name **and** the normalised contact phone number
    are both equal.

The hospital number carries the identity when it is present, because on a ward
several inpatients can share a surname and a family phone number is entered for
more than one of them. Requiring both name and phone to match is what keeps two
different people who share a name apart; the cost is that a returning Patient
who gives a new phone number registers as a new record, which is preferred over
merging two people, because a merge cannot be undone and a duplicate can.

A supplied number is matched on its own and never falls back to the name-and-
phone rule, so a numbered registration can never quietly claim an unrelated
record that happens to share a name and phone. Adding a number to an already-
registered Patient is a separate, explicit act: the attach route in
``app.routers.clinical`` sets it on one record a human has chosen, and defers
to this module's ``normalise_hospital_number`` for the key.

The rule is enforced at the data layer by two partial unique indexes (see
``app.models.Patient``), so a concurrent double submission cannot create two
rows either.

Normalisation:

- name: surrounding whitespace trimmed, internal whitespace collapsed to one
  space, case-folded (``"  Ada   LOVELACE "`` -> ``"ada lovelace"``)
- phone: non-digits dropped, a leading ``+`` kept (``"0770-090 0123"`` ->
  ``"07700900123"``, ``"+44 20 7946 0958"`` -> ``"+442079460958"``)
- hospital number: surrounding whitespace trimmed, internal whitespace collapsed
  to one space, case-folded (``"  MRN 4471 "`` -> ``"mrn 4471"``). The number is
  stored as entered and this key is used only for matching, the way name and
  phone already work. Unlike the phone rule no characters are dropped, because
  a number is an opaque identifier and folding two spellings a reader would call
  different risks matching the wrong record.
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


def normalise_hospital_number(number: str) -> str:
    return _WHITESPACE.sub(" ", number.strip()).casefold()


def find_or_create_patient(
    session: Session,
    *,
    full_name: str,
    age: int,
    sex: Sex,
    contact_phone: str,
    contact_email: str | None,
    hospital_number: str | None = None,
) -> tuple[Patient, bool]:
    """Return the matching Patient, or stage one for insertion.

    The flag says which happened. This function deliberately does **not** commit:
    the caller does, so a registration and its audit entry share one transaction
    (see ``app.audit``). It flushes only, because the flush is what surfaces the
    unique-index race below.

    The hospital number decides the match when it is present: the lookup is
    made on the number alone and does not fall back to the name-and-phone rule,
    so a numbered registration cannot claim an unrelated no-number record. With
    no number supplied, the non-numbered lookup still applies.

    A concurrent double submission is still handled here: when two requests pass
    the lookup together, the matching partial unique index rejects the second
    insert at flush time, so this rolls back its own attempt and reuses the row
    the winner created.
    """
    name_key = normalise_name(full_name)
    contact_key = normalise_contact(contact_phone)
    hospital_number_key = _hospital_key(hospital_number)

    existing = _find(session, name_key, contact_key, hospital_number_key)
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
        hospital_number=(
            hospital_number.strip()
            if hospital_number_key is not None and hospital_number is not None
            else None
        ),
        hospital_number_key=hospital_number_key,
    )
    session.add(patient)
    try:
        session.flush()
    except IntegrityError:
        # Another request registered the same person between the lookup and
        # the insert; the matching partial unique index caught it, so reuse that
        # row.
        session.rollback()
        existing = _find(session, name_key, contact_key, hospital_number_key)
        if existing is None:
            raise
        return existing, False
    return patient, True


def search_patients(
    session: Session, *, query: str, limit: int
) -> list[Patient]:
    """Find Patients by a fragment of their name, contact number or hospital number.

    This is a discovery aid, deliberately looser than the matching rule above.
    ``find_or_create_patient`` treats two records as one person only when the
    whole normalised name **and** the whole normalised phone are both equal, or
    when the hospital number is equal; that rule is untouched, and nothing here
    decides identity. A search may match part of a name, part of a contact
    number, or part of a hospital number, and returns several candidates for a
    human to choose between — collapsing the two would let a partial name merge
    two people, which is exactly what the matching rule forbids.

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
    hospital_number_key = _hospital_key(query)
    if hospital_number_key:
        conditions.append(
            Patient.hospital_number_key.contains(
                hospital_number_key, autoescape=True
            )
        )

    return list(
        session.scalars(
            select(Patient)
            .where(or_(*conditions))
            .order_by(Patient.name_key, Patient.id)
            .limit(limit)
        ).all()
    )


def _hospital_key(hospital_number: str | None) -> str | None:
    """The matching key for a hospital number, or None when it is absent.

    A blank or whitespace-only value is absent, not an empty key: it must never
    collide with another absent number, and the data layer treats null keys as
    distinct.
    """
    if hospital_number is None:
        return None
    key = normalise_hospital_number(hospital_number)
    return key or None


def _find(
    session: Session,
    name_key: str,
    contact_key: str,
    hospital_number_key: str | None,
) -> Patient | None:
    """The one Patient that matches, by number when present else by name+phone.

    A numbered lookup matches only a record carrying that same number, and an
    unnumbered lookup matches only a record carrying no number: identity by
    number and identity by name-and-phone are separate rules, not a fallback
    chain, so a numbered registration cannot claim an unrelated no-number row.
    """
    if hospital_number_key is not None:
        return session.scalar(
            select(Patient).where(
                Patient.hospital_number_key == hospital_number_key
            )
        )
    return session.scalar(
        select(Patient).where(
            Patient.name_key == name_key,
            Patient.contact_key == contact_key,
            Patient.hospital_number_key.is_(None),
        )
    )
