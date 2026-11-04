"""Stored evaluation runs: rubric labels beside real Machine Recommendations.

The corpus can be materialised into ordinary Patient/Encounter/Assessment rows.
Those rows are measurement scaffolding: they carry their rubric label in a
column of its own, never in ``machine_recommendation`` or ``final_decision``,
they stay off the working Queue and activity Reports, and the Accuracy
Evaluation Report prefers them when they exist.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import accuracy
from app.assessments import create_triage_assessment
from app.models import Encounter, Patient, TriageAssessment
from app.prioritisation import UrgencyLevel, assess
from app.queue import awaiting_queue
from app.reports import daily_queue, performance, priority_distribution
from evaluation import harness
from evaluation.corpus import load_corpus
from evaluation.materialise import materialise_corpus

RUN_ID = "test-rubric-corpus"


@pytest.fixture
def session(client: TestClient):
    with client.app.state.session_factory() as session:
        yield session


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


def test_materialise_scores_each_encounter_with_the_real_engine(
    client: TestClient, session, corpus
) -> None:
    created = materialise_corpus(
        session, corpus, run_id=RUN_ID, replace=True
    )
    session.commit()

    assert created == corpus.encounter_count
    assert session.scalar(
        select(func.count()).select_from(Encounter).where(
            Encounter.evaluation_run_id == RUN_ID
        )
    ) == corpus.encounter_count

    # The materialiser walks the corpus in order, so the rows pair directly.
    assessments = session.scalars(
        select(TriageAssessment).order_by(TriageAssessment.id)
    ).all()
    assert len(assessments) == corpus.encounter_count
    for assessment, item in zip(assessments, corpus.encounters):
        # The stored recommendation is the real engine's output, and the
        # rubric label lives in its own column.
        assert assessment.machine_recommendation == (
            assess(harness.pipeline_inputs(item)).level.value
        )
        assert assessment.ground_truth_level == (
            item.ground_truth.urgency_level.value
        )
        assert assessment.machine_recommendation in {
            level.value for level in UrgencyLevel
        }


def test_materialise_refuses_a_duplicate_run_unless_replacing(
    client: TestClient, session, corpus
) -> None:
    materialise_corpus(session, corpus, run_id=RUN_ID, replace=True)
    session.commit()

    with pytest.raises(ValueError, match="already has"):
        materialise_corpus(session, corpus, run_id=RUN_ID)

    rebuilt = materialise_corpus(
        session, corpus, run_id=RUN_ID, replace=True
    )
    session.commit()
    assert rebuilt == corpus.encounter_count
    assert session.scalar(
        select(func.count()).select_from(Encounter).where(
            Encounter.evaluation_run_id == RUN_ID
        )
    ) == corpus.encounter_count


def test_evaluation_rows_stay_off_the_queue_and_activity_reports(
    client: TestClient, session, corpus
) -> None:
    materialise_corpus(session, corpus, run_id=RUN_ID, replace=True)
    session.commit()

    now = datetime.now(timezone.utc)
    assert awaiting_queue(session, now) == []
    assert daily_queue(session, now.date()).volume == 0
    assert priority_distribution(session).total == 0
    assert performance(session).completed == 0

    # One live Encounter is the only thing that reaches the working views.
    patient = Patient(
        full_name="Live Patient",
        name_key="live patient",
        age=40,
        sex="female",
        contact_phone="07700 900999",
        contact_key="07700900999",
    )
    session.add(patient)
    session.flush()
    live = Encounter(
        patient_id=patient.id,
        presenting_complaint="Chest pain",
        pain_level=8,
        illness_duration_hours=2,
        temperature_c=37.0,
        heart_rate_bpm=120,
        systolic_bp=110,
        diastolic_bp=70,
        oxygen_saturation_percent=96,
    )
    session.add(live)
    session.flush()
    create_triage_assessment(session, live)
    session.commit()

    assert [entry.encounter.id for entry in awaiting_queue(session, now)] == [
        live.id
    ]
    assert daily_queue(session, now.date()).volume == 1
    assert priority_distribution(session).total == 1
    assert performance(session).completed == 0  # still awaiting


def test_a_stored_evaluation_run_is_preferred_and_labelled(
    client: TestClient, session, corpus
) -> None:
    materialise_corpus(session, corpus, run_id=RUN_ID, replace=True)
    session.commit()

    report = accuracy.build_report(session, None)

    assert report.available is True
    assert len(report.runs) == 1
    run = report.runs[0]
    assert run.source is accuracy.RunSource.evaluation
    assert run.run_mode == "evaluation"
    assert run.dataset == f"stored evaluation run {RUN_ID}"
    assert run.total == corpus.encounter_count

    # The stored figures are the engine's actual pipeline result, not a copy
    # of any artefact.
    scored = harness.score_pipeline(corpus)
    expected = harness.compute_metrics(
        [result.ground_truth for result in scored],
        [result.machine_recommendation for result in scored],
    )
    assert run.accuracy == pytest.approx(expected["accuracy"])
    assert run.correct == sum(
        expected["confusion_matrix"]["rows"][index][index]
        for index in range(3)
    )

    # The API surface labels the stored source, rather than pretending the run
    # came from the offline artefact.
    login = client.post(
        "/api/auth/login",
        json={
            "email": "administrator@example.com",
            "password": "administrator-password",
        },
    )
    assert login.status_code == 200
    payload = client.get(
        "/api/administrator/reports/accuracy-evaluation"
    ).json()
    assert payload["available"] is True
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["source"] == "evaluation"
    assert payload["runs"][0]["run_mode"] == "evaluation"
    assert payload["runs"][0]["total"] == corpus.encounter_count


def test_ground_truth_is_frozen_once_stored(
    client: TestClient, session, corpus
) -> None:
    materialise_corpus(session, corpus, run_id=RUN_ID, replace=True)
    session.commit()

    assessment = session.scalars(select(TriageAssessment)).first()
    assert assessment is not None
    assessment.ground_truth_level = "Low"
    with pytest.raises(ValueError, match="immutable"):
        session.flush()
    session.rollback()
