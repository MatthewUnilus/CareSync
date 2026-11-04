"""Materialise the rubric-labelled corpus as stored Assessment records.

Ticket 04 requires ground truth to be kept distinct from Machine
Recommendations *in the stored data*, and ticket 14 requires the accuracy
figures to be computed from stored, immutable Triage Assessments. This command
closes that gap without changing live reporting: it writes one Patient, one
Encounter and one scored Triage Assessment per corpus Encounter, tagged with an
evaluation-run identifier and the rubric's ground-truth level.

Each Assessment's ``machine_recommendation`` is produced by the real engine
through :func:`app.assessments.create_triage_assessment`; nothing is copied
from the harness artefact. The rubric label lands in its own
``ground_truth_level`` column, never in ``machine_recommendation`` or
``final_decision``.

Evaluation rows are excluded from the Queue and from the activity and
performance Reports. When a stored evaluation run exists, the Accuracy
Evaluation Report prefers it over the offline artefact.

Usage, from ``backend/``::

    uv run python -m evaluation.materialise
    uv run python -m evaluation.materialise --run-id my-run --replace
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assessments import create_triage_assessment
from app.config import get_settings
from app.db import Base, build_engine, build_session_factory
from app.models import Encounter, Patient, TriageAssessment
from evaluation.corpus import CORPUS_PATH, Corpus, load_corpus

DEFAULT_RUN_ID = "esi-v4-rubric-v1.0.0-corpus"


def materialise_corpus(
    session: Session,
    corpus: Corpus,
    *,
    run_id: str = DEFAULT_RUN_ID,
    replace: bool = False,
) -> int:
    """Write the corpus as stored records and return the Assessment count.

    The fallback is deliberately disabled, matching the harness's primary
    pipeline run: the result is deterministic and reproducible. Existing rows
    for ``run_id`` are refused unless ``replace`` is true, so a rerun cannot
    silently double the corpus.
    """
    existing = session.scalar(
        select(func.count())
        .select_from(Encounter)
        .where(Encounter.evaluation_run_id == run_id)
    ) or 0
    if existing and not replace:
        raise ValueError(
            f"evaluation run {run_id!r} already has {existing} stored "
            "Encounter(s); pass --replace to rebuild it"
        )
    if existing:
        _delete_run(session, run_id)

    slug = run_id[:16].replace(" ", "-")
    created = 0
    for index, encounter in enumerate(corpus.encounters):
        patient = Patient(
            full_name=f"Evaluation Patient {slug} {index:03d}",
            name_key=f"evaluation patient {slug} {index:03d}".casefold(),
            age=int(round(encounter.patient_age_years)),
            sex=encounter.patient_sex,
            contact_phone=f"eval-{slug[:20]}-{index:04d}",
            contact_key=f"eval-{slug[:20]}-{index:04d}",
        )
        session.add(patient)
        session.flush()

        intake = encounter.intake
        # The rubric corpus records 0 for a patient who cannot report pain;
        # the product's intake range is 1-10. Store the minimum valid value.
        # For the three affected Encounter the engine's recommendation is
        # unchanged, and the stored-versus-pipeline test pins that.
        pain_level = max(1, int(intake.pain_level))
        stored_encounter = Encounter(
            patient_id=patient.id,
            evaluation_run_id=run_id,
            presenting_complaint=intake.presenting_complaint,
            pain_level=pain_level,
            illness_duration_hours=intake.illness_duration_hours,
            temperature_c=intake.temperature_c,
            heart_rate_bpm=intake.heart_rate_bpm,
            systolic_bp=intake.systolic_bp,
            diastolic_bp=intake.diastolic_bp,
            oxygen_saturation_percent=intake.oxygen_saturation_percent,
            notes=intake.notes or None,
        )
        session.add(stored_encounter)
        session.flush()

        create_triage_assessment(
            session,
            stored_encounter,
            ground_truth_level=encounter.ground_truth.urgency_level.value,
        )
        created += 1

    return created


def _delete_run(session: Session, run_id: str) -> None:
    """Remove a previous materialisation, Assessments first (no DB cascade)."""
    encounters = session.scalars(
        select(Encounter).where(Encounter.evaluation_run_id == run_id)
    ).all()
    patient_ids = {encounter.patient_id for encounter in encounters}
    for encounter in encounters:
        for assessment in session.scalars(
            select(TriageAssessment).where(
                TriageAssessment.encounter_id == encounter.id
            )
        ).all():
            session.delete(assessment)
        session.delete(encounter)
    session.flush()
    for patient_id in patient_ids:
        patient = session.get(Patient, patient_id)
        if patient is not None:
            session.delete(patient)
    session.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialise the rubric-labelled evaluation corpus into stored "
            "Patients, Encounters and scored Triage Assessments."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    parser.add_argument(
        "--database-url",
        default=None,
        help="override the configured database URL",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="delete and rebuild rows already stored under this run id",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    database_url = args.database_url or settings.database_url
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    corpus = load_corpus(args.corpus)
    try:
        with session_factory() as session:
            created = materialise_corpus(
                session, corpus, run_id=args.run_id, replace=args.replace
            )
            session.commit()
    except ValueError as error:
        print(error)
        return 2

    print(
        f"materialised {created} Encounter(s) from {args.corpus} "
        f"as evaluation run {args.run_id!r}"
    )
    print(f"database: {database_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
