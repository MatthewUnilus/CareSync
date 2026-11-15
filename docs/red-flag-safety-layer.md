# Red-flag safety layer

`backend/app/red_flags.py` is the deterministic safety layer between the trained
classifier and the Machine Recommendation. It is layer (2) of the Prioritization
Engine described in `spec.md`; ticket 08's cached fallback is layer (3).

The layer exists because the shipped interim classifier is trained on a source
with no pain level, illness duration or complaint, reacts only to age and the
four vitals, and scores below the majority baseline
(`backend/evaluation/datasets/README.md`). On its own it can call an otherwise
quiet, hypoxaemic young adult Low. Every red flag that raises such a
presentation comes from the rules below, not from the model.

## How it composes

- It runs **after** the classifier, over the same `PrioritisationInputs`.
- If any rule fires and the classifier's answer is Medium or Low, the result is
  **High**.
- If no rule fires, the classifier's answer is returned unchanged — the same
  enum member, not a re-derived copy.
- There is no branch that can return a lower Urgency Level. A High stays High.
- The result is the Machine Recommendation stored on the Triage Assessment and
  the level the Queue orders by. The UI needs no change.
- It is pure: no database, no session, no I/O, no clock, no randomness. The
  three-second budget is met many times over.

## The rules explain themselves to the board

Each rule also names the intake fields it keys on (`RedFlagRule.vitals`, using the
field names in `app.schemas.IntakePayload`; empty for the symptom rules). The API
exposes every fired rule on `AssessmentResponse.red_flags`, and the Queue card
renders them under **"Why this is High"** with the rule's citation, marking the
exact vital that fired.

This is deliberately one source of truth. The card does not restate the
thresholds: the flags are re-derived server-side from the Assessment's frozen
snapshot via `app.assessments.inputs_from_assessment` and the same `fired_rules`
the safety layer runs. So what a clinician reads as the reason for a
recommendation cannot drift from the recommendation itself, and marking a value
abnormal in the client is driven by the server's rule set rather than a second
copy. A test asserts every `vitals` name is a real `IntakePayload` field, so a
rule cannot name a field that does not exist and be silently dropped.

## The rules

Thresholds follow the ESI convention: "exceeded" means strictly greater than
the listed value, except oxygen saturation, which is below it. Vital rules state
their age band; symptom rules key on a Symptom Group recognised from the
presenting complaint.

| Rule id | Fires when | Clinical citation |
| --- | --- | --- |
| `oxygen_saturation_below_90` | Oxygen saturation below 90 percent at any age | ESI v4, Chapter 2, p. 8 (Figure 2-1a) and p. 9 (SpO2 below 90 percent is listed as a level-1 criterion); RUBRIC.md rule esi_1_hypoxaemia |
| `adult_hypoxaemia` | Oxygen saturation below 92 percent at age 8 or over | ESI v4, Chapter 5, Figure 5-1, p. 35; RUBRIC.md rule esi_2_danger_zone_vitals |
| `infant_tachycardia` | Heart rate above 160 bpm under age 3 | ESI v4, Chapter 5, Figure 5-1, p. 35; RUBRIC.md rule esi_2_danger_zone_vitals (the more sensitive of the under-3-months and 3-months-to-3-years bands) |
| `child_tachycardia` | Heart rate above 140 bpm from age 3 to under 8 | ESI v4, Chapter 5, Figure 5-1, p. 35; RUBRIC.md rule esi_2_danger_zone_vitals |
| `adult_tachycardia` | Heart rate above 100 bpm at age 8 or over | ESI v4, Chapter 5, Figure 5-1, p. 35, and p. 36; RUBRIC.md rule esi_2_danger_zone_vitals |
| `infant_fever` | Temperature above 38.0 C under age 1 | ESI v4, Chapter 5, Table 5-1, p. 37 (the 1-28 day and 1-3 month rows, which both use 38.0 C and at least ESI 2) |
| `adult_hypotension` | Systolic blood pressure below 90 mmHg at age 8 or over | ESI v4, Chapter 2, p. 10 (ESI level-1 examples: hypotension with signs of hypoperfusion; chest pain, pale, diaphoretic, blood pressure 70/palp) and Chapter 5, p. 37 (case example up-triaged for BP 90/60 with tachycardia). ESI's danger-zone box excludes blood pressure; this is a documented operationalisation. |
| `adult_severe_hypertension` | Systolic blood pressure 210 mmHg or more, or diastolic blood pressure 120 mmHg or more, at age 8 or over | ESI v4, Chapter 3, p. 18 (hypertensive crisis is a high-risk cardiovascular situation) and Table 3-1, p. 23 (blood pressure 210/120 with no known hypertension is high risk) |
| `chest_pain` | Chest pain recognised from the presenting complaint | ESI v4, Chapter 3, p. 18 (chest or epigastric discomfort suspicious for acute coronary syndrome is a high-risk ESI 2 presentation) and Table 3-1, p. 23 |
| `stroke_signs` | Slurred speech, facial droop or weakness on one side recognised from the presenting complaint | ESI v4, Chapter 2, p. 15 (left-arm weakness is ESI 2) and Chapter 3, p. 19 (sudden speech deficit or motor weakness is a possible acute stroke); Table 3-1, p. 24 |
| `altered_mental_status` | Altered mental status or confusion recognised from the presenting complaint | ESI v4, Chapter 3, p. 26 (new onset confusion, lethargy or disorientation is ESI 2); RUBRIC.md rule esi_2_new_onset_altered_mental_status |
| `seizure` | Seizure recognised from the presenting complaint | ESI v4, Chapter 3, p. 19 (all patients with a reported seizure meet ESI level-2 criteria) |
| `suicidal_or_self_harm` | Suicidal thoughts or self harm recognised from the presenting complaint | ESI v4, Chapter 3, p. 19 (patients who are suicidal or a danger to themselves are high risk) and Table 3-1, p. 24 |
| `major_haemorrhage` | Vomiting blood or uncontrolled bleeding recognised from the presenting complaint | ESI v4, Chapter 3, p. 21 (uncontrolled bleeding is a high-risk wound) and Table 3-1, p. 23 (vomiting blood with tachycardia is high risk for gastrointestinal bleeding) |
| `anaphylaxis` | Anaphylaxis recognised from the presenting complaint | ESI v4, Chapter 3, p. 17 (a patient with throat tightening after a known allergen is high risk for anaphylaxis) |
| `overdose` | Overdose recognised from the presenting complaint | ESI v4, Chapter 3, p. 21 (most overdoses are a high-risk situation and ESI 2 unless a lifesaving intervention is needed) |
| `head_injury` | Head injury recognised from the presenting complaint | ESI v4, Chapter 3, p. 21 (high-risk trauma includes head injury; loss of consciousness and raised intracranial pressure are assessed) and Table 3-1, p. 25 |
| `neck_stiffness` | Neck stiffness recognised from the presenting complaint | ESI v4, Chapter 3, Table 3-1, p. 24 (severe headache with a stiff neck, rash and fever is high risk for meningitis) |
| `vaginal_bleeding` | Vaginal bleeding recognised from the presenting complaint | ESI v4, Chapter 3, pp. 19-20 (possible ectopic pregnancy and heavy postpartum bleeding are ESI 2) and Table 3-1, p. 24 |
| `syncope` | Fainting recognised from the presenting complaint | ESI v4, Chapter 3, p. 19 (complaints of syncope or near syncope are high-risk general medical presentations) |

