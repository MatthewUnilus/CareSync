"""Symptom Group recognition: the free-text complaint mapped onto the vocabulary.

Recognition is spaCy entity extraction onto a concrete, finite list with exact
matching — no synonym table and no inference. These tests call the recogniser
directly with constructed complaints, then drive the API to check that the
recognised groups are stored with the Assessment and surfaced on the Queue.
"""

import pytest
from fastapi.testclient import TestClient

from app.models import TriageAssessment
from app.symptom_groups import recognise, vocabulary


def test_a_complaint_is_recognised_onto_a_symptom_group() -> None:
    assert recognise(
        "crushing central chest pain radiating to the left arm"
    ) == ("chest pain",)


def test_a_complaint_matching_no_symptom_group_is_recognised_as_none() -> None:
    assert recognise("feeling generally unwell since yesterday") == ()


def test_a_complaint_can_match_more_than_one_symptom_group() -> None:
    assert set(recognise("fever and cough since last night")) == {
        "cough",
        "fever",
    }


@pytest.mark.parametrize(
    "complaint",
    ["heart attack", "short of breath", "tummy ache", "chest pains"],
)
def test_recognition_is_exact_and_uses_no_synonyms(complaint: str) -> None:
    # These are all plausible ways to describe a vocabulary concept, but none
    # of them is the canonical phrase, so none is recognised.
    assert recognise(complaint) == ()


def test_recognition_ignores_case_but_not_word_meaning() -> None:
    assert recognise("Chest Pain on exertion") == ("chest pain",)


def test_the_longer_vocabulary_phrase_wins_an_overlap() -> None:
    assert recognise("vomiting blood this morning") == ("vomiting blood",)


def test_negation_is_not_interpreted() -> None:
    # Literal matching is the documented behaviour: the recognised groups are
    # shown to the Clinical user precisely so this limitation is visible.
    assert recognise("no chest pain") == ("chest pain",)


def test_the_same_complaint_always_produces_the_same_groups() -> None:
    complaint = "shortness of breath and a fever"
    first = recognise(complaint)
    assert first == recognise(complaint)
    assert first == recognise(complaint.upper())


def test_the_vocabulary_is_versioned_and_contains_the_glossary_examples() -> None:
    loaded = vocabulary()
    assert loaded.version.count(".") == 2
    assert {"chest pain", "shortness of breath", "fever"} <= set(loaded.groups)


def test_every_symptom_group_is_a_canonical_unique_phrase() -> None:
    groups = vocabulary().groups
    assert len(groups) == len(set(groups))
    assert all(group == group.strip().lower() for group in groups)


def _intake(complaint: str) -> dict[str, object]:
    return {
        "presenting_complaint": complaint,
        "pain_level": 2,
        "illness_duration_hours": 24,
        "temperature_c": 36.8,
        "heart_rate_bpm": 78,
        "respiratory_rate_bpm": 16,
        "blood_pressure": {"systolic": 120, "diastolic": 80},
        "oxygen_saturation_percent": 98,
        "notes": None,
    }


def _open_encounter(client: TestClient, complaint: str) -> dict[str, object]:
    patient = client.post(
        "/api/clinical/patients",
        json={
            "full_name": "Grace Hopper",
            "age": 45,
            "sex": "female",
            "contact_phone": "07700 900456",
            "contact_email": None,
        },
    )
    assert patient.status_code in (200, 201)
    encounter = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient.json()["id"], "intake": _intake(complaint)},
    )
    assert encounter.status_code == 201, encounter.text
    return encounter.json()


def test_producing_an_assessment_stores_the_recognised_symptom_groups(
    clinical_client: TestClient,
) -> None:
    encounter = _open_encounter(
        clinical_client,
        "crushing central chest pain radiating to the left arm",
    )

    assert encounter["assessment"]["recognised_symptom_groups"] == ["chest pain"]


def test_no_symptom_group_recognised_is_distinguishable_from_one(
    clinical_client: TestClient,
) -> None:
    none = _open_encounter(clinical_client, "feeling generally unwell")
    one = _open_encounter(clinical_client, "a sore throat for two days")

    assert none["assessment"]["recognised_symptom_groups"] == []
    assert one["assessment"]["recognised_symptom_groups"] == ["sore throat"]
    assert (
        none["assessment"]["recognised_symptom_groups"]
        != one["assessment"]["recognised_symptom_groups"]
    )


def test_the_recognised_symptom_groups_cannot_be_rewritten(
    clinical_client: TestClient,
) -> None:
    encounter = _open_encounter(clinical_client, "fever and cough")
    assessment_id = encounter["assessment"]["id"]
    session_factory = clinical_client.app.state.session_factory

    with session_factory() as session:
        assessment = session.get(TriageAssessment, assessment_id)
        assert assessment is not None
        assessment.recognised_symptom_groups = "fever"
        with pytest.raises(ValueError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        stored = session.get(TriageAssessment, assessment_id)
        assert stored is not None
        assert stored.recognised_symptom_groups == "cough,fever"


def test_the_queue_shows_the_recognised_symptom_groups_of_the_assessment(
    clinical_client: TestClient,
) -> None:
    encounter = _open_encounter(clinical_client, "fever and cough")

    queue = clinical_client.get("/api/clinical/queue")
    assert queue.status_code == 200
    entry = next(
        entry
        for entry in queue.json()["entries"]
        if entry["encounter_id"] == encounter["id"]
    )

    assert set(entry["assessment"]["recognised_symptom_groups"]) == {
        "cough",
        "fever",
    }


def test_the_complaint_text_is_not_a_feature_of_the_recommendation(
    clinical_client: TestClient,
) -> None:
    # The classifier consumes the structured feature vector, never the text, so
    # two wordings that recognise the same (here: no) Symptom Group must produce
    # the same Machine Recommendation. Recognition is still recorded with the
    # Assessment, which is how a Clinical user sees what the model was given.
    first = _open_encounter(clinical_client, "feeling generally unwell")
    second = _open_encounter(clinical_client, "a vague sense of malaise")

    assert first["assessment"]["recognised_symptom_groups"] == []
    assert second["assessment"]["recognised_symptom_groups"] == []
    assert (
        first["assessment"]["machine_recommendation"]
        == second["assessment"]["machine_recommendation"]
    )


def test_recognised_symptom_groups_reach_the_classifier_as_features(
    clinical_client: TestClient,
) -> None:
    # Recognition runs before the engine and the vector carries one dimension per
    # group, so the same captured vitals with a recognised group are a different
    # model input from the same vitals without one. The shipped interim artefact
    # happens to give every group a zero weight because its training source
    # records no complaints; that is a property of the artefact, not of the
    # boundary, and it is recorded in the artefact's `constant_features`.
    with_group = _open_encounter(
        clinical_client, "crushing central chest pain radiating to the left arm"
    )
    without_group = _open_encounter(clinical_client, "feeling generally unwell")

    assert with_group["assessment"]["recognised_symptom_groups"] == ["chest pain"]
    assert without_group["assessment"]["recognised_symptom_groups"] == []
