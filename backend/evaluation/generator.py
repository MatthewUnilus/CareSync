"""Deterministic synthetic Encounter generator for evaluation.

Every generated Encounter is labelled by applying the written ESI v4 rubric to
its described presentation (see :mod:`evaluation.labeller`). The generator
contains no urgency labels of its own: a scenario is only a clinical
description, and its ground-truth label is always the rubric's output.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from evaluation.labeller import label
from evaluation.rubric import (
    EsiLevel,
    EsiResource,
    GroundTruthLabel,
    HighRiskFlag,
    MentalStatus,
    Presentation,
    UrgencyLevel,
)

DEFAULT_SEED = 20261103
GENERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class EncounterIntake:
    """The subset of a Presentation captured by the real Encounter intake."""

    presenting_complaint: str
    pain_level: int
    illness_duration_hours: float
    temperature_c: float
    heart_rate_bpm: int
    systolic_bp: int
    diastolic_bp: int
    oxygen_saturation_percent: int
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "presenting_complaint": self.presenting_complaint,
            "pain_level": self.pain_level,
            "illness_duration_hours": self.illness_duration_hours,
            "temperature_c": self.temperature_c,
            "heart_rate_bpm": self.heart_rate_bpm,
            "systolic_bp": self.systolic_bp,
            "diastolic_bp": self.diastolic_bp,
            "oxygen_saturation_percent": self.oxygen_saturation_percent,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "EncounterIntake":
        return cls(
            presenting_complaint=str(data["presenting_complaint"]),
            pain_level=int(data["pain_level"]),  # type: ignore[arg-type]
            illness_duration_hours=float(data["illness_duration_hours"]),  # type: ignore[arg-type]
            temperature_c=float(data["temperature_c"]),  # type: ignore[arg-type]
            heart_rate_bpm=int(data["heart_rate_bpm"]),  # type: ignore[arg-type]
            systolic_bp=int(data["systolic_bp"]),  # type: ignore[arg-type]
            diastolic_bp=int(data["diastolic_bp"]),  # type: ignore[arg-type]
            oxygen_saturation_percent=int(data["oxygen_saturation_percent"]),  # type: ignore[arg-type]
            notes=str(data["notes"]),
        )


@dataclass(frozen=True)
class LabelledEncounter:
    encounter_id: str
    patient_age_years: float
    patient_sex: str
    intake: EncounterIntake
    presentation: Presentation
    ground_truth: GroundTruthLabel

    def to_dict(self) -> dict[str, object]:
        return {
            "encounter_id": self.encounter_id,
            "patient": {
                "age_years": self.patient_age_years,
                "sex": self.patient_sex,
            },
            "intake": self.intake.to_dict(),
            "presentation": presentation_to_dict(self.presentation),
            "ground_truth": {
                "urgency_level": self.ground_truth.urgency_level.value,
                "esi_level": int(self.ground_truth.esi_level),
                "rubric_version": self.ground_truth.rubric_version,
                "matched_rule": self.ground_truth.matched_rule,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "LabelledEncounter":
        patient = data["patient"]
        ground_truth = data["ground_truth"]
        if not isinstance(patient, dict) or not isinstance(ground_truth, dict):
            raise ValueError("patient and ground_truth must be objects")
        presentation_data = data["presentation"]
        intake_data = data["intake"]
        if not isinstance(presentation_data, dict) or not isinstance(intake_data, dict):
            raise ValueError("presentation and intake must be objects")
        return cls(
            encounter_id=str(data["encounter_id"]),
            patient_age_years=float(patient["age_years"]),  # type: ignore[arg-type]
            patient_sex=str(patient["sex"]),
            intake=EncounterIntake.from_dict(intake_data),
            presentation=presentation_from_dict(presentation_data),
            ground_truth=GroundTruthLabel(
                urgency_level=UrgencyLevel(str(ground_truth["urgency_level"])),
                esi_level=EsiLevel(int(ground_truth["esi_level"])),  # type: ignore[arg-type]
                rubric_version=str(ground_truth["rubric_version"]),
                matched_rule=str(ground_truth["matched_rule"]),
                citation="",
            ),
        )


def presentation_to_dict(presentation: Presentation) -> dict[str, object]:
    return {
        "age_years": presentation.age_years,
        "sex": presentation.sex,
        "presenting_complaint": presentation.presenting_complaint,
        "onset": presentation.onset,
        "illness_duration_hours": presentation.illness_duration_hours,
        "pain_level": presentation.pain_level,
        "pain_requires_intervention_beyond_triage": (
            presentation.pain_requires_intervention_beyond_triage
        ),
        "temperature_c": presentation.temperature_c,
        "heart_rate_bpm": presentation.heart_rate_bpm,
        "respiratory_rate_bpm": presentation.respiratory_rate_bpm,
        "systolic_bp": presentation.systolic_bp,
        "diastolic_bp": presentation.diastolic_bp,
        "oxygen_saturation_percent": presentation.oxygen_saturation_percent,
        "mental_status": presentation.mental_status.value,
        "new_onset_altered_mental_status": (
            presentation.new_onset_altered_mental_status
        ),
        "associated_symptoms": sorted(presentation.associated_symptoms),
        "mechanism_of_injury": presentation.mechanism_of_injury,
        "medical_history": sorted(presentation.medical_history),
        "high_risk_flags": sorted(flag.value for flag in presentation.high_risk_flags),
        "severe_distress": presentation.severe_distress,
        "life_saving_intervention_required": (
            presentation.life_saving_intervention_required
        ),
        "severe_respiratory_distress": presentation.severe_respiratory_distress,
        "expected_resources": [
            resource.value for resource in presentation.expected_resources
        ],
    }


def presentation_from_dict(data: dict[str, object]) -> Presentation:
    return Presentation(
        age_years=float(data["age_years"]),  # type: ignore[arg-type]
        sex=str(data["sex"]),
        presenting_complaint=str(data["presenting_complaint"]),
        onset=str(data["onset"]),
        illness_duration_hours=float(data["illness_duration_hours"]),  # type: ignore[arg-type]
        pain_level=int(data["pain_level"]),  # type: ignore[arg-type]
        pain_requires_intervention_beyond_triage=bool(
            data["pain_requires_intervention_beyond_triage"]
        ),
        temperature_c=float(data["temperature_c"]),  # type: ignore[arg-type]
        heart_rate_bpm=int(data["heart_rate_bpm"]),  # type: ignore[arg-type]
        respiratory_rate_bpm=int(data["respiratory_rate_bpm"]),  # type: ignore[arg-type]
        systolic_bp=int(data["systolic_bp"]),  # type: ignore[arg-type]
        diastolic_bp=int(data["diastolic_bp"]),  # type: ignore[arg-type]
        oxygen_saturation_percent=int(data["oxygen_saturation_percent"]),  # type: ignore[arg-type]
        mental_status=MentalStatus(str(data["mental_status"])),
        new_onset_altered_mental_status=bool(
            data["new_onset_altered_mental_status"]
        ),
        associated_symptoms=frozenset(
            str(value) for value in data["associated_symptoms"]  # type: ignore[union-attr]
        ),
        mechanism_of_injury=(
            None
            if data["mechanism_of_injury"] is None
            else str(data["mechanism_of_injury"])
        ),
        medical_history=frozenset(
            str(value) for value in data["medical_history"]  # type: ignore[union-attr]
        ),
        high_risk_flags=frozenset(
            HighRiskFlag(str(value)) for value in data["high_risk_flags"]  # type: ignore[union-attr]
        ),
        severe_distress=bool(data["severe_distress"]),
        life_saving_intervention_required=bool(
            data["life_saving_intervention_required"]
        ),
        severe_respiratory_distress=bool(data["severe_respiratory_distress"]),
        expected_resources=tuple(
            EsiResource(str(value)) for value in data["expected_resources"]  # type: ignore[union-attr]
        ),
    )


def _baseline() -> Presentation:
    return Presentation(
        age_years=34.0,
        sex="female",
        presenting_complaint="sore throat for two days",
        onset="gradual",
        illness_duration_hours=48.0,
        pain_level=3,
        pain_requires_intervention_beyond_triage=False,
        temperature_c=37.2,
        heart_rate_bpm=78,
        respiratory_rate_bpm=16,
        systolic_bp=118,
        diastolic_bp=74,
        oxygen_saturation_percent=98,
        mental_status=MentalStatus.alert,
        new_onset_altered_mental_status=False,
        associated_symptoms=frozenset({"cough"}),
        mechanism_of_injury=None,
        medical_history=frozenset(),
        high_risk_flags=frozenset(),
        severe_distress=False,
        life_saving_intervention_required=False,
        severe_respiratory_distress=False,
        expected_resources=(EsiResource.labs,),
    )


@dataclass(frozen=True)
class _Scenario:
    encounter_id: str
    description: str
    overrides: dict[str, object]


_SCENARIOS: tuple[_Scenario, ...] = (
    # High urgency: ESI 1 (immediate life-saving intervention, respiratory
    # failure, hypoxaemia, unresponsiveness).
    _Scenario(
        "syn-001",
        "Cardiac arrest with hypoxaemia and unresponsiveness",
        {
            "presenting_complaint": "collapsed at home, not breathing normally",
            "onset": "sudden",
            "illness_duration_hours": 0.2,
            "pain_level": 0,
            "temperature_c": 36.1,
            "heart_rate_bpm": 132,
            "respiratory_rate_bpm": 32,
            "systolic_bp": 82,
            "diastolic_bp": 54,
            "oxygen_saturation_percent": 84,
            "mental_status": MentalStatus.unresponsive,
            "new_onset_altered_mental_status": True,
            "associated_symptoms": frozenset({"cyanosis"}),
            "medical_history": frozenset({"hypertension"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.suspected_acute_coronary_syndrome}
            ),
            "life_saving_intervention_required": True,
            "severe_respiratory_distress": True,
            "expected_resources": (),
        },
    ),
    _Scenario(
        "syn-002",
        "Severe respiratory distress from an asthma exacerbation",
        {
            "presenting_complaint": "severe shortness of breath, cannot speak in sentences",
            "onset": "sudden",
            "illness_duration_hours": 2.0,
            "pain_level": 4,
            "temperature_c": 37.0,
            "heart_rate_bpm": 126,
            "respiratory_rate_bpm": 34,
            "systolic_bp": 138,
            "diastolic_bp": 86,
            "oxygen_saturation_percent": 88,
            "associated_symptoms": frozenset({"wheeze", "accessory muscle use"}),
            "medical_history": frozenset({"asthma"}),
            "severe_respiratory_distress": True,
            "expected_resources": (
                EsiResource.nebulized_medications,
                EsiResource.labs,
            ),
        },
    ),
    # High urgency: ESI 2 (high-risk situation, altered mental status, severe
    # pain, severe distress, danger-zone vital signs).
    _Scenario(
        "syn-003",
        "Suspected acute coronary syndrome",
        {
            "presenting_complaint": "crushing central chest pain radiating to left arm",
            "onset": "sudden",
            "illness_duration_hours": 1.0,
            "pain_level": 7,
            "pain_requires_intervention_beyond_triage": True,
            "temperature_c": 36.9,
            "heart_rate_bpm": 96,
            "respiratory_rate_bpm": 20,
            "systolic_bp": 142,
            "diastolic_bp": 88,
            "oxygen_saturation_percent": 96,
            "associated_symptoms": frozenset({"diaphoresis", "nausea"}),
            "medical_history": frozenset({"hyperlipidaemia"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.suspected_acute_coronary_syndrome}
            ),
            "expected_resources": (EsiResource.ecg, EsiResource.labs),
        },
    ),
    _Scenario(
        "syn-004",
        "Suspected stroke with new focal weakness",
        {
            "age_years": 72.0,
            "presenting_complaint": "sudden left arm weakness and slurred speech",
            "onset": "sudden",
            "illness_duration_hours": 0.5,
            "pain_level": 1,
            "temperature_c": 36.8,
            "heart_rate_bpm": 88,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 188,
            "diastolic_bp": 104,
            "oxygen_saturation_percent": 95,
            "mental_status": MentalStatus.verbal,
            "new_onset_altered_mental_status": True,
            "associated_symptoms": frozenset({"facial droop", "dysarthria"}),
            "medical_history": frozenset({"hypertension", "atrial fibrillation"}),
            "high_risk_flags": frozenset({HighRiskFlag.signs_of_stroke}),
            "expected_resources": (EsiResource.ct, EsiResource.labs),
        },
    ),
    _Scenario(
        "syn-005",
        "Severe flank pain needing urgent analgesia",
        {
            "presenting_complaint": "severe flank pain, writhing",
            "onset": "sudden",
            "illness_duration_hours": 3.0,
            "pain_level": 9,
            "pain_requires_intervention_beyond_triage": True,
            "temperature_c": 37.4,
            "heart_rate_bpm": 104,
            "respiratory_rate_bpm": 22,
            "systolic_bp": 148,
            "diastolic_bp": 92,
            "oxygen_saturation_percent": 97,
            "associated_symptoms": frozenset({"nausea", "vomiting"}),
            "medical_history": frozenset({"renal colic"}),
            "expected_resources": (EsiResource.labs, EsiResource.ct),
        },
    ),
    _Scenario(
        "syn-006",
        "Adult danger-zone tachycardia with fever",
        {
            "age_years": 45.0,
            "presenting_complaint": "feels hot and shaky",
            "onset": "gradual",
            "illness_duration_hours": 24.0,
            "pain_level": 3,
            "temperature_c": 38.2,
            "heart_rate_bpm": 118,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 118,
            "diastolic_bp": 72,
            "oxygen_saturation_percent": 97,
            "associated_symptoms": frozenset({"chills", "malaise"}),
            "expected_resources": (EsiResource.labs, EsiResource.iv_fluids),
        },
    ),
    _Scenario(
        "syn-007",
        "Paediatric danger-zone tachycardia",
        {
            "age_years": 5.0,
            "sex": "male",
            "presenting_complaint": "cough and fever",
            "illness_duration_hours": 20.0,
            "pain_level": 2,
            "temperature_c": 38.1,
            "heart_rate_bpm": 145,
            "respiratory_rate_bpm": 26,
            "systolic_bp": 102,
            "diastolic_bp": 64,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"cough", "runny nose"}),
            "expected_resources": (EsiResource.labs,),
        },
    ),
    _Scenario(
        "syn-008",
        "High-risk trauma mechanism",
        {
            "age_years": 29.0,
            "sex": "male",
            "presenting_complaint": "unrestrained passenger in a high-speed crash",
            "onset": "sudden",
            "illness_duration_hours": 1.0,
            "pain_level": 5,
            "temperature_c": 36.7,
            "heart_rate_bpm": 102,
            "respiratory_rate_bpm": 20,
            "systolic_bp": 112,
            "diastolic_bp": 70,
            "oxygen_saturation_percent": 96,
            "associated_symptoms": frozenset({"right upper quadrant pain"}),
            "mechanism_of_injury": "unrestrained passenger, high-speed motor vehicle crash",
            "high_risk_flags": frozenset({HighRiskFlag.major_trauma_mechanism}),
            "expected_resources": (
                EsiResource.ct,
                EsiResource.x_ray,
                EsiResource.labs,
            ),
        },
    ),
    _Scenario(
        "syn-009",
        "Suicidal ideation with a plan",
        {
            "age_years": 22.0,
            "sex": "male",
            "presenting_complaint": "expressing suicidal thoughts with a plan",
            "onset": "gradual",
            "illness_duration_hours": 12.0,
            "pain_level": 2,
            "temperature_c": 36.6,
            "heart_rate_bpm": 84,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 116,
            "diastolic_bp": 72,
            "oxygen_saturation_percent": 99,
            "associated_symptoms": frozenset({"hopelessness"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.suicidal_or_homicidal_ideation}
            ),
            "severe_distress": True,
            "expected_resources": (EsiResource.specialty_consultation,),
        },
    ),
    _Scenario(
        "syn-010",
        "Possible ectopic pregnancy",
        {
            "age_years": 28.0,
            "presenting_complaint": "lower abdominal pain with a missed period",
            "onset": "gradual",
            "illness_duration_hours": 8.0,
            "pain_level": 6,
            "temperature_c": 37.0,
            "heart_rate_bpm": 92,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 108,
            "diastolic_bp": 66,
            "oxygen_saturation_percent": 99,
            "associated_symptoms": frozenset({"vaginal spotting"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.suspected_ectopic_pregnancy}
            ),
            "expected_resources": (EsiResource.labs, EsiResource.ultrasound),
        },
    ),
    _Scenario(
        "syn-011",
        "Febrile immunocompromised patient",
        {
            "age_years": 61.0,
            "presenting_complaint": "fever while receiving chemotherapy",
            "onset": "gradual",
            "illness_duration_hours": 10.0,
            "pain_level": 2,
            "temperature_c": 38.6,
            "heart_rate_bpm": 98,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 110,
            "diastolic_bp": 68,
            "oxygen_saturation_percent": 96,
            "associated_symptoms": frozenset({"fatigue"}),
            "medical_history": frozenset({"chemotherapy"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.immunocompromised_with_fever}
            ),
            "expected_resources": (EsiResource.labs, EsiResource.iv_fluids),
        },
    ),
    _Scenario(
        "syn-012",
        "New onset confusion in an older adult",
        {
            "age_years": 79.0,
            "presenting_complaint": "found confused this morning",
            "onset": "sudden",
            "illness_duration_hours": 3.0,
            "pain_level": 1,
            "temperature_c": 37.0,
            "heart_rate_bpm": 88,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 150,
            "diastolic_bp": 84,
            "oxygen_saturation_percent": 96,
            "mental_status": MentalStatus.verbal,
            "new_onset_altered_mental_status": True,
            "associated_symptoms": frozenset({"disorientation"}),
            "expected_resources": (EsiResource.labs, EsiResource.ct),
        },
    ),
    _Scenario(
        "syn-013",
        "Possible spontaneous pneumothorax",
        {
            "age_years": 21.0,
            "sex": "male",
            "presenting_complaint": "sudden shortness of breath after coughing",
            "onset": "sudden",
            "illness_duration_hours": 1.0,
            "pain_level": 5,
            "temperature_c": 36.8,
            "heart_rate_bpm": 108,
            "respiratory_rate_bpm": 24,
            "systolic_bp": 124,
            "diastolic_bp": 78,
            "oxygen_saturation_percent": 95,
            "associated_symptoms": frozenset({"pleuritic chest pain"}),
            "high_risk_flags": frozenset({HighRiskFlag.suspected_pneumothorax}),
            "expected_resources": (EsiResource.x_ray, EsiResource.labs),
        },
    ),
    _Scenario(
        "syn-014",
        "Sudden worst headache of life",
        {
            "age_years": 44.0,
            "presenting_complaint": "worst headache of my life after lifting furniture",
            "onset": "sudden",
            "illness_duration_hours": 1.0,
            "pain_level": 9,
            "pain_requires_intervention_beyond_triage": True,
            "temperature_c": 36.9,
            "heart_rate_bpm": 90,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 160,
            "diastolic_bp": 94,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"neck stiffness", "photophobia"}),
            "high_risk_flags": frozenset(
                {HighRiskFlag.suspected_subarachnoid_haemorrhage}
            ),
            "expected_resources": (EsiResource.ct, EsiResource.labs),
        },
    ),
    _Scenario(
        "syn-015",
        "Acute severe psychological distress",
        {
            "age_years": 31.0,
            "presenting_complaint": "acute grief reaction, unable to settle",
            "onset": "sudden",
            "illness_duration_hours": 2.0,
            "pain_level": 2,
            "temperature_c": 36.7,
            "heart_rate_bpm": 92,
            "respiratory_rate_bpm": 20,
            "systolic_bp": 128,
            "diastolic_bp": 80,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"agitation"}),
            "severe_distress": True,
            "expected_resources": (EsiResource.specialty_consultation,),
        },
    ),
    # Medium urgency: ESI 3 (two or more expected resources, no ESI 1/2 rule).
    _Scenario(
        "syn-016",
        "Abdominal pain requiring imaging and labs",
        {
            "age_years": 22.0,
            "sex": "male",
            "presenting_complaint": "right lower abdominal pain since this morning",
            "illness_duration_hours": 8.0,
            "pain_level": 5,
            "temperature_c": 37.4,
            "heart_rate_bpm": 88,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 122,
            "diastolic_bp": 76,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"nausea", "anorexia"}),
            "expected_resources": (EsiResource.labs, EsiResource.ct),
        },
    ),
    _Scenario(
        "syn-017",
        "Leg swelling needing ultrasound and labs",
        {
            "age_years": 45.0,
            "presenting_complaint": "left lower leg pain and swelling after a long car trip",
            "illness_duration_hours": 48.0,
            "pain_level": 4,
            "temperature_c": 36.9,
            "heart_rate_bpm": 82,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 132,
            "diastolic_bp": 82,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"calf tenderness"}),
            "expected_resources": (EsiResource.labs, EsiResource.ultrasound),
        },
    ),
    _Scenario(
        "syn-018",
        "Febrile urinary symptoms needing fluids and labs",
        {
            "age_years": 38.0,
            "presenting_complaint": "fever and burning on urination",
            "illness_duration_hours": 30.0,
            "pain_level": 4,
            "temperature_c": 38.4,
            "heart_rate_bpm": 94,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 118,
            "diastolic_bp": 74,
            "oxygen_saturation_percent": 98,
            "associated_symptoms": frozenset({"dysuria", "frequency"}),
            "expected_resources": (EsiResource.labs, EsiResource.iv_fluids),
        },
    ),
    _Scenario(
        "syn-019",
        "Back pain needing imaging and labs",
        {
            "age_years": 55.0,
            "presenting_complaint": "back pain after lifting a heavy box",
            "illness_duration_hours": 6.0,
            "pain_level": 6,
            "temperature_c": 37.0,
            "heart_rate_bpm": 86,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 140,
            "diastolic_bp": 86,
            "oxygen_saturation_percent": 97,
            "associated_symptoms": frozenset({"muscle spasm"}),
            "expected_resources": (EsiResource.labs, EsiResource.x_ray),
        },
    ),
    _Scenario(
        "syn-020",
        "Migraine needing intravenous treatment",
        {
            "age_years": 26.0,
            "presenting_complaint": "migraine with photophobia",
            "illness_duration_hours": 18.0,
            "pain_level": 6,
            "temperature_c": 36.8,
            "heart_rate_bpm": 76,
            "respiratory_rate_bpm": 14,
            "systolic_bp": 116,
            "diastolic_bp": 72,
            "oxygen_saturation_percent": 99,
            "associated_symptoms": frozenset({"photophobia", "nausea"}),
            "medical_history": frozenset({"migraine"}),
            "expected_resources": (
                EsiResource.iv_medications,
                EsiResource.labs,
            ),
        },
    ),
    # Low urgency: ESI 4 (one resource) and ESI 5 (no resources).
    _Scenario(
        "syn-021",
        "Sore throat needing a throat swab",
        {
            "presenting_complaint": "sore throat for two days",
            "expected_resources": (EsiResource.labs,),
        },
    ),
    _Scenario(
        "syn-022",
        "Ankle sprain needing an x-ray",
        {
            "age_years": 19.0,
            "presenting_complaint": "twisted ankle, able to walk",
            "illness_duration_hours": 4.0,
            "pain_level": 4,
            "temperature_c": 36.9,
            "heart_rate_bpm": 80,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 120,
            "diastolic_bp": 76,
            "oxygen_saturation_percent": 99,
            "associated_symptoms": frozenset({"ankle swelling"}),
            "expected_resources": (EsiResource.x_ray,),
        },
    ),
    _Scenario(
        "syn-023",
        "Small laceration needing a simple repair",
        {
            "presenting_complaint": "small forearm laceration",
            "illness_duration_hours": 2.0,
            "pain_level": 3,
            "temperature_c": 36.8,
            "heart_rate_bpm": 76,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 114,
            "diastolic_bp": 70,
            "oxygen_saturation_percent": 99,
            "expected_resources": (EsiResource.simple_procedure,),
        },
    ),
    _Scenario(
        "syn-024",
        "Uncomplicated urinary tract infection",
        {
            "presenting_complaint": "burning on urination",
            "illness_duration_hours": 36.0,
            "pain_level": 3,
            "temperature_c": 37.3,
            "heart_rate_bpm": 78,
            "respiratory_rate_bpm": 16,
            "systolic_bp": 114,
            "diastolic_bp": 70,
            "oxygen_saturation_percent": 99,
            "expected_resources": (EsiResource.labs,),
        },
    ),
    _Scenario(
        "syn-025",
        "Medication refill with no tests expected",
        {
            "age_years": 52.0,
            "sex": "male",
            "presenting_complaint": "needs blood pressure medication refill",
            "illness_duration_hours": 24.0,
            "pain_level": 1,
            "temperature_c": 36.6,
            "heart_rate_bpm": 72,
            "respiratory_rate_bpm": 14,
            "systolic_bp": 150,
            "diastolic_bp": 92,
            "oxygen_saturation_percent": 98,
            "medical_history": frozenset({"hypertension"}),
            "expected_resources": (),
        },
    ),
    _Scenario(
        "syn-026",
        "Poison ivy rash needing only an examination",
        {
            "age_years": 10.0,
            "sex": "male",
            "presenting_complaint": "itchy rash after poison ivy",
            "illness_duration_hours": 24.0,
            "pain_level": 2,
            "temperature_c": 36.7,
            "heart_rate_bpm": 84,
            "respiratory_rate_bpm": 18,
            "systolic_bp": 104,
            "diastolic_bp": 64,
            "oxygen_saturation_percent": 99,
            "associated_symptoms": frozenset({"rash", "itching"}),
            "expected_resources": (),
        },
    ),
    _Scenario(
        "syn-027",
        "Repeat prescription request",
        {
            "age_years": 67.0,
            "presenting_complaint": "requesting a repeat prescription",
            "illness_duration_hours": 72.0,
            "pain_level": 1,
            "temperature_c": 36.5,
            "heart_rate_bpm": 70,
            "respiratory_rate_bpm": 14,
            "systolic_bp": 136,
            "diastolic_bp": 80,
            "oxygen_saturation_percent": 98,
            "expected_resources": (),
        },
    ),
)


def _jitter(presentation: Presentation, rng: random.Random) -> Presentation:
    """Vary measurable values without moving a case across a rubric boundary.

    The amplitudes are deliberately small: a high-risk case stays high risk, a
    medium case keeps its resource count, and a stable low case stays stable.
    """
    systolic = presentation.systolic_bp + rng.randint(-3, 3)
    diastolic = presentation.diastolic_bp + rng.randint(-2, 2)
    if systolic <= diastolic:
        systolic = diastolic + 1
    return replace(
        presentation,
        temperature_c=round(presentation.temperature_c + rng.uniform(-0.1, 0.1), 1),
        heart_rate_bpm=presentation.heart_rate_bpm + rng.randint(-2, 2),
        respiratory_rate_bpm=presentation.respiratory_rate_bpm + rng.randint(-1, 1),
        systolic_bp=systolic,
        diastolic_bp=diastolic,
        oxygen_saturation_percent=presentation.oxygen_saturation_percent
        + rng.randint(-1, 1),
        pain_level=max(0, min(10, presentation.pain_level + rng.randint(-1, 1))),
    )


def _notes(presentation: Presentation) -> str:
    associated = ", ".join(sorted(presentation.associated_symptoms)) or "none"
    history = ", ".join(sorted(presentation.medical_history)) or "none"
    return (
        f"Rubric-only observations: respiratory rate {presentation.respiratory_rate_bpm}/min; "
        f"mental status {presentation.mental_status.value}; "
        f"new onset altered mental status: {presentation.new_onset_altered_mental_status}; "
        f"onset {presentation.onset}; associated symptoms: {associated}; "
        f"mechanism of injury: {presentation.mechanism_of_injury or 'none'}; "
        f"past history: {history}."
    )


def _to_encounter(
    encounter_id: str, presentation: Presentation
) -> LabelledEncounter:
    intake = EncounterIntake(
        presenting_complaint=presentation.presenting_complaint,
        pain_level=presentation.pain_level,
        illness_duration_hours=presentation.illness_duration_hours,
        temperature_c=presentation.temperature_c,
        heart_rate_bpm=presentation.heart_rate_bpm,
        systolic_bp=presentation.systolic_bp,
        diastolic_bp=presentation.diastolic_bp,
        oxygen_saturation_percent=presentation.oxygen_saturation_percent,
        notes=_notes(presentation),
    )
    return LabelledEncounter(
        encounter_id=encounter_id,
        patient_age_years=presentation.age_years,
        patient_sex=presentation.sex,
        intake=intake,
        presentation=presentation,
        ground_truth=label(presentation),
    )


def generate(seed: int = DEFAULT_SEED) -> tuple[LabelledEncounter, ...]:
    """Generate the corpus deterministically from a fixed seed."""
    rng = random.Random(seed)
    baseline = _baseline()
    encounters: list[LabelledEncounter] = []
    for scenario in _SCENARIOS:
        presentation = replace(baseline, **scenario.overrides)
        encounters.append(_to_encounter(scenario.encounter_id, _jitter(presentation, rng)))
    return tuple(encounters)
