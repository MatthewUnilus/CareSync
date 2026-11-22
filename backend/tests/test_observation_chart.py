"""The Observation chart, at the API boundary.

Vital signs live in one place: every set is an Observation attached to an
Encounter or an Admission, never both and never neither. These tests drive the
HTTP API — the seam a client uses — for charting a set, reading a Patient's
chart newest-first with each reading's previous value beside it, and the
refusals that guard the record: an Observation is append-only, and a reading
outside its adult resting reference interval is marked for display only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Admission, Observation, User
from app.observations import previous_observation
from app.timeutils import utc_now

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

REASON = "Crushing chest pain since this morning"

#: The reading columns of an Observation row, without a subject. Used to build
#: rows directly where no route can produce the shape under test (the
#: exactly-one-subject constraint on the neither/both cases).
READING_COLUMNS = {
    "pain_level": 4,
    "illness_duration_hours": 12.0,
    "temperature_c": 37.0,
    "heart_rate_bpm": 80,
    "respiratory_rate_bpm": 16,
    "systolic": 120,
    "diastolic": 78,
    "oxygen_saturation_percent": 98,
}


def register_patient(
    client: TestClient, full_name: str = "Ada Lovelace", age: int = 36
) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": full_name,
            "age": age,
            "sex": "female",
            "contact_phone": "07700 900123",
            "contact_email": None,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def open_encounter(client: TestClient, patient_id: int) -> int:
    response = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient_id, "intake": {"presenting_complaint": REASON}},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def admit(
    client: TestClient,
    patient_id: int,
    ward: str = "Ward A",
    bed: str = "3",
) -> int:
    """Insert an Admission directly.

    Ticket 31 owns the admission routes and the ward board, so until they land
    an Admission is written only by a fixture. The chart's admission seam is
    still exercised over HTTP, which is the seam a client uses.
    """
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        admission = Admission(patient_id=patient_id, ward=ward, bed=bed)
        session.add(admission)
        session.commit()
        return admission.id


def discharge(client: TestClient, admission_id: int) -> None:
    """Set a stay's discharge instant directly.

    Ticket 31 owns the discharge route; until it lands the instant is written
    here so the chart's closed-stay refusal can be exercised over HTTP.
    """
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        admission = session.get(Admission, admission_id)
        assert admission is not None
        admission.discharged_at = utc_now()
        session.commit()


def readings(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pain_level": 4,
        "illness_duration_hours": 12,
        "temperature_c": 37.0,
        "heart_rate_bpm": 80,
        "respiratory_rate_bpm": 16,
        "blood_pressure": {"systolic": 120, "diastolic": 78},
        "oxygen_saturation_percent": 98,
        "notes": "Comfortable, no distress",
    }
    data.update(overrides)
    return data


def chart(client: TestClient, encounter_id: int, **overrides: Any):
    return client.post(
        f"/api/clinical/encounters/{encounter_id}/observations",
        json=readings(**overrides),
    )


def chart_admission(client: TestClient, admission_id: int, **overrides: Any):
    return client.post(
        f"/api/clinical/admissions/{admission_id}/observations",
        json=readings(**overrides),
    )


def chart_of(client: TestClient, patient_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/clinical/patients/{patient_id}/observations")
    assert response.status_code == 200, response.text
    return response.json()["observations"]


def audit_actions(client: TestClient) -> list[str]:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200
    response = client.get("/api/administrator/audit-log")
    assert response.status_code == 200, response.text
    return [entry["action"] for entry in response.json()["entries"]]


def test_charting_an_observation_against_an_encounter(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    response = chart(clinical_client, encounter_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["encounter_id"] == encounter_id
    assert body["admission_id"] is None
    assert body["blood_pressure"] == {"systolic": 120, "diastolic": 78}
    assert body["notes"] == "Comfortable, no distress"
    assert body["previous"] is None


def test_charting_an_observation_against_an_admission(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = chart_admission(clinical_client, admission_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["admission_id"] == admission_id
    assert body["encounter_id"] is None


def test_an_unknown_field_is_refused_rather_than_ignored(
    clinical_client: TestClient,
) -> None:
    """A typo'd reading is refused, not silently dropped.

    An unknown key must not be accepted as if it had been charted: a client that
    misspells ``heart_rate_bpm`` would otherwise believe the value was recorded.
    Both the visit and the stay edges of the chart refuse it with a ``422``.
    """
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    admission_id = admit(clinical_client, patient_id)

    visit_response = chart(clinical_client, encounter_id, heart_rate=80)
    stay_response = chart_admission(clinical_client, admission_id, heart_rate=80)

    assert visit_response.status_code == 422, visit_response.text
    assert stay_response.status_code == 422, stay_response.text
    # Nothing was charted from either refused set.
    assert chart_of(clinical_client, patient_id) == []


def test_charting_against_an_ended_visit_is_refused(
    clinical_client: TestClient,
) -> None:
    """A visit that has ended takes no new sets: 409, and nothing is recorded."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    ended = clinical_client.post(f"/api/clinical/encounters/{encounter_id}/end")
    assert ended.status_code == 200, ended.text

    response = chart(clinical_client, encounter_id)

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": (
            "An Encounter that has already ended cannot take new Observations"
        )
    }
    # No set was charted, so the chart stays empty and no chart entry was written.
    assert chart_of(clinical_client, patient_id) == []
    assert "chart_observation" not in audit_actions(clinical_client)


