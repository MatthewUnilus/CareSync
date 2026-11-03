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
        systolic_bp=encounter.systolic_bp,
        diastolic_bp=encounter.diastolic_bp,
        oxygen_saturation_percent=encounter.oxygen_saturation_percent,
        recognised_symptom_groups=recognise(encounter.presenting_complaint),
    )


def create_triage_assessment(
    session: Session,
    encounter: Encounter,
    *,
    supersedes: TriageAssessment | None = None,
    fallback: FallbackResolver | None = None,
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
        systolic_bp=inputs.systolic_bp,
        diastolic_bp=inputs.diastolic_bp,
        oxygen_saturation_percent=inputs.oxygen_saturation_percent,
        notes=encounter.notes,
        recognised_symptom_groups=",".join(inputs.recognised_symptom_groups),
        machine_recommendation=recommendation.level.value,
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
