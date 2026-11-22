"""Ticket 32: nursing notes from a template, with the latest vitals prefilled.

These tests drive the API a nurse uses. A note is written against an Admission
from one of five templates, its fields are free text stored one row each, and a
new note may prefill from the patient's latest Observation so the vitals are
already there. A correction is a new note that points at the one it corrects and
leaves the original in the record. Notes read back oldest-first, the board's
outstanding counts are unaffected, and every note written or corrected appends
exactly one audit entry in the same transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.audit_actions import AuditAction
from app.models import Admission, AuditEntry, NursingNote

CLINICAL_AUDIT_ACTOR = "Clinical Demo User"

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

#: The five templates and their exact field vocabulary, in template order. Every
#: template carries a ``vital_signs`` field for the prefill to land in.
EXPECTED_TEMPLATES: dict[str, list[str]] = {
    "shift_assessment": [
        "vital_signs",
        "general_condition",
        "mobility",
        "skin",
        "pain",
        "intake_output",
    ],
    "ward_round_entry": [
        "vital_signs",
        "current_issue",
        "findings",
        "plan",
        "review_due",
    ],
    "intervention_record": [
        "vital_signs",
        "intervention",
        "indication",
        "response",
    ],
    "handover_entry": [
        "vital_signs",
        "situation",
        "background",
        "current_state",
        "watch",
    ],
    "discharge_summary": [
        "vital_signs",
        "stay_summary",
        "treatment_given",
        "state_at_discharge",
        "follow_up",
    ],
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


def admit(
    client: TestClient,
    patient_id: int,
    ward: str = "Ward A",
    bed: str = "3",
) -> int:
    response = client.post(
        "/api/ward/admissions",
        json={
            "patient_id": patient_id,
            "ward": ward,
            "bed": bed,
            "encounter_id": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def discharge(client: TestClient, admission_id: int):
    return client.post(f"/api/ward/admissions/{admission_id}/discharge")


def readings(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "pain_level": 4,
        "illness_duration_hours": 12,
        "temperature_c": 37.0,
        "heart_rate_bpm": 80,
        "respiratory_rate_bpm": 16,
        "blood_pressure": {"systolic": 120, "diastolic": 78},
        "oxygen_saturation_percent": 98,
        "notes": None,
    }
    data.update(overrides)
    return data


def chart_admission(client: TestClient, admission_id: int, **overrides: Any):
    return client.post(
        f"/api/clinical/admissions/{admission_id}/observations",
        json=readings(**overrides),
    )


def templates(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/ward/note-templates")
    assert response.status_code == 200, response.text
    return response.json()["templates"]


def prefill(client: TestClient, admission_id: int, template_key: str):
    return client.get(
        f"/api/ward/admissions/{admission_id}/note-prefill",
        params={"template_key": template_key},
    )


def write_note(
    client: TestClient,
    admission_id: int,
    template_key: str,
    fields: list[dict[str, str]],
    corrects_note_id: int | None = None,
):
    return client.post(
        f"/api/ward/admissions/{admission_id}/notes",
        json={
            "template_key": template_key,
            "fields": fields,
            "corrects_note_id": corrects_note_id,
        },
    )


def notes(client: TestClient, admission_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/ward/admissions/{admission_id}/notes")
    assert response.status_code == 200, response.text
    return response.json()["notes"]


def fields_for(
    template_key: str, value_prefix: str = "value", **overrides: str
) -> list[dict[str, str]]:
    """A full field set for a template: every key, exactly once.

    A note must carry every field its template defines, so the stored shape is one
    row per template field. ``overrides`` replace a named field's value; the rest
    get a placeholder. An override to the empty string proves a field may be left
    blank (free text is optional to fill in).
    """
    return [
        {"key": key, "value": overrides.get(key, f"{value_prefix} {key}")}
        for key in EXPECTED_TEMPLATES[template_key]
    ]


def login_as_administrator(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert response.status_code == 200


def audit_log(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    login_as_administrator(client)
    response = client.get("/api/administrator/audit-log", params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def actions(entries: list[dict[str, Any]]) -> list[str]:
    return [entry["action"] for entry in entries]


# --------------------------------------------------------------------------- #
# The template vocabulary
# --------------------------------------------------------------------------- #


def test_the_template_route_serves_the_five_templates_with_their_fields(
    clinical_client: TestClient,
) -> None:
    served = templates(clinical_client)

    assert [item["key"] for item in served] == list(EXPECTED_TEMPLATES)
    for item in served:
        assert item["label"]
        assert [field["key"] for field in item["fields"]] == EXPECTED_TEMPLATES[
            item["key"]
        ]
        for field in item["fields"]:
            assert field["label"]


def test_every_template_carries_a_vital_signs_field(
    clinical_client: TestClient,
) -> None:
    for item in templates(clinical_client):
        assert "vital_signs" in [field["key"] for field in item["fields"]]


def test_the_prefilled_field_is_labelled_as_readings(
    clinical_client: TestClient,
) -> None:
    """The prefill carries pain and illness duration too, so its label is
    "readings" rather than a clinical "vital signs" label. The client reads the
    label from here, so the wording lives in one place."""
    for item in templates(clinical_client):
        label = next(
            field["label"]
            for field in item["fields"]
            if field["key"] == "vital_signs"
        )
        assert "reading" in label.lower()
        assert "vital sign" not in label.lower()


# --------------------------------------------------------------------------- #
# The prefill
# --------------------------------------------------------------------------- #


def test_the_prefill_carries_the_latest_observations_values(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    charted = chart_admission(
        clinical_client,
        admission_id,
        temperature_c=37.0,
        heart_rate_bpm=80,
        respiratory_rate_bpm=16,
    ).json()

    response = prefill(clinical_client, admission_id, "shift_assessment")

    assert response.status_code == 200, response.text
    body = response.json()
    vital_signs = body["fields"]["vital_signs"]
    # The exact recorded numbers, labelled, in the free text.
    assert "Temperature 37.0 C" in vital_signs
    assert "Heart rate 80 bpm" in vital_signs
    assert "Respiratory rate 16 /min" in vital_signs
    assert "Blood pressure 120/78 mmHg" in vital_signs
    assert "Oxygen saturation 98 %" in vital_signs
    # Pain and illness duration are readings the prefill includes too, so the
    # field is a set of readings rather than only clinical vital signs.
    assert "Pain 4/10" in vital_signs
    assert "Illness duration 12.0 h" in vital_signs
    # The source stamp, so the nurse can see where the numbers came from.
    assert CLINICAL_AUDIT_ACTOR in vital_signs
    source = body["source_observation"]
    assert source["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert datetime.fromisoformat(source["taken_at"]) == datetime.fromisoformat(
        charted["taken_at"]
    )


def test_the_prefill_uses_the_most_recent_observation(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    chart_admission(clinical_client, admission_id, heart_rate_bpm=80)
    latest = chart_admission(clinical_client, admission_id, heart_rate_bpm=96).json()

    body = prefill(clinical_client, admission_id, "shift_assessment").json()

    assert "Heart rate 96 bpm" in body["fields"]["vital_signs"]
    assert datetime.fromisoformat(body["source_observation"]["taken_at"]) == (
        datetime.fromisoformat(latest["taken_at"])
    )


def test_the_prefill_is_empty_when_nothing_is_charted(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    body = prefill(clinical_client, admission_id, "handover_entry").json()

    assert body["fields"] == {}
    assert body["source_observation"] is None


def test_the_prefill_of_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = prefill(clinical_client, 999_999, "shift_assessment")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


def test_the_prefill_of_an_unknown_template_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = prefill(clinical_client, admission_id, "not_a_template")

    assert response.status_code == 422, response.text


def test_a_note_can_be_written_from_the_prefilled_values(
    clinical_client: TestClient,
) -> None:
    """The headline behaviour: the vitals arrive in the note, not retyped."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    chart_admission(clinical_client, admission_id, heart_rate_bpm=88)
    prefilled = prefill(clinical_client, admission_id, "shift_assessment").json()

    created = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for(
            "shift_assessment",
            vital_signs=prefilled["fields"]["vital_signs"],
            general_condition="Comfortable at rest",
        ),
    )
    assert created.status_code == 201, created.text

    (stored,) = notes(clinical_client, admission_id)
    stored_fields = {field["key"]: field["value"] for field in stored["fields"]}
    assert stored_fields["vital_signs"] == prefilled["fields"]["vital_signs"]
    assert "Heart rate 88 bpm" in stored_fields["vital_signs"]


