"""The red-flag safety layer between the classifier and the recommendation.

The Prioritization Engine composes three layers (``spec.md``, "Prioritization
Engine composition"): the trained classifier, this deterministic safety layer,
and ticket 08's cached fallback. This module is layer two. It runs *after* the
classifier and can only raise a recommendation to High; it can never lower one.
A presentation with no firing rule is returned exactly as the classifier
produced it.

Why the layer exists
--------------------
The shipped interim classifier is trained on a source that records no pain
level, no illness duration and no complaint, so it reacts only to age and the
four vitals and is below the majority baseline (see
``evaluation/datasets/README.md``). Left alone it can call a hypoxaemic young
adult Low. Every red flag below therefore comes from the deterministic rules,
not from the model.

The rule set is deliberately bounded
------------------------------------
This is *not* a full ESI rule engine. It implements twenty documented red-flag
rules drawn from ESI version 4; each carries a clinical citation, and the same
rules and citations are written out in ``docs/red-flag-safety-layer.md``. It
does not:

- count expected resources, which is the core of ESI levels 3-5;
- assess AVPU / mental status, respiratory rate, onset, pain needing
  intervention beyond triage, mechanism of injury, past history, pregnancy
  status, immunocompromise or medications — none of these is a structured
  input;
- interpret the free-text complaint; it sees only the Symptom Groups recognised
  from it, and recognition does not understand negation;
- assign an ESI level or replace clinical judgement. Raising a presentation is
  a safety behaviour that accepts over-triage in exchange for not missing a
  critically unwell patient.

Bounded consequences worth knowing:

- ``age`` is whole years, so the ESI danger-zone bands "under 3 months" and
  "3 months to under 3 years" cannot be distinguished. The layer applies the
  more sensitive heart-rate threshold (160) to every patient under 3, and the
  lower of the two infant fever bands to every patient under 1.
- ESI's danger-zone box does not include blood pressure. Two adult-only rules
  (hypotension and severe hypertension) are documented operationalisations of
  high-risk situations in the handbook's own text, not danger-zone entries.
- The 3-36 month fever band maps to ESI 3 (Medium), so it cannot be expressed
  as a rule that raises to High and is deliberately omitted.

The layer is pure: it takes the same ``PrioritisationInputs`` the classifier
takes, touches no database or session, and is deterministic. Iterating twenty
predicates is a few microseconds, well inside the three-second budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # pragma: no cover - only needed by type checkers
    from app.prioritisation import PrioritisationInputs, UrgencyLevel


@dataclass(frozen=True)
class RedFlagRule:
    """One red flag, the finding it keys on, and its clinical citation.

    ``vitals`` names the captured intake fields this rule keys on, using the
    names in :class:`app.schemas.IntakePayload`. It is empty for the rules that
    key on recognised Symptom Groups instead of a measured value. The board uses
    it to mark the exact abnormal value a rule fired on, so what the clinician
    sees highlighted is derived from these thresholds rather than restated in
    the client.
    """

    id: str
    finding: str
    citation: str
    fires: Callable[["PrioritisationInputs"], bool]
    vitals: tuple[str, ...] = ()


def _any_group(*groups: str) -> Callable[["PrioritisationInputs"], bool]:
    """Return a predicate that is true when any of ``groups`` was recognised."""
    wanted = frozenset(groups)

    def fires(inputs: "PrioritisationInputs") -> bool:
        return bool(wanted.intersection(inputs.recognised_symptom_groups))

    return fires


#: Every red flag the layer knows, in the order they are documented.
#: Thresholds use the ESI convention: "exceeded" is strictly greater than the
#: listed value, except oxygen saturation, which is below it.
RULES: tuple[RedFlagRule, ...] = (
    RedFlagRule(
        id="oxygen_saturation_below_90",
        finding="Oxygen saturation below 90 percent at any age",
        citation=(
            "ESI v4, Chapter 2, p. 8 (Figure 2-1a) and p. 9 (SpO2 below 90 "
            "percent is listed as a level-1 criterion); RUBRIC.md rule "
            "esi_1_hypoxaemia"
        ),
        fires=lambda inputs: inputs.oxygen_saturation_percent < 90,
        vitals=("oxygen_saturation_percent",),
    ),
    RedFlagRule(
        id="adult_hypoxaemia",
        finding="Oxygen saturation below 92 percent at age 8 or over",
        citation=(
            "ESI v4, Chapter 5, Figure 5-1, p. 35; "
            "RUBRIC.md rule esi_2_danger_zone_vitals"
        ),
        fires=lambda inputs: (
            inputs.age >= 8 and inputs.oxygen_saturation_percent < 92
        ),
        vitals=("oxygen_saturation_percent",),
    ),
    RedFlagRule(
        id="infant_tachycardia",
        finding="Heart rate above 160 bpm under age 3",
        citation=(
            "ESI v4, Chapter 5, Figure 5-1, p. 35; "
            "RUBRIC.md rule esi_2_danger_zone_vitals (the more sensitive of "
            "the under-3-months and 3-months-to-3-years bands)"
        ),
        fires=lambda inputs: inputs.age < 3 and inputs.heart_rate_bpm > 160,
        vitals=("heart_rate_bpm",),
    ),
    RedFlagRule(
        id="child_tachycardia",
        finding="Heart rate above 140 bpm from age 3 to under 8",
        citation=(
            "ESI v4, Chapter 5, Figure 5-1, p. 35; "
            "RUBRIC.md rule esi_2_danger_zone_vitals"
        ),
        fires=lambda inputs: (
            3 <= inputs.age < 8 and inputs.heart_rate_bpm > 140
        ),
        vitals=("heart_rate_bpm",),
    ),
    RedFlagRule(
        id="adult_tachycardia",
        finding="Heart rate above 100 bpm at age 8 or over",
        citation=(
            "ESI v4, Chapter 5, Figure 5-1, p. 35, and p. 36; "
            "RUBRIC.md rule esi_2_danger_zone_vitals"
        ),
        fires=lambda inputs: inputs.age >= 8 and inputs.heart_rate_bpm > 100,
        vitals=("heart_rate_bpm",),
    ),
    RedFlagRule(
        id="infant_fever",
        finding="Temperature above 38.0 C under age 1",
        citation=(
            "ESI v4, Chapter 5, Table 5-1, p. 37 (the 1-28 day and 1-3 month "
            "rows, which both use 38.0 C and at least ESI 2)"
        ),
        fires=lambda inputs: (
            inputs.age < 1 and inputs.temperature_c > 38.0
        ),
        vitals=("temperature_c",),
    ),
    RedFlagRule(
        id="adult_hypotension",
        finding="Systolic blood pressure below 90 mmHg at age 8 or over",
        citation=(
            "ESI v4, Chapter 2, p. 10 (ESI level-1 examples: hypotension with "
            "signs of hypoperfusion; chest pain, pale, diaphoretic, blood "
            "pressure 70/palp) and Chapter 5, p. 37 (case example up-triaged "
            "for BP 90/60 with tachycardia). ESI's danger-zone box excludes "
            "blood pressure; this is a documented operationalisation."
        ),
        fires=lambda inputs: (
            inputs.age >= 8 and inputs.systolic_bp < 90
        ),
        vitals=("blood_pressure",),
    ),
    RedFlagRule(
        id="adult_severe_hypertension",
        finding=(
            "Systolic blood pressure 210 mmHg or more, or diastolic blood "
            "pressure 120 mmHg or more, at age 8 or over"
        ),
        citation=(
            "ESI v4, Chapter 3, p. 18 (hypertensive crisis is a high-risk "
            "cardiovascular situation) and Table 3-1, p. 23 (blood pressure "
            "210/120 with no known hypertension is high risk)"
        ),
        fires=lambda inputs: (
            inputs.age >= 8
            and (inputs.systolic_bp >= 210 or inputs.diastolic_bp >= 120)
        ),
        vitals=("blood_pressure",),
    ),
    RedFlagRule(
        id="chest_pain",
        finding="Chest pain recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 18 (chest or epigastric discomfort "
            "suspicious for acute coronary syndrome is a high-risk ESI 2 "
            "presentation) and Table 3-1, p. 23"
        ),
        fires=_any_group("chest pain"),
    ),
    RedFlagRule(
        id="stroke_signs",
        finding=(
            "Slurred speech, facial droop or weakness on one side recognised "
            "from the presenting complaint"
        ),
        citation=(
            "ESI v4, Chapter 2, p. 15 (left-arm weakness is ESI 2) and "
            "Chapter 3, p. 19 (sudden speech deficit or motor weakness is a "
            "possible acute stroke); Table 3-1, p. 24"
        ),
        fires=_any_group("slurred speech", "facial droop", "weakness on one side"),
    ),
    RedFlagRule(
        id="altered_mental_status",
        finding=(
            "Altered mental status or confusion recognised from the "
            "presenting complaint"
        ),
        citation=(
            "ESI v4, Chapter 3, p. 26 (new onset confusion, lethargy or "
            "disorientation is ESI 2); RUBRIC.md rule "
            "esi_2_new_onset_altered_mental_status"
        ),
        fires=_any_group("altered mental status", "confusion"),
    ),
    RedFlagRule(
        id="seizure",
        finding="Seizure recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 19 (all patients with a reported seizure "
            "meet ESI level-2 criteria)"
        ),
        fires=_any_group("seizure"),
    ),
    RedFlagRule(
        id="suicidal_or_self_harm",
        finding=(
            "Suicidal thoughts or self harm recognised from the presenting "
            "complaint"
        ),
        citation=(
            "ESI v4, Chapter 3, p. 19 (patients who are suicidal or a danger "
            "to themselves are high risk) and Table 3-1, p. 24"
        ),
        fires=_any_group("suicidal thoughts", "self harm"),
    ),
    RedFlagRule(
        id="major_haemorrhage",
        finding=(
            "Vomiting blood or uncontrolled bleeding recognised from the "
            "presenting complaint"
        ),
        citation=(
            "ESI v4, Chapter 3, p. 21 (uncontrolled bleeding is a high-risk "
            "wound) and Table 3-1, p. 23 (vomiting blood with tachycardia is "
            "high risk for gastrointestinal bleeding)"
        ),
        fires=_any_group("vomiting blood", "uncontrolled bleeding"),
    ),
    RedFlagRule(
        id="anaphylaxis",
        finding="Anaphylaxis recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 17 (a patient with throat tightening after "
            "a known allergen is high risk for anaphylaxis)"
        ),
        fires=_any_group("anaphylaxis"),
    ),
    RedFlagRule(
        id="overdose",
        finding="Overdose recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 21 (most overdoses are a high-risk "
            "situation and ESI 2 unless a lifesaving intervention is needed)"
        ),
        fires=_any_group("overdose"),
    ),
    RedFlagRule(
        id="head_injury",
        finding="Head injury recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 21 (high-risk trauma includes head injury; "
            "loss of consciousness and raised intracranial pressure are "
            "assessed) and Table 3-1, p. 25"
        ),
        fires=_any_group("head injury"),
    ),
    RedFlagRule(
        id="neck_stiffness",
        finding="Neck stiffness recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, Table 3-1, p. 24 (severe headache with a "
            "stiff neck, rash and fever is high risk for meningitis)"
        ),
        fires=_any_group("neck stiffness"),
    ),
    RedFlagRule(
        id="vaginal_bleeding",
        finding="Vaginal bleeding recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, pp. 19-20 (possible ectopic pregnancy and "
            "heavy postpartum bleeding are ESI 2) and Table 3-1, p. 24"
        ),
        fires=_any_group("vaginal bleeding"),
    ),
    RedFlagRule(
        id="syncope",
        finding="Fainting recognised from the presenting complaint",
        citation=(
            "ESI v4, Chapter 3, p. 19 (complaints of syncope or near syncope "
            "are high-risk general medical presentations)"
        ),
        fires=_any_group("fainting"),
    ),
)


def fired_rules(inputs: "PrioritisationInputs") -> tuple[RedFlagRule, ...]:
    """Return every red flag that fires for these inputs, in rule order."""
    return tuple(rule for rule in RULES if rule.fires(inputs))


def _has_red_flag(inputs: "PrioritisationInputs") -> bool:
    return any(rule.fires(inputs) for rule in RULES)


def apply_safety_layer(
    inputs: "PrioritisationInputs",
    recommendation: "UrgencyLevel",
) -> "UrgencyLevel":
    """Return ``recommendation``, raised to High when a red flag fires.

    The classifier's answer is returned unchanged — the same enum member — when
    no rule fires. There is no branch that can return a lower Urgency Level.
    """
    # Imported here so this module can be imported by ``prioritisation`` while
    # still naming the level it produces.
    from app.prioritisation import UrgencyLevel

    if recommendation is UrgencyLevel.high:
        return recommendation
    if _has_red_flag(inputs):
        return UrgencyLevel.high
    return recommendation


__all__ = [
    "RULES",
    "RedFlagRule",
    "apply_safety_layer",
    "fired_rules",
]