The published source is the ESI v4 handbook cited in
`backend/evaluation/RUBRIC.md`:

> Gilboy N, Tanabe P, Travers D, Rosenau AM. *Emergency Severity Index (ESI): A
> Triage Tool for Emergency Department Care, Version 4.* Implementation
> Handbook, 2012 Edition. AHRQ Publication No. 12-0014. Rockville, MD: Agency
> for Healthcare Research and Quality; November 2011.

`RUBRIC.md` is the independent evaluation standard; its rule ids are cited where
a rule implements the same ESI criterion. The rubric's danger-zone table and
pediatric temperature table are transcriptions of the handbook, so the
thresholds above agree with it.

## The boundary is deliberate

This is not a full ESI rule engine. It does not count expected resources, which
is the core of ESI levels 3-5. It does not assess AVPU or mental status,
respiratory rate, onset, pain needing intervention beyond triage, mechanism of
injury, past history, pregnancy status, immunocompromise or medications: none of
those is a structured engine input. It does not interpret free text; it sees
only the Symptom Groups recognised from it, and that recognition does not
understand negation ("no chest pain" is still *chest pain*). It does not assign
an ESI level, and it does not replace the Clinical user's judgement.

Over-triage is the accepted cost. A safety layer that misses a critical
presentation is worse than one that asks a clinician to look sooner.

Known consequences of the bounded design:

- `age` is whole years, so the handbook's "under 3 months" and "3 months to
  under 3 years" heart-rate bands cannot be separated. Every patient under 3
  gets the more sensitive threshold (160). The same applies to the 1-28 day and
  1-3 month fever bands: every patient under 1 is compared with 38.0 C.
- The 3-36 month fever band maps to ESI 3 (Medium), which this layer cannot
  express because it only raises to High. A 1-2 year old with a high fever may
  therefore stay at the classifier's answer.
- ESI's danger-zone box excludes blood pressure. The two adult blood-pressure
  rules are documented operationalisations of high-risk situations in the
  handbook's text, not danger-zone entries; they do not apply to children.
- Pain is not a red flag. The handbook requires the triage nurse to judge that
  the pain needs intervention beyond triage, which the engine does not receive;
  a pain score alone is not automatically ESI 2. A pain-only presentation can
  still be under-triaged.
- Shortness of breath, cough, fever in an adult, dizziness, palpitations and
  similar common groups do not fire on their own. They are rescued only when a
  vital threshold is also crossed.
- Four Symptom Groups marked as ESI red flags in the vocabulary do not have a
  rule of their own: `shortness of breath`, `coughing blood`, `low blood sugar`
  and `alcohol withdrawal`. Shortness of breath and alcohol withdrawal usually
  arrive with a heart rate or saturation the layer does catch; haemoptysis and
  hypoglycaemia can present with quiet vitals and remain a gap.

Tickets 08 and 14 should treat those as known limits, not defects: the fallback
must still run the safety layer over its own answer, and the Accuracy Evaluation
Report should show the False Low-Priority rate with the layer enabled and
disabled separately.

## Tests

`backend/tests/test_red_flags.py` has, for every rule, a presentation that fires
and the same presentation one step outside the threshold that does not. It also
asserts that no rule can lower a recommendation, that a no-flag presentation
returns the classifier's exact enum member, that every firing case is one the
classifier alone would not call High, that the layer stays inside the
three-second budget, that every rule and citation appears in this document, and
that the composed recommendation is what the Assessment stores and the Queue
orders by.