def test_charting_against_a_discharged_admission_is_refused(
    clinical_client: TestClient,
) -> None:
    """A discharged stay takes no new sets: 409, and nothing is recorded."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    discharge(clinical_client, admission_id)

    response = chart_admission(clinical_client, admission_id)

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "A discharged Admission cannot take new Observations"
    }
    assert chart_of(clinical_client, patient_id) == []


def test_an_ended_visit_still_shows_its_charted_history(
    clinical_client: TestClient,
) -> None:
    """The read side is untouched: an ended visit still shows what was charted."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    charted = chart(clinical_client, encounter_id).json()
    ended = clinical_client.post(f"/api/clinical/encounters/{encounter_id}/end")
    assert ended.status_code == 200, ended.text

    observations = chart_of(clinical_client, patient_id)

    assert [item["id"] for item in observations] == [charted["id"]]


def test_a_discharged_admission_still_shows_its_charted_history(
    clinical_client: TestClient,
) -> None:
    """A discharged stay keeps its history, it only leaves the working views."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    charted = chart_admission(clinical_client, admission_id).json()
    discharge(clinical_client, admission_id)

    observations = chart_of(clinical_client, patient_id)

    assert [item["id"] for item in observations] == [charted["id"]]
    assert observations[0]["admission_id"] == admission_id


def test_a_charted_observation_is_attributed_and_time_stamped(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id).json()

    assert body["actor"]["display_name"] == "Clinical Demo User"
    assert body["actor"]["id"] > 0
    # The server speaks an aware UTC instant, not a bare local timestamp.
    assert datetime.fromisoformat(body["taken_at"]).tzinfo is not None


def test_a_chart_lists_observations_newest_first_with_the_previous_reading(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    first = chart(clinical_client, encounter_id, heart_rate_bpm=80).json()
    second = chart(clinical_client, encounter_id, heart_rate_bpm=92).json()
    third = chart(clinical_client, encounter_id, heart_rate_bpm=104).json()

    # The charting response itself carries the preceding reading beside the new
    # one, so the just-charted set can be compared without a second read.
    assert first["previous"] is None
    assert second["previous"]["heart_rate_bpm"] == 80
    assert third["previous"]["heart_rate_bpm"] == 92

    observations = chart_of(clinical_client, patient_id)

    assert [item["id"] for item in observations] == [
        third["id"],
        second["id"],
        first["id"],
    ]
    # Each reading sits beside the one taken before it, so the direction of
    # travel is visible without reading back to the previous row.
    assert observations[0]["previous"]["heart_rate_bpm"] == 92
    assert observations[0]["previous"]["taken_at"] == second["taken_at"]
    assert observations[1]["previous"]["heart_rate_bpm"] == 80
    assert observations[2]["previous"] is None
    # The previous value is readings only, not another whole Observation.
    assert "id" not in observations[0]["previous"]


def test_an_empty_chart_returns_no_observations(
    clinical_client: TestClient,
) -> None:
    """An empty chart says so; it does not invent a row of zeros."""
    patient_id = register_patient(clinical_client)

    assert chart_of(clinical_client, patient_id) == []


def test_charting_writes_one_audit_entry_against_the_visit(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    assert chart(clinical_client, encounter_id).status_code == 201

    assert audit_actions(clinical_client) == [
        "register_patient",
        "open_encounter",
        "chart_observation",
    ]


def test_an_observation_cannot_be_edited_after_it_is_written(
    clinical_client: TestClient,
) -> None:
    """Append-only at the application layer (ADR 0001, no database triggers)."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    observation_id = chart(clinical_client, encounter_id).json()["id"]

    # There is no public edit route: the chart's collection path answers no
    # method that would rewrite a saved set.
    collection = f"/api/clinical/patients/{patient_id}/observations"
    assert clinical_client.put(collection, json={}).status_code == 405
    assert clinical_client.delete(collection).status_code == 405

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(Observation, observation_id)
        assert stored is not None
        stored.temperature_c = 39.5
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(Observation, observation_id)
        assert stored is not None
        assert stored.temperature_c == 37.0