# --------------------------------------------------------------------------- #
# Writing and reading a note
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("template_key", list(EXPECTED_TEMPLATES))
def test_a_note_from_each_template_saves_and_reads_back_with_its_fields(
    clinical_client: TestClient,
    template_key: str,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    fields = fields_for(template_key)

    created = write_note(clinical_client, admission_id, template_key, fields)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["admission_id"] == admission_id
    assert body["template_key"] == template_key
    assert body["author"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert body["corrects_note_id"] is None
    assert body["corrected_by_note_id"] is None
    assert body["fields"] == fields

    (stored,) = notes(clinical_client, admission_id)
    assert stored == body


def test_fields_read_back_in_template_order(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    # Sent deliberately out of template order.
    shuffled = list(reversed(fields_for("handover_entry")))

    created = write_note(
        clinical_client, admission_id, "handover_entry", shuffled
    )

    assert created.status_code == 201, created.text
    assert [field["key"] for field in created.json()["fields"]] == (
        EXPECTED_TEMPLATES["handover_entry"]
    )


def test_a_patients_notes_read_oldest_first(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    first = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment", "first"),
    ).json()
    second = write_note(
        clinical_client,
        admission_id,
        "intervention_record",
        fields_for("intervention_record", "second"),
    ).json()
    third = write_note(
        clinical_client,
        admission_id,
        "handover_entry",
        fields_for("handover_entry", "third"),
    ).json()

    assert [note["id"] for note in notes(clinical_client, admission_id)] == [
        first["id"],
        second["id"],
        third["id"],
    ]


def test_one_admissions_notes_do_not_include_another_admissions(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    first = admit(clinical_client, patient_id, bed="1")
    second = admit(clinical_client, patient_id, bed="2")
    kept = write_note(
        clinical_client, first, "shift_assessment", fields_for("shift_assessment")
    ).json()

    assert [note["id"] for note in notes(clinical_client, first)] == [kept["id"]]
    assert notes(clinical_client, second) == []


def test_an_unknown_field_key_is_refused_rather_than_stored(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    fields = fields_for("shift_assessment") + [{"key": "not_a_field", "value": "x"}]

    response = write_note(clinical_client, admission_id, "shift_assessment", fields)

    assert response.status_code == 422, response.text
    assert notes(clinical_client, admission_id) == []


def test_a_duplicate_field_key_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    fields = fields_for("shift_assessment") + [{"key": "pain", "value": "again"}]

    response = write_note(clinical_client, admission_id, "shift_assessment", fields)

    assert response.status_code == 422, response.text
    assert notes(clinical_client, admission_id) == []


def test_a_missing_template_field_is_refused(
    clinical_client: TestClient,
) -> None:
    """Every template field must be present, so the stored shape is stable."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    fields = fields_for("shift_assessment")[:-1]

    response = write_note(clinical_client, admission_id, "shift_assessment", fields)

    assert response.status_code == 422, response.text
    assert notes(clinical_client, admission_id) == []


def test_a_field_may_be_left_blank(
    clinical_client: TestClient,
) -> None:
    """Free text is optional to fill in: the key is present, the value is empty."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    fields = fields_for("shift_assessment", pain="")

    response = write_note(clinical_client, admission_id, "shift_assessment", fields)

    assert response.status_code == 201, response.text
    (stored,) = notes(clinical_client, admission_id)
    assert {field["key"]: field["value"] for field in stored["fields"]}["pain"] == ""


def test_a_stored_note_carries_one_row_per_template_field(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    created = write_note(
        clinical_client, admission_id, "handover_entry", fields_for("handover_entry")
    )

    assert created.status_code == 201, created.text
    assert [field["key"] for field in created.json()["fields"]] == (
        EXPECTED_TEMPLATES["handover_entry"]
    )


def test_writing_a_note_against_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = write_note(
        clinical_client, 999_999, "shift_assessment", fields_for("shift_assessment")
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


def test_writing_a_note_from_an_unknown_template_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = write_note(
        clinical_client, admission_id, "not_a_template", [{"key": "x", "value": "y"}]
    )

    assert response.status_code == 422, response.text


def test_reading_notes_of_an_unknown_admission_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get("/api/ward/admissions/999999/notes")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Admission not found"}


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #


def test_a_correction_appends_a_note_that_leaves_the_original_in_place(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    original_fields = fields_for("shift_assessment", pain="3")
    original = write_note(
        clinical_client, admission_id, "shift_assessment", original_fields
    ).json()

    correction = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment", pain="6"),
        corrects_note_id=original["id"],
    )

    assert correction.status_code == 201, correction.text
    corrected = correction.json()
    assert corrected["corrects_note_id"] == original["id"]
    assert corrected["corrected_by_note_id"] is None

    stored = {note["id"]: note for note in notes(clinical_client, admission_id)}
    # The original is not edited and not removed; it shows it was corrected.
    assert stored[original["id"]]["fields"] == original_fields
    assert stored[original["id"]]["corrected_by_note_id"] == corrected["id"]
    assert stored[corrected["id"]]["corrects_note_id"] == original["id"]


def test_a_correction_of_an_unknown_note_is_not_found(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    response = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment"),
        corrects_note_id=999_999,
    )

    assert response.status_code == 404, response.text


def test_a_correction_must_name_a_note_on_the_same_admission(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    first = admit(clinical_client, patient_id, bed="1")
    second = admit(clinical_client, patient_id, bed="2")
    other_note = write_note(
        clinical_client, first, "shift_assessment", fields_for("shift_assessment")
    ).json()

    response = write_note(
        clinical_client,
        second,
        "shift_assessment",
        fields_for("shift_assessment", pain="6"),
        corrects_note_id=other_note["id"],
    )

    assert response.status_code == 409, response.text


def test_a_correction_must_use_the_same_template(
    clinical_client: TestClient,
) -> None:
    """A correction restates the same document, so its template may not change."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    original = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    ).json()

    response = write_note(
        clinical_client,
        admission_id,
        "handover_entry",
        fields_for("handover_entry"),
        corrects_note_id=original["id"],
    )

    assert response.status_code == 409, response.text
    assert len(notes(clinical_client, admission_id)) == 1


def test_a_note_already_corrected_cannot_be_corrected_again(
    clinical_client: TestClient,
) -> None:
    """The correction link is one-directional and singular."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    original = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    ).json()
    write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment", pain="6"),
        corrects_note_id=original["id"],
    )

    response = write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment", pain="7"),
        corrects_note_id=original["id"],
    )

    assert response.status_code == 409, response.text
    assert len(notes(clinical_client, admission_id)) == 2


# --------------------------------------------------------------------------- #
# A closed stay
# --------------------------------------------------------------------------- #


def test_an_ordinary_note_on_a_discharged_stay_is_refused(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    )

    assert response.status_code == 409, response.text
    assert notes(clinical_client, admission_id) == []


def test_a_discharge_summary_may_be_written_on_a_closed_stay(
    clinical_client: TestClient,
) -> None:
    """The summary records the stay and the state at leaving, so it follows discharge."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = write_note(
        clinical_client, admission_id, "discharge_summary", fields_for("discharge_summary")
    )

    assert response.status_code == 201, response.text
    assert response.json()["template_key"] == "discharge_summary"


def test_the_prefill_of_a_discharged_stay_still_returns_the_readings(
    clinical_client: TestClient,
) -> None:
    """Reading the prefill is read-only, so it works on a stay that has ended."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    chart_admission(clinical_client, admission_id, heart_rate_bpm=88)
    assert discharge(clinical_client, admission_id).status_code == 200

    response = prefill(clinical_client, admission_id, "discharge_summary")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "Heart rate 88 bpm" in body["fields"]["vital_signs"]
    assert body["source_observation"] is not None


# --------------------------------------------------------------------------- #
# The board and the audit log
# --------------------------------------------------------------------------- #


def test_the_board_is_unaffected_by_notes(
    clinical_client: TestClient,
) -> None:
    """A note is not outstanding work, so the board's counts do not move."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    before = clinical_client.get("/api/ward/board").json()["admissions"]

    write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    )
    write_note(
        clinical_client, admission_id, "intervention_record", fields_for("intervention_record")
    )

    after = clinical_client.get("/api/ward/board").json()["admissions"]
    assert after == before
    (row,) = after
    assert row["outstanding_medication_count"] == 0
    assert row["overdue_medication_count"] == 0
    assert row["due_medication_count"] == 0
    assert row["open_task_count"] == 0
    assert row["unreviewed_result_count"] == 0


def test_writing_a_note_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)

    write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    )

    entries = [
        entry
        for entry in audit_log(clinical_client, admission_id=admission_id)
        if entry["action"] == AuditAction.write_nursing_note.value
    ]
    (entry,) = entries
    assert entry["actor"]["display_name"] == CLINICAL_AUDIT_ACTOR
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Nursing note written"


def test_correcting_a_note_appends_one_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    original = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    ).json()

    write_note(
        clinical_client,
        admission_id,
        "shift_assessment",
        fields_for("shift_assessment", pain="6"),
        corrects_note_id=original["id"],
    )

    entries = [
        entry
        for entry in audit_log(clinical_client, admission_id=admission_id)
        if entry["action"] == AuditAction.correct_nursing_note.value
    ]
    (entry,) = entries
    assert entry["patient_id"] == patient_id
    assert entry["admission_id"] == admission_id
    assert entry["action_label"] == "Nursing note corrected"


def test_a_refused_note_writes_no_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    assert discharge(clinical_client, admission_id).status_code == 200

    refused = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    )
    assert refused.status_code == 409, refused.text

    assert (
        AuditAction.write_nursing_note.value
        not in actions(audit_log(clinical_client, admission_id=admission_id))
    )


# --------------------------------------------------------------------------- #
# Append-only
# --------------------------------------------------------------------------- #


def test_a_note_cannot_be_edited_after_it_is_written(
    clinical_client: TestClient,
) -> None:
    """Append-only at the application layer (ADR 0001, no database triggers)."""
    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    note_id = write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    ).json()["id"]

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        stored = session.get(NursingNote, note_id)
        assert stored is not None
        stored.template_key = "handover_entry"
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(NursingNote, note_id)
        assert stored is not None
        assert stored.template_key == "shift_assessment"


def test_note_row_counts_are_one_note_and_one_row_per_field(
    clinical_client: TestClient,
) -> None:
    from app.models import NursingNoteField

    patient_id = register_patient(clinical_client)
    admission_id = admit(clinical_client, patient_id)
    write_note(
        clinical_client, admission_id, "shift_assessment", fields_for("shift_assessment")
    )

    session_factory = clinical_client.app.state.session_factory
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(NursingNote)) == 1
        assert session.scalar(select(func.count()).select_from(NursingNoteField)) == len(
            EXPECTED_TEMPLATES["shift_assessment"]
        )
        assert session.scalar(select(func.count()).select_from(Admission)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEntry)) >= 1
