# Ground-truth rubric: Urgency Level from ESI v4

**Rubric version:** `esi-v4-rubric-v1.0.0`

This is the independent standard against which the Prioritization Engine is
scored. It was written from the published Emergency Severity Index (ESI)
version 4 criteria, not from the Engine's rules or feature representation. It is
used only for evaluation: ESI levels never appear in the product UI, and a
rubric label is never a Machine Recommendation or a Final Decision.

## Published source

> Gilboy N, Tanabe P, Travers D, Rosenau AM. *Emergency Severity Index (ESI): A
> Triage Tool for Emergency Department Care, Version 4.* Implementation
> Handbook, 2012 Edition. AHRQ Publication No. 12-0014. Rockville, MD: Agency
> for Healthcare Research and Quality; November 2011.
>
> Online locator: <https://esitriage.org/handbook.asp>

Page references below are the printed page numbers of that handbook. The
danger-zone vital-sign thresholds are transcribed from Figure 5-1 on page 35.
The ESI algorithm and its resource list are in Chapter 2 (Figures 2-1, 2-1a and
2-2; Tables 2-1, 2-3 and 2-4). High-risk examples and severe pain/distress are
in Chapters 2 and 3, including Table 3-1.

## Output mapping

ESI is a five-level scale. The product uses a three-level Urgency Level
(`CONTEXT.md`), so the rubric first assigns an ESI level and then coarsens it:

| ESI level | Urgency Level |
| --- | --- |
| ESI 1 | High |
| ESI 2 | High |
| ESI 3 | Medium |
| ESI 4 | Low |
| ESI 5 | Low |

Every valid presentation matches exactly one ordered rule, and therefore
exactly one Urgency Level.

## Inputs

The description is deliberately richer than the Engine's feature vector. The
Engine sees a recognised Symptom Group, pain level, illness duration, age and
four vitals (temperature, heart rate, blood pressure and oxygen saturation).
The rubric additionally uses respiratory rate (an ESI vital sign the Engine does
not receive as a structured feature), mental status, new-onset mental status
change, onset, associated symptoms, mechanism of injury, past medical history,
high-risk flags and expected ESI resources.

| Input | Used by the Engine? | Used by this rubric? |
| --- | --- | --- |
| Age | Yes | Yes, including age-specific danger-zone thresholds |
| Sex | No | Recorded |
| Presenting complaint (raw description) | Only as a Symptom Group | Yes, as the clinical description |
| Onset (sudden / gradual / unknown) | No | Yes, when deciding high-risk flags |
| Illness duration | Yes | Yes, as part of the description |
| Pain level (0-10) | Yes | Yes |
| Pain needing intervention beyond triage (clinical judgement) | No | Yes |
| Temperature | Yes | Yes |
| Heart rate | Yes | Yes |
| Respiratory rate | No structured feature | Yes |
| Systolic / diastolic blood pressure | Yes | Recorded; ESI does not use blood pressure for acuity |
| Oxygen saturation | Yes | Yes |
| Mental status (AVPU) | No | Yes |
| New-onset altered mental status | No | Yes |
| Associated symptoms | No | Yes, when deciding high-risk flags |
| Mechanism of injury | No | Yes, when deciding high-risk flags |
| Past medical history / medications | No | Yes, when deciding high-risk flags |
| High-risk flags (derived from the fields above) | No | Yes |
| Expected ESI resources | No | Yes |

`high_risk_flags` is not an extra source of truth: the rubric user sets it from
the described history, mechanism, onset and associated symptoms when they fit a
published ESI level-2 high-risk example. The flag makes that clinical judgement
explicit and testable.

## Ordered rules

The rules are applied from top to bottom. The first rule that applies wins.