def test_an_observation_must_attach_to_exactly_one_subject(
    clinical_client: TestClient,
) -> None:
    """Neither subject, or both, is refused by the database constraint."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    admission_id = admit(clinical_client, patient_id)
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        actor = session.scalar(select(User).where(User.role == "clinical"))
        assert actor is not None
        # Neither an Encounter nor an Admission: the chart has no home.
        session.add(
            Observation(patient_id=patient_id, actor=actor, **READING_COLUMNS)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        actor = session.scalar(select(User).where(User.role == "clinical"))
        assert actor is not None
        # Both at once: the set cannot belong to a visit and a stay together.
        session.add(
            Observation(
                patient_id=patient_id,
                actor=actor,
                encounter_id=encounter_id,
                admission_id=admission_id,
                **READING_COLUMNS,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    assert chart_of(clinical_client, patient_id) == []


BOUNDARY_REJECTIONS: list[dict[str, Any]] = [
    {"pain_level": 11},
    {"pain_level": 0},
    {"illness_duration_hours": 8761},
    {"illness_duration_hours": -1},
    {"temperature_c": 45.1},
    {"temperature_c": 29.9},
    {"heart_rate_bpm": 301},
    {"heart_rate_bpm": 19},
    {"respiratory_rate_bpm": 81},
    {"respiratory_rate_bpm": -1},
    {"blood_pressure": {"systolic": 301, "diastolic": 100}},
    {"blood_pressure": {"systolic": 49, "diastolic": 40}},
    {"blood_pressure": {"systolic": 120, "diastolic": 201}},
    {"blood_pressure": {"systolic": 120, "diastolic": 19}},
    {"blood_pressure": {"systolic": 80, "diastolic": 90}},
    {"oxygen_saturation_percent": 101},
    {"oxygen_saturation_percent": 49},
]


@pytest.mark.parametrize("override", BOUNDARY_REJECTIONS)
def test_each_reading_boundary_is_rejected_above_and_below(
    clinical_client: TestClient, override: dict[str, Any]
) -> None:
    """The intake bounds survive unchanged: a reading out of range is a 422."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    response = chart(clinical_client, encounter_id, **override)

    assert response.status_code == 422, response.text
    # The refused set was not recorded.
    assert chart_of(clinical_client, patient_id) == []


