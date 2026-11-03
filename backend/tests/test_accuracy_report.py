"""The Accuracy Evaluation Report, exercised at the read model and API seams.

Every accuracy figure is computed from stored ``TriageAssessment`` rows. The
ground-truth label comes from an evaluation run manifest, never from the
engine; the run manifest is what makes the comparison possible and what records
whether the fallback was enabled. The tests seed Assessments directly so the
Machine Recommendation in each cell is exact, then pass a run that names those
Assessment ids.

The central property is immutability: a later Override moves ``final_decision``
and appends an Override row, but it must not move a single cell of the matrix.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import accuracy
from app.models import Encounter, Override, Patient, TriageAssessment, User
from app.override_reasons import OverrideReason
from app.prioritisation import UrgencyLevel

ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

GROUND_TRUTH = accuracy.GroundTruthSource(
    name="ESI v4 rubric",
    version="esi-v4-rubric-v1.0.0",
    citation="Gilboy et al., ESI v4 Implementation Handbook, AHRQ 12-0014.",
    document="evaluation/RUBRIC.md",
)

_SEQUENCE = iter(range(1, 100_000))


def seed_assessment(
    session,
    *,
    machine_recommendation: str,
    final_decision: str | None = None,
    unclassified: bool = False,
    age: int = 40,
) -> TriageAssessment:
    """Insert one immutable Assessment with a chosen Machine Recommendation."""
    n = next(_SEQUENCE)
    patient = Patient(
        full_name=f"Seeded Patient {n}",
        name_key=f"seeded patient {n}",
        age=age,
        sex="female",
        contact_phone=f"07700 9{n:05d}",
        contact_key=f"077009{n:05d}",
    )
    session.add(patient)
    session.flush()
    encounter = Encounter(
        patient_id=patient.id,
        presenting_complaint="Chest pain",
        pain_level=5,
        illness_duration_hours=4.0,
        temperature_c=37.0,
        heart_rate_bpm=80,
        systolic_bp=120,
        diastolic_bp=80,
        oxygen_saturation_percent=97,
    )
    session.add(encounter)
    session.flush()
    assessment = TriageAssessment(
        encounter_id=encounter.id,
        patient_age=age,
        presenting_complaint="Chest pain",
        pain_level=5,
        illness_duration_hours=4.0,
        temperature_c=37.0,
        heart_rate_bpm=80,
        systolic_bp=120,
        diastolic_bp=80,
        oxygen_saturation_percent=97,
        recognised_symptom_groups="chest pain",
        machine_recommendation=machine_recommendation,
        final_decision=final_decision or machine_recommendation,
        unclassified=unclassified,
    )
    session.add(assessment)
    session.flush()
    return assessment


def seed_override(session, assessment: TriageAssessment, reason: OverrideReason):
    actor = session.scalar(select(User).where(User.role == "clinical"))
    assert actor is not None
    session.add(
        Override(
            assessment_id=assessment.id,
            actor_user_id=actor.id,
            reason=reason.value,
        )
    )
    session.flush()


def case(
    assessment: TriageAssessment,
    ground_truth: str,
    *,
    machine_recommendation: str | None = None,
    fallback_used: bool = False,
    unclassified: bool = False,
) -> accuracy.RunCase:
    return accuracy.RunCase(
        assessment_id=assessment.id,
        ground_truth=UrgencyLevel(ground_truth),
        machine_recommendation=(
            UrgencyLevel(machine_recommendation)
            if machine_recommendation is not None
            else None
        ),
        fallback_used=fallback_used,
        unclassified=unclassified,
    )


def make_run(
    cases: list[accuracy.RunCase],
    *,
    run_id: str = "run",
    mode: accuracy.FallbackMode = accuracy.FallbackMode.disabled,
) -> accuracy.EvaluationRun:
    return accuracy.EvaluationRun(
        run_id=run_id,
        mode=mode,
        dataset="rubric-labelled synthetic corpus",
        engine_artefact="urgency-classifier-v1.0.0",
        ground_truth=GROUND_TRUTH,
        cases=tuple(cases),
    )


def manifest(*runs: accuracy.EvaluationRun) -> dict[str, Any]:
    return {
        "schema_version": accuracy.MANIFEST_SCHEMA_VERSION,
        "runs": [
            {
                "run_id": run.run_id,
                "mode": run.mode.value,
                "dataset": run.dataset,
                "engine_artefact": run.engine_artefact,
                "ground_truth": {
                    "name": run.ground_truth.name,
                    "version": run.ground_truth.version,
                    "citation": run.ground_truth.citation,
                    "document": run.ground_truth.document,
                },
                "cases": [
                    {
                        "assessment_id": item.assessment_id,
                        "ground_truth": item.ground_truth.value,
                        "machine_recommendation": (
                            item.machine_recommendation.value
                            if item.machine_recommendation is not None
                            else None
                        ),
                        "fallback_used": item.fallback_used,
                        "unclassified": item.unclassified,
                    }
                    for item in run.cases
                ],
            }
            for run in runs
        ],
    }


def write_manifest(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def session(client: TestClient):
    with client.app.state.session_factory() as session:
        yield session


@pytest.fixture
def run_path(client: TestClient, tmp_path: Path) -> Path:
    path = tmp_path / "accuracy-evaluation.json"
    client.app.state.settings.accuracy_run_path = str(path)
    return path


def login_as_administrator(client: TestClient) -> None:
    response = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert response.status_code == 200, response.text


def fetch_report(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/administrator/reports/accuracy-evaluation")
    assert response.status_code == 200, response.text
    return response.json()


def matrix_cells(run: Any) -> dict[tuple[str, str], int]:
    return {
        (cell.machine_recommendation.value, cell.ground_truth.value): cell.assessments
        for cell in run.confusion_matrix
    }


def level(run: Any, urgency: str) -> Any:
    return next(item for item in run.levels if item.urgency_level.value == urgency)


# The reference sample. Rows are Machine Recommendation, columns ground truth.
REFERENCE = [
    ("High", "High"),
    ("High", "High"),
    ("High", "Medium"),
    ("Medium", "Medium"),
    ("Medium", "Medium"),
    ("Medium", "Low"),
    ("Low", "Low"),
    ("Low", "Low"),
    ("Low", "Low"),
    ("Low", "High"),
]


def seed_reference(session) -> list[accuracy.RunCase]:
    return [
        case(seed_assessment(session, machine_recommendation=machine), truth)
        for machine, truth in REFERENCE
    ]


def test_the_confusion_matrix_counts_every_machine_level_against_ground_truth(
    client: TestClient, session
) -> None:
    run = make_run(seed_reference(session))
    report = accuracy.evaluate_run(session, run)

    assert report.total == 10
    assert report.correct == 7
    assert report.accuracy == 0.7
    assert matrix_cells(report) == {
        ("High", "High"): 2,
        ("High", "Medium"): 1,
        ("High", "Low"): 0,
        ("Medium", "High"): 0,
        ("Medium", "Medium"): 2,
        ("Medium", "Low"): 1,
        ("Low", "High"): 1,
        ("Low", "Medium"): 0,
        ("Low", "Low"): 3,
    }
    # Every level appears as both a row and a column, in Queue order.
    assert [cell.machine_recommendation.value for cell in report.confusion_matrix][
        :3
    ] == ["High", "High", "High"]
    assert [
        cell.ground_truth.value for cell in report.confusion_matrix[:3]
    ] == ["High", "Medium", "Low"]


def test_precision_and_recall_are_reported_for_each_level_separately(
    client: TestClient, session
) -> None:
    run = make_run(seed_reference(session))
    report = accuracy.evaluate_run(session, run)

    high = level(report, "High")
    medium = level(report, "Medium")
    low = level(report, "Low")

    # High: predicted 3 times, right twice; actually 3, right twice.
    assert high.predicted_count == 3
    assert high.ground_truth_count == 3
    assert high.correct == 2
    assert high.precision == pytest.approx(2 / 3)
    assert high.recall == pytest.approx(2 / 3)

    # Medium: predicted 3 times, right twice; actually 3, right twice.
    assert medium.predicted_count == 3
    assert medium.ground_truth_count == 3
    assert medium.precision == pytest.approx(2 / 3)
    assert medium.recall == pytest.approx(2 / 3)

    # Low: predicted 4 times, right three; actually 4, right three. A single
    # aggregate score would hide that these differ from High and Medium.
    assert low.predicted_count == 4
    assert low.ground_truth_count == 4
    assert low.correct == 3
    assert low.precision == pytest.approx(3 / 4)
    assert low.recall == pytest.approx(3 / 4)


def test_false_high_and_false_low_priority_rates_are_separate_figures(
    client: TestClient, session
) -> None:
    run = make_run(seed_reference(session))
    report = accuracy.evaluate_run(session, run)

    # False High: recommended High for a patient the rubric did not call High.
    # One case (High predicted, Medium truth) out of seven non-High truths.
    assert report.false_high_priority.count == 1
    assert report.false_high_priority.denominator == 7
    assert report.false_high_priority.rate == pytest.approx(1 / 7)

    # False Low: recommended Low for a patient the rubric called more urgent.
    # One case (Low predicted, High truth) out of six non-Low truths. This is
    # the missed-urgent risk, and it must not be merged with False High.
    assert report.false_low_priority.count == 1
    assert report.false_low_priority.denominator == 6
    assert report.false_low_priority.rate == pytest.approx(1 / 6)


def test_a_later_override_cannot_move_a_machine_recommendation_in_the_matrix(
    client: TestClient, session
) -> None:
    assessment = seed_assessment(
        session, machine_recommendation="High", final_decision="High"
    )
    run = make_run([case(assessment, "High")])

    before = accuracy.evaluate_run(session, run)
    assert matrix_cells(before) == {
        ("High", "High"): 1,
        ("High", "Medium"): 0,
        ("High", "Low"): 0,
        ("Medium", "High"): 0,
        ("Medium", "Medium"): 0,
        ("Medium", "Low"): 0,
        ("Low", "High"): 0,
        ("Low", "Medium"): 0,
        ("Low", "Low"): 0,
    }
    assert before.false_low_priority.count == 0

    # An Override changes the Final Decision and appends its record. It must
    # not change the stored Machine Recommendation.
    assessment.final_decision = "Low"
    seed_override(session, assessment, OverrideReason.clinical_gestalt)
    session.commit()
    session.refresh(assessment)

    after = accuracy.evaluate_run(session, run)
    assert assessment.machine_recommendation == "High"
    assert matrix_cells(after) == matrix_cells(before)
    assert after.total == before.total
    assert after.correct == before.correct
    assert after.false_low_priority == before.false_low_priority


def test_override_rate_and_reason_distribution_come_from_stored_rows(
    client: TestClient, session
) -> None:
    first = seed_assessment(session, machine_recommendation="High")
    second = seed_assessment(session, machine_recommendation="Medium")
    third = seed_assessment(session, machine_recommendation="Low")
    fourth = seed_assessment(session, machine_recommendation="Low")

    seed_override(session, first, OverrideReason.vitals_inconsistent)
    seed_override(session, second, OverrideReason.other)
    session.commit()

    metrics = accuracy.override_metrics(session)

    assert metrics.assessments == 4
    assert metrics.overridden_assessments == 2
    assert metrics.overrides == 2
    assert metrics.rate == pytest.approx(0.5)
    assert {item.reason: item.overrides for item in metrics.reasons} == {
        OverrideReason.vitals_inconsistent: 1,
        OverrideReason.symptom_not_captured: 0,
        OverrideReason.clinical_gestalt: 0,
        OverrideReason.patient_deteriorating: 0,
        OverrideReason.duplicate_entry: 0,
        OverrideReason.other: 1,
    }
    assert [
        item.reason for item in metrics.reasons
    ] == list(OverrideReason)
    assert next(
        item
        for item in metrics.reasons
        if item.reason is OverrideReason.vitals_inconsistent
    ).share == pytest.approx(0.5)


def test_fallback_on_and_fallback_off_runs_are_distinguishable_and_coverage_is_separate(
    client: TestClient, session
) -> None:
    cases = seed_reference(session)
    disabled = make_run(cases, run_id="primary", mode=accuracy.FallbackMode.disabled)
    enabled = make_run(
        [
            accuracy.RunCase(
                assessment_id=item.assessment_id,
                ground_truth=item.ground_truth,
                machine_recommendation=item.machine_recommendation,
                fallback_used=index < 2,
                unclassified=index == 1,
            )
            for index, item in enumerate(cases)
        ],
        run_id="fallback-on",
        mode=accuracy.FallbackMode.enabled,
    )

    report = accuracy.build_report(
        session, accuracy.RunBundle(accuracy.MANIFEST_SCHEMA_VERSION, (disabled, enabled))
    )

    assert [run.run_id for run in report.runs] == ["primary", "fallback-on"]
    assert [run.mode for run in report.runs] == [
        accuracy.FallbackMode.disabled,
        accuracy.FallbackMode.enabled,
    ]
    assert report.runs[0].fallback.enabled is False
    assert report.runs[0].fallback.coverage is None
    assert report.runs[0].fallback.fallback_used == 0
    assert report.runs[1].fallback.enabled is True
    assert report.runs[1].fallback.fallback_used == 2
    assert report.runs[1].fallback.coverage == pytest.approx(0.2)
    assert report.runs[1].fallback.unclassified == 1
    assert report.runs[1].fallback.unclassified_rate == pytest.approx(0.1)
    # Coverage is reported beside the score, not folded into it: both runs
    # carry the same confusion matrix and the same accuracy.
    assert matrix_cells(report.runs[0]) == matrix_cells(report.runs[1])
    assert report.runs[0].accuracy == report.runs[1].accuracy == 0.7


def test_no_labelled_run_is_an_explicit_empty_state_not_a_zero_score(
    client: TestClient, session
) -> None:
    seed_assessment(session, machine_recommendation="High")
    session.commit()

    report = accuracy.build_report(session, None)

    assert report.available is False
    assert report.runs == ()
    assert report.empty_reason is not None
    assert "ground-truth labels" in report.empty_reason
    # The Override figures do not depend on ground truth, so they remain
    # available and honest even when accuracy cannot be shown.
    assert report.overrides.assessments == 1
    assert report.overrides.rate == 0


def test_a_run_whose_cases_do_not_resolve_is_empty_rather_than_zero(
    client: TestClient, session
) -> None:
    run = make_run([case_for_missing(999_999, "High")])
    report = accuracy.build_report(
        session, accuracy.RunBundle(accuracy.MANIFEST_SCHEMA_VERSION, (run,))
    )

    assert report.available is False
    assert report.runs == ()
    assert report.empty_reason is not None


def case_for_missing(assessment_id: int, ground_truth: str) -> accuracy.RunCase:
    return accuracy.RunCase(
        assessment_id=assessment_id,
        ground_truth=UrgencyLevel(ground_truth),
        machine_recommendation=None,
        fallback_used=False,
        unclassified=False,
    )


def test_missing_assessments_and_inconsistent_recommendations_are_reported(
    client: TestClient, session
) -> None:
    present = seed_assessment(session, machine_recommendation="High")
    run = make_run(
        [
            case(present, "High", machine_recommendation="High"),
            case_for_missing(999_999, "Low"),
        ]
    )
    report = accuracy.evaluate_run(session, run)

    assert report.sample.labelled_cases == 2
    assert report.sample.resolved_assessments == 1
    assert report.sample.missing_assessments == (999_999,)
    assert report.sample.inconsistent_recommendations == ()


def test_a_manifest_recommendation_that_disagrees_with_the_stored_row_is_flagged(
    client: TestClient, session
) -> None:
    assessment = seed_assessment(session, machine_recommendation="High")
    run = make_run([case(assessment, "High", machine_recommendation="Low")])
    report = accuracy.evaluate_run(session, run)

    # The stored immutable row wins; the mismatch is exposed, not hidden.
    assert report.sample.inconsistent_recommendations == (assessment.id,)
    assert matrix_cells(report)[("High", "High")] == 1


def test_the_ground_truth_source_is_carried_into_the_report(
    client: TestClient, session
) -> None:
    run = make_run(seed_reference(session))
    report = accuracy.evaluate_run(session, run)

    assert report.ground_truth.name == "ESI v4 rubric"
    assert report.ground_truth.version == "esi-v4-rubric-v1.0.0"
    assert "AHRQ" in report.ground_truth.citation


def test_the_route_reads_the_manifest_and_reports_both_run_modes(
    client: TestClient, session, run_path: Path
) -> None:
    cases = seed_reference(session)
    session.commit()
    disabled = make_run(cases, run_id="primary", mode=accuracy.FallbackMode.disabled)
    enabled = accuracy.EvaluationRun(
        run_id="fallback-on",
        mode=accuracy.FallbackMode.enabled,
        dataset="rubric-labelled synthetic corpus",
        engine_artefact="urgency-classifier-v1.0.0",
        ground_truth=GROUND_TRUTH,
        cases=tuple(
            accuracy.RunCase(
                assessment_id=item.assessment_id,
                ground_truth=item.ground_truth,
                machine_recommendation=item.machine_recommendation,
                fallback_used=True,
                unclassified=False,
            )
            for item in cases
        ),
    )
    write_manifest(run_path, manifest(disabled, enabled))
    login_as_administrator(client)

    payload = fetch_report(client)

    assert payload["available"] is True
    assert [run["run_id"] for run in payload["runs"]] == ["primary", "fallback-on"]
    assert payload["runs"][0]["mode"] == "fallback-disabled"
    assert payload["runs"][1]["mode"] == "fallback-enabled"
    assert payload["runs"][0]["fallback"]["coverage"] is None
    assert payload["runs"][1]["fallback"]["coverage"] == 1.0
    assert payload["runs"][0]["accuracy"] == 0.7
    assert payload["runs"][0]["ground_truth"]["name"] == "ESI v4 rubric"
    assert payload["overrides"]["assessments"] == 10


def test_the_route_explains_an_unlabelled_database_without_inventing_a_score(
    client: TestClient, run_path: Path
) -> None:
    login_as_administrator(client)

    payload = fetch_report(client)

    assert payload["available"] is False
    assert payload["runs"] == []
    assert payload["empty_reason"]
    assert payload["overrides"] == {
        "assessments": 0,
        "overridden_assessments": 0,
        "overrides": 0,
        "rate": None,
        "reasons": [
            {"reason": reason.value, "overrides": 0, "share": None}
            for reason in OverrideReason
        ],
    }


def test_computing_the_accuracy_report_writes_nothing(
    client: TestClient, session, run_path: Path
) -> None:
    cases = seed_reference(session)
    session.commit()
    write_manifest(run_path, manifest(make_run(cases)))
    login_as_administrator(client)

    with client.app.state.session_factory() as check:
        before = _stored_state(check)

    fetch_report(client)
    fetch_report(client)

    with client.app.state.session_factory() as check:
        after = _stored_state(check)

    assert after == before


def _stored_state(session) -> dict[str, Any]:
    return {
        "assessments": [
            (
                assessment.id,
                assessment.machine_recommendation,
                assessment.final_decision,
            )
            for assessment in session.scalars(
                select(TriageAssessment).order_by(TriageAssessment.id)
            ).all()
        ],
        "overrides": [
            (override.id, override.assessment_id, override.reason)
            for override in session.scalars(
                select(Override).order_by(Override.id)
            ).all()
        ],
    }


def test_the_accuracy_report_is_administrator_only(client: TestClient) -> None:
    response = client.get(
        "/api/administrator/reports/accuracy-evaluation"
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_the_accuracy_report_is_refused_to_a_clinical_user(
    clinical_client: TestClient,
) -> None:
    response = clinical_client.get(
        "/api/administrator/reports/accuracy-evaluation"
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_a_manifest_with_an_unknown_mode_is_rejected(
    client: TestClient, session, run_path: Path
) -> None:
    write_manifest(
        run_path,
        {
            "schema_version": accuracy.MANIFEST_SCHEMA_VERSION,
            "runs": [
                {
                    "run_id": "bad",
                    "mode": "sometimes",
                    "ground_truth": {
                        "name": "ESI v4 rubric",
                        "version": "v1",
                        "citation": "x",
                    },
                    "cases": [],
                }
            ],
        },
    )

    with pytest.raises(accuracy.AccuracyRunError):
        accuracy.load_run_bundle(run_path)


def test_a_fallback_disabled_run_cannot_claim_a_fallback_case(
    client: TestClient, run_path: Path
) -> None:
    write_manifest(
        run_path,
        {
            "schema_version": accuracy.MANIFEST_SCHEMA_VERSION,
            "runs": [
                {
                    "run_id": "inconsistent",
                    "mode": "fallback-disabled",
                    "ground_truth": {
                        "name": "ESI v4 rubric",
                        "version": "v1",
                        "citation": "x",
                    },
                    "cases": [
                        {
                            "assessment_id": 1,
                            "ground_truth": "High",
                            "fallback_used": True,
                        }
                    ],
                }
            ],
        },
    )

    with pytest.raises(accuracy.AccuracyRunError):
        accuracy.load_run_bundle(run_path)


def test_precision_is_null_when_a_level_was_never_predicted(
    client: TestClient, session
) -> None:
    cases = [
        case(seed_assessment(session, machine_recommendation="High"), "High"),
        case(seed_assessment(session, machine_recommendation="High"), "Medium"),
    ]
    report = accuracy.evaluate_run(session, make_run(cases))

    low = level(report, "Low")
    assert low.predicted_count == 0
    assert low.precision is None
    # No case had ground truth Low either, so recall has no denominator.
    assert low.recall is None