| # | Rule id | Condition | ESI | Urgency | Source |
| --- | --- | --- | --- | --- | --- |
| 1 | `esi_1_immediate_life_saving_intervention` | Immediate life-saving intervention is required (airway, breathing, circulation, or a major change in level of consciousness) | 1 | High | Chapter 2, p. 8, Figure 2-1a; Table 2-1, p. 10 |
| 2 | `esi_1_severe_respiratory_distress` | Severe respiratory distress | 1 | High | Chapter 2, p. 8, Figure 2-1a |
| 3 | `esi_1_hypoxaemia` | Oxygen saturation below 90 percent | 1 | High | Chapter 2, p. 8, Figure 2-1a; p. 10 |
| 4 | `esi_1_unresponsive` | AVPU is P (responds only to pain) or U (unresponsive) | 1 | High | Chapter 2, p. 10, Table 2-2 |
| 5 | `esi_2_high_risk_situation` | The presentation is a high-risk situation: it could deteriorate or needs time-sensitive treatment | 2 | High | Chapter 2, pp. 11-12; Chapter 3, Table 3-1 |
| 6 | `esi_2_new_onset_altered_mental_status` | New onset confusion, lethargy or disorientation (chronic dementia does not count) | 2 | High | Chapter 2, pp. 11-12; Chapter 3, p. 26 |
| 7 | `esi_2_severe_pain` | Pain is 7/10 or more and needs intervention beyond what triage can provide | 2 | High | Chapter 2, p. 12; Chapter 3, p. 26 |
| 8 | `esi_2_severe_distress` | Severe physiological or psychological distress | 2 | High | Chapter 2, p. 13; Chapter 3, p. 27 |
| 9 | `esi_2_danger_zone_vitals` | An age-specific danger-zone vital sign is exceeded (see table below) | 2 | High | Chapter 5, Figure 5-1, p. 35 |
| 10 | `esi_3_two_or_more_resources` | Two or more ESI resource types are expected | 3 | Medium | Chapter 2, pp. 13-14, Tables 2-3 and 2-4; Chapter 4 |
| 11 | `esi_4_one_resource` | Exactly one ESI resource type is expected | 4 | Low | Chapter 2, p. 14, Tables 2-3 and 2-4; Chapter 4 |
| 12 | `esi_5_no_resources` | No ESI resource types are expected | 5 | Low | Chapter 2, p. 14, Tables 2-3 and 2-4; Chapter 4 |

A pain score of 7 or more is not automatically ESI 2 in the handbook: the
triage nurse must judge that the pain needs intervention beyond triage. The
rubric makes that judgement an explicit input
(`pain_requires_intervention_beyond_triage`) so that labelling stays
deterministic.

## Danger-zone vital signs

Transcribed from Figure 5-1, page 35. "Exceeded" means strictly greater than
the listed value, except oxygen saturation, which is below the listed value.

| Age band | Heart rate | Respiratory rate | Oxygen saturation |
| --- | --- | --- | --- |
| Under 3 months | > 180 | > 50 | Not specified in the figure |
| 3 months to under 3 years | > 160 | > 40 | Not specified in the figure |
| 3 years to under 8 years | > 140 | > 30 | Not specified in the figure |
| 8 years and over | > 100 | > 20 | < 92 percent |

The handbook uses the band label "over 8 years". This rubric treats exactly 8
years as the adult band.

## Counting resources

The resource vocabulary and counting rule follow Table 2-3:

- Labs, ECG, x-ray, CT, MRI, ultrasound, angiography, IV fluids, IV/IM/
  nebulised medications, specialty consultation and a simple procedure each
  count as one resource type.
- A complex procedure (for example conscious sedation) counts as two.
- History and physical, point-of-care testing, saline or heplock, oral
  medications, tetanus immunisation, prescription refills, a phone call to a
  primary care provider, simple wound care and crutches/splints/slings are not
  resources.

Duplicate resource types are rejected rather than counted twice.

## Determinism and limits

- Given the same `Presentation`, the labeller returns the same label. There is
  no randomness, model or engine call in the rubric or labeller.
- The rubric rejects invalid or incomplete presentations rather than guessing.
- This is an evaluation instrument written from published ESI criteria. It is
  not a clinical decision tool and is not used at the point of care.
- The synthetic corpus is generated from a fixed seed, and every label in it is
  the output of this rubric. Labels live under the `ground_truth` key in the
  corpus; the corpus has no `machine_recommendation` field.

## Corpus format

The committed corpus is a JSON document with these top-level keys:

```json
{
  "schema_version": 1,
  "rubric_version": "esi-v4-rubric-v1.0.0",
  "rubric_citation": "...",
  "rubric_document": "evaluation/RUBRIC.md",
  "generator_version": "1.0.0",
  "seed": 20261103,
  "encounter_count": 27,
  "ground_truth_namespace": "ground_truth",
  "encounters": []
}
```

Each Encounter entry carries:

- `patient`: `age_years` and `sex`.
- `intake`: the fields the product's Encounter stores (complaint, pain,
  duration, the four vitals and free-text notes). The notes repeat the
  rubric-only observations so the record is self-describing.
- `presentation`: every input the rubric saw, including respiratory rate,
  mental status, onset, associated symptoms, mechanism, history, high-risk
  flags and expected resources.
- `ground_truth`: `urgency_level`, `esi_level`, `rubric_version` and
  `matched_rule`. This is the only label namespace. There is deliberately no
  `machine_recommendation`, `final_decision` or `override` field.

`evaluation.corpus.load_corpus(path)` returns a typed `Corpus` without
regenerating anything. `python -m evaluation.corpus` regenerates the committed
file from the recorded seed.

## Versioning

The rubric version is part of the corpus metadata and of every ground-truth
label (`ground_truth.rubric_version`). The committed corpus is
`backend/evaluation/corpus/esi-v4-rubric-v1.0.0.json`. Any change to a rule, a
threshold or the input vocabulary must increment the rubric version and produce
a new corpus file rather than silently editing the existing one.