#: A value one step BELOW its adult resting interval, and the field marked.
BELOW_RANGE: list[tuple[dict[str, Any], str]] = [
    ({"temperature_c": 36.4}, "temperature_c"),
    ({"heart_rate_bpm": 59}, "heart_rate_bpm"),
    ({"respiratory_rate_bpm": 11}, "respiratory_rate_bpm"),
    ({"blood_pressure": {"systolic": 89, "diastolic": 60}}, "blood_pressure"),
    ({"blood_pressure": {"systolic": 100, "diastolic": 59}}, "blood_pressure"),
    ({"oxygen_saturation_percent": 94}, "oxygen_saturation_percent"),
]

#: A value one step ABOVE its adult resting interval, and the field marked.
#: Oxygen saturation has no above case: its interval tops out at 100, which is
#: also the intake bound, so a higher value is refused by validation instead.
ABOVE_RANGE: list[tuple[dict[str, Any], str]] = [
    ({"temperature_c": 37.4}, "temperature_c"),
    ({"heart_rate_bpm": 101}, "heart_rate_bpm"),
    ({"respiratory_rate_bpm": 19}, "respiratory_rate_bpm"),
    ({"blood_pressure": {"systolic": 121, "diastolic": 70}}, "blood_pressure"),
    ({"blood_pressure": {"systolic": 110, "diastolic": 81}}, "blood_pressure"),
]


@pytest.mark.parametrize("override,field", BELOW_RANGE + ABOVE_RANGE)
def test_a_reading_outside_its_reference_interval_is_marked(
    clinical_client: TestClient, override: dict[str, Any], field: str
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id, **override).json()

    assert body["abnormal_fields"] == [field]


#: A value sitting exactly on each adult interval boundary. The interval is
#: inclusive at both ends, so a boundary value is normal and nothing is marked.
AT_BOUNDARY: list[dict[str, Any]] = [
    {"temperature_c": 36.5},
    {"temperature_c": 37.3},
    {"heart_rate_bpm": 60},
    {"heart_rate_bpm": 100},
    {"respiratory_rate_bpm": 12},
    {"respiratory_rate_bpm": 18},
    {"blood_pressure": {"systolic": 90, "diastolic": 60}},
    {"blood_pressure": {"systolic": 120, "diastolic": 80}},
    {"oxygen_saturation_percent": 95},
    {"oxygen_saturation_percent": 100},
]


@pytest.mark.parametrize("override", AT_BOUNDARY)
def test_a_reading_on_its_reference_interval_boundary_is_not_marked(
    clinical_client: TestClient, override: dict[str, Any]
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id, **override).json()

    assert body["abnormal_fields"] == []


def test_oxygen_saturation_above_its_interval_is_refused_by_the_intake_bound(
    clinical_client: TestClient,
) -> None:
    """SpO2 tops out at 100, which is also the intake bound, so 101 is a 422."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    response = chart(clinical_client, encounter_id, oxygen_saturation_percent=101)

    assert response.status_code == 422, response.text


#: One set with every reading outside its interval at once.
MIXED_ABNORMAL: dict[str, Any] = {
    "temperature_c": 38.0,
    "heart_rate_bpm": 110,
    "respiratory_rate_bpm": 22,
    "blood_pressure": {"systolic": 150, "diastolic": 95},
    "oxygen_saturation_percent": 90,
}

MIXED_ABNORMAL_FIELDS = [
    "temperature_c",
    "heart_rate_bpm",
    "respiratory_rate_bpm",
    "blood_pressure",
    "oxygen_saturation_percent",
]


def test_a_fully_normal_set_is_marked_nothing(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id).json()

    assert body["abnormal_fields"] == []


def test_a_set_abnormal_in_every_reading_marks_each_field(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id, **MIXED_ABNORMAL).json()

    assert body["abnormal_fields"] == MIXED_ABNORMAL_FIELDS


def test_an_abnormal_mark_does_not_change_the_recorded_value(
    clinical_client: TestClient,
) -> None:
    """Display only (ADR 0010): the value is returned and stored as sent."""
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id, **MIXED_ABNORMAL).json()

    assert body["temperature_c"] == MIXED_ABNORMAL["temperature_c"]
    assert body["blood_pressure"] == MIXED_ABNORMAL["blood_pressure"]
    # And the value as it comes back from the chart is the value that was sent.
    stored = chart_of(clinical_client, patient_id)[0]
    assert stored["temperature_c"] == MIXED_ABNORMAL["temperature_c"]
    assert stored["heart_rate_bpm"] == MIXED_ABNORMAL["heart_rate_bpm"]
    assert stored["blood_pressure"] == MIXED_ABNORMAL["blood_pressure"]
    assert stored["oxygen_saturation_percent"] == (
        MIXED_ABNORMAL["oxygen_saturation_percent"]
    )
    assert stored["abnormal_fields"] == MIXED_ABNORMAL_FIELDS


def test_an_adult_is_marked_against_the_adult_ranges(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id).json()

    assert body["reference_range_applies"] is True
    assert body["reference_range_note"] is None


def test_a_pediatric_patient_is_not_marked_against_adult_ranges(
    clinical_client: TestClient,
) -> None:
    """The adult intervals are not a child's normal, so a child is not marked."""
    patient_id = register_patient(clinical_client, age=12)
    encounter_id = open_encounter(clinical_client, patient_id)

    body = chart(clinical_client, encounter_id, **MIXED_ABNORMAL).json()

    assert body["reference_range_applies"] is False
    assert body["abnormal_fields"] == []
    assert isinstance(body["reference_range_note"], str)
    assert body["reference_range_note"]
    # The readings are still returned unchanged; only the marks are withheld.
    assert body["temperature_c"] == MIXED_ABNORMAL["temperature_c"]


