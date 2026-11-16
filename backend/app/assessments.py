"""Creating Triage Assessments from an Encounter's captured intake.

Intake is complete as soon as an Encounter exists (ticket 02), so opening an
Encounter creates its first Assessment in the same transaction. A Re-assessment
(ticket 10) reuses this factory to append a later one. The recommendation comes
from Seam B (``app.prioritisation``); this module is the only place that bridges
a stored Encounter to those pure inputs.
"""

from sqlalchemy.orm import Session

from app.fallback import FallbackResolver
from app.models import Encounter, TriageAssessment
from app.prioritisation import PrioritisationInputs, assess
from app.symptom_groups import recognise


def build_inputs(encounter: Encounter) -> PrioritisationInputs:
    """Capture the engine inputs from the Encounter and its Patient.

    Recognition runs here, as part of producing the Assessment, so the groups
    are frozen into the same snapshot as the rest of the inputs. This ticket
    only records them: ``recommend`` still decides exactly as it did before.
    """
    return PrioritisationInputs(
        presenting_complaint=encounter.presenting_complaint,
        age=encounter.patient.age,
        pain_level=encounter.pain_level,
        illness_duration_hours=encounter.illness_duration_hours,
        temperature_c=encounter.temperature_c,
        heart_rate_bpm=encounter.heart_rate_bpm,
        respiratory_rate_bpm=encounter.respiratory_rate_bpm,
        systolic_bp=encounter.systolic_bp,
        diastolic_bp=encounter.diastolic_bp,
        oxygen_saturation_percent=encounter.oxygen_saturation_percent,
        recognised_symptom_groups=recognise(encounter.presenting_complaint),
    )


def inputs_from_assessment(assessment: TriageAssessment) -> PrioritisationInputs:
    """Rebuild the engine inputs from an Assessment's frozen snapshot.

    The snapshot is the durable record of what the recommendation was made from
    (the Encounter's intake is a separate, later-editable row only while no
    Assessment exists). Rebuilding from it lets a reader re-derive the red flags
    for a stored Assessment, so what the board shows as "why this is High" is
    computed from the same thresholds the recommendation used and cannot drift
    from it.
    """
    return PrioritisationInputs(
        presenting_complaint=assessment.presenting_complaint,
        age=assessment.patient_age,
        pain_level=assessment.pain_level,
        illness_duration_hours=assessment.illness_duration_hours,
        temperature_c=assessment.temperature_c,
        heart_rate_bpm=assessment.heart_rate_bpm,
        respiratory_rate_bpm=assessment.respiratory_rate_bpm,
        systolic_bp=assessment.systolic_bp,
        diastolic_bp=assessment.diastolic_bp,
        oxygen_saturation_percent=assessment.oxygen_saturation_percent,
        recognised_symptom_groups=tuple(
            group
            for group in assessment.recognised_symptom_groups.split(",")
            if group
        ),
    )


def create_triage_assessment(
    session: Session,
    encounter: Encounter,
    *,
    supersedes: TriageAssessment | None = None,
    fallback: FallbackResolver | None = None,
    ground_truth_level: str | None = None,
) -> TriageAssessment:
    """Run the engine once and append the resulting Assessment.

    ``supersedes`` is set only by a Re-assessment: it records the Assessment
    that was governing the Encounter until this one was created. Opening an
    Encounter passes nothing, so a first Assessment supersedes no one.

    ``fallback`` is the runtime resolver, supplied by the API path. Passing
    ``None`` disables the fallback layer, which is the reproducible-evaluation
    configuration rather than the runtime default.
    """
    inputs = build_inputs(encounter)
    recommendation = assess(inputs, fallback=fallback)

    assessment = TriageAssessment(
        encounter=encounter,
        patient_age=inputs.age,
        presenting_complaint=inputs.presenting_complaint,
        pain_level=inputs.pain_level,
        illness_duration_hours=inputs.illness_duration_hours,
        temperature_c=inputs.temperature_c,
        heart_rate_bpm=inputs.heart_rate_bpm,
        respiratory_rate_bpm=inputs.respiratory_rate_bpm,
        systolic_bp=inputs.systolic_bp,
        diastolic_bp=inputs.diastolic_bp,
        oxygen_saturation_percent=inputs.oxygen_saturation_percent,
        notes=encounter.notes,
        recognised_symptom_groups=",".join(inputs.recognised_symptom_groups),
        machine_recommendation=recommendation.level.value,
        # Supplied only by the evaluation-corpus materialiser. Live Assessments
        # have no ground truth, so the column stays null and the rubric label
        # can never be confused with a Machine Recommendation.
        ground_truth_level=ground_truth_level,
        unclassified=recommendation.unclassified,
        # No Override exists at this point, so the Final Decision starts equal
        # to the Machine Recommendation. An Override changes only this field.
        final_decision=recommendation.level.value,
        supersedes_assessment_id=(
            supersedes.id if supersedes is not None else None
        ),
    )
    session.add(assessment)
    return assessment
