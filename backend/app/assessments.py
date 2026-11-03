"""Creating the Triage Assessment that completing intake produces.

Intake is complete as soon as an Encounter exists (ticket 02), so opening an
Encounter creates its first Assessment in the same transaction. The
recommendation comes from Seam B (``app.prioritisation``); this module is the
only place that bridges a stored Encounter to those pure inputs.
"""

from sqlalchemy.orm import Session

from app.models import Encounter, TriageAssessment
from app.prioritisation import PrioritisationInputs, recommend
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
    session: Session, encounter: Encounter
) -> TriageAssessment:
    """Run the engine once and append the resulting Assessment."""
    inputs = build_inputs(encounter)
    recommendation = recommend(inputs)

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
        machine_recommendation=recommendation.value,
        # No Override exists in this ticket, so the Final Decision starts equal
        # to the Machine Recommendation. Ticket 09 changes only this field.
        final_decision=recommendation.value,
    )
    session.add(assessment)
    return assessment