def test_readings_taken_at_the_same_instant_are_ordered_by_id(
    clinical_client: TestClient,
) -> None:
    """Two sets at one instant read in a stable order: the higher id is newer.

    The instant is written by the server, so the tie is forced here by writing
    two rows directly. The chart still reads them deterministically and places
    the lower id as the previous set.
    """
    patient_id = register_patient(clinical_client)
    encounter_id = open_encounter(clinical_client, patient_id)
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        actor = session.scalar(select(User).where(User.role == "clinical"))
        assert actor is not None
        shared = utc_now()
        earlier = Observation(
            patient_id=patient_id,
            encounter_id=encounter_id,
            actor=actor,
            taken_at=shared,
            **{**READING_COLUMNS, "heart_rate_bpm": 80},
        )
        session.add(earlier)
        session.flush()
        earlier_id = earlier.id
        later = Observation(
            patient_id=patient_id,
            encounter_id=encounter_id,
            actor=actor,
            taken_at=shared,
            **{**READING_COLUMNS, "heart_rate_bpm": 92},
        )
        session.add(later)
        session.flush()
        later_id = later.id
        # The SQL helper the charting response uses applies the same tie-break:
        # at a shared instant the lower id is the previous set, and the lower id
        # has no previous of its own.
        assert previous_observation(session, later) is earlier
        assert previous_observation(session, earlier) is None
        session.commit()

    observations = chart_of(clinical_client, patient_id)

    assert [item["id"] for item in observations] == [later_id, earlier_id]
    assert observations[0]["previous"]["heart_rate_bpm"] == 80
    assert observations[0]["previous"]["taken_at"] == observations[0]["taken_at"]
    assert observations[1]["previous"] is None


def test_charting_against_an_unknown_visit_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = chart(clinical_client, 999_999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Encounter not found"}


def test_charting_against_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = chart_admission(clinical_client, 999_999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Admission not found"}


def test_the_chart_of_an_unknown_patient_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/clinical/patients/999999/observations")

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_an_administrator_cannot_chart_or_read_observations(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    patient_id = register_patient(client)
    encounter_id = open_encounter(client, patient_id)

    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    charted = chart(client, encounter_id)
    read = client.get(f"/api/clinical/patients/{patient_id}/observations")

    for response in (charted, read):
        assert response.status_code == 403
        assert response.json() == {"detail": "Role not permitted"}


def test_observation_routes_require_authentication(client: TestClient) -> None:
    assert chart(client, 1).status_code == 401
    assert chart_admission(client, 1).status_code == 401
    assert client.get("/api/clinical/patients/1/observations").status_code == 401
