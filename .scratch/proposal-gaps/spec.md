# Spec — Closing the proposal gaps

Status: **ready-for-agent**

Vocabulary follows `CONTEXT.md`. Where a term is capitalised (Patient, Encounter, Triage Assessment, Urgency Level, Machine Recommendation, Final Decision, Override, Override Reason, Re-assessment, Departure, Queue, Prioritization Engine, Symptom Group, Report, Clinical, Administrator), it carries the meaning defined there.

---

## Problem Statement

A gap analysis of the completed build against the project proposal report found the system realises approximately 85% of what the proposal commits to. Three of the four shortfalls are addressable in code:

1. **Respiratory rate is never captured.** The proposal lists it explicitly in §1.3 ("vital signs such as temperature, pulse, blood pressure, respiratory rate, and oxygen saturation"). The intake collects temperature, heart rate, blood pressure and oxygen saturation, but not respiratory rate. The rubric that scores the engine already models it (`evaluation/rubric.py`), so the omission is a build gap, not a scope decision.

2. **Patient history is not searchable.** The proposal's enhanced functions (§1.2.2) promise "searchable patient history". The build can list recent Encounters and open one by id, but there is no way to find a Patient by name or to see one Patient's Encounters over time.

3. **There is no audit log.** The proposal's enhanced functions (§1.2.2) promise "audit logs". The build records who performed an Override and why, but nothing else. Registration, intake, correction, Re-assessment and Departure leave no attributable record beyond the row they mutate.

The fourth shortfall — classifier accuracy below the majority baseline — is a property of the training data (the available open source records no complaint, pain, illness duration or respiratory rate) and is **out of scope** for this effort beyond making respiratory rate available to the classifier. It is documented in ADR 0005 and must continue to be reported honestly.

## Solution

Add respiratory rate to the intake as a first-class vital sign, with a documented red-flag safety rule and a classifier feature; add Patient search and a per-Patient history view; and add an append-only audit log covering every clinical mutation, readable by an Administrator.

Respiratory rate is wired in at three levels deliberately:

- **Capture** — it becomes part of the intake, the frozen Triage Assessment snapshot, and the board/queue display, so a clinician can record and see it.
- **Safety layer** — it gains age-banded tachypnoea red-flag rules drawn from the ESI danger-zone thresholds already transcribed in the rubric, so a patient breathing dangerously fast is raised to High even if the model would not.
- **Classifier feature** — it becomes a dimension of the feature vector. It is expected to carry a near-zero coefficient because the training source does not record it, exactly as pain level and illness duration already sit unused. It is added for contract completeness and to be ready for a better dataset, not because it is expected to improve accuracy.

Because the feature vector is a versioned contract between training and inference, adding a dimension requires a retrain and an artefact version bump. Shipping a code vector that disagrees with the shipped artefact would raise at runtime (`classifier.py` compares the two), so the two must move together.

## User Stories

### Respiratory rate

64. As a Clinical user, I want to record respiratory rate during intake, so that objective breathing effort is part of the assessment.
65. As a Clinical user, I want intake to reject an implausible respiratory rate, so that a typo cannot skew the recommendation.
66. As a Clinical user, I want respiratory rate carried into the frozen Triage Assessment snapshot, so that what was recorded at decision time survives for review.
67. As a Clinical user, I want time-waiting and detail views to show respiratory rate beside the other vitals, so that I can judge without opening another screen.
68. As a Clinical user, I want a dangerously fast respiratory rate to raise the recommendation to High, so that a patient in respiratory distress is never missed.
69. As a Clinical user, I want the tachypnoea red flag to be age-banded, so that a rate normal for an infant is not treated as normal for an adult.
70. As an examiner, I want each tachypnoea rule to carry its clinical citation, so that the safety layer remains defensible.
71. As the researcher, I want respiratory rate to be a dimension of the classifier feature vector, so that a future dataset recording it needs no code change.
72. As the researcher, I want a feature-vector change to force a retrain and an artefact version bump, so that a code/artefact mismatch cannot ship silently.

### Patient history

73. As a Clinical user, I want to search Patients by name, so that I can find a returning Patient without knowing their id.
74. As a Clinical user, I want to search Patients by contact number, so that I can find someone whose name I cannot spell.
75. As a Clinical user, I want to open one Patient's history and see their Encounters over time, so that a pattern across visits is visible.
76. As a Clinical user, I want each Encounter in the history to show its Urgency Level and Final Decision, so that I can see what happened at each visit.
77. As a Clinical user, I want evaluation-run Encounters excluded from Patient history, so that corpus data does not masquerade as a real visit.
78. As a Clinical user, I want an empty search to show nothing rather than everyone, so that the view is not a bulk export.

### Audit log

79. As an Administrator, I want every clinical mutation recorded with its actor and timestamp, so that I can see who did what and when.
80. As an Administrator, I want registration, intake, correction, Override, Re-assessment and Departure all covered, so that no state-changing action is invisible.
81. As an Administrator, I want to filter the audit log to one Encounter, so that I can reconstruct a single visit.
82. As an Administrator, I want the audit log to be append-only, so that a record cannot be quietly edited after the fact.
83. As an Administrator, I want the audit log readable and no more, so that oversight stays separate from care.
84. As a Clinical user, I want my name attached to my actions, so that accountability is real rather than anonymous.
85. As the researcher, I want an audit entry written in the same transaction as the change it describes, so that a change without its record is impossible.

## Implementation Decisions

**Respiratory rate bounds.** Validated `ge=0 le=80`, matching the bound already used by `evaluation/rubric.py`'s `Presentation`. The rubric is the existing clinical source of truth for this range; the intake must not invent a second one.

**Tachypnoea thresholds.** The four age bands are taken verbatim from the ESI danger-zone thresholds already transcribed in `evaluation/rubric.py` (`danger_zone_exceeded`): over 50 under 3 months, over 40 under 3 years, over 30 from 3 to under 8 years, over 20 at 8 years and over. These are the same bands the heart-rate rules already use, so the respiratory rules join the existing set rather than introducing a second scheme. Each rule carries a citation in the established style.

**Age granularity limitation.** `age` is whole years, so the "under 3 months" band cannot be distinguished from "3 months to under 3 years". The respiratory rules therefore use the same coarsening the heart-rate rules already apply, and the module docstring must state this rather than hide it.

**Feature vector is a contract.** `SCALAR_FEATURE_NAMES` in `features.py` is the single definition of the scalar dimensions, used by both training and inference. Respiratory rate is appended. Because `classifier.py` raises when the loaded artefact's `feature_names` differ from the code's, the change requires retraining and bumping the artefact version from `urgency-classifier-v1.0.0` to `v1.1.0`. The version is referenced in `app/classifier.py`, `evaluation/triage_datasets.py`, `evaluation/train_classifier.py`, and `evaluation/artefact.py`; all must move together.

**Missing-value sentinel.** The training source records no respiratory rate. Rather than substitute a plausible number, the loader uses a sentinel outside the intake's producible domain, following the existing `MISSING_PAIN_LEVEL` / `MISSING_ILLNESS_DURATION_HOURS` convention, so a model trained on it can still learn from the value where it is recorded.

**Expected effect on accuracy.** None, or a small shift. The added dimension is constant in training. The retrain exists to keep the contract honest, not to improve the score, and the reported figures must not be presented as an improvement.

**Patient search semantics.** Search is deliberately looser than identity resolution. `patients.py` documents that a name alone is never sufficient to *match an identity*; that rule is untouched. A search is a discovery aid and may match partially. The distinction must be preserved in code comments so a future reader does not collapse them.

**Search input discipline.** A blank or whitespace-only query returns an empty result, not the whole patient table. Results are capped by a limit parameter following the existing `GET /encounters` pattern.

**Evaluation-run exclusion.** Patient history excludes Encounters carrying an `evaluation_run_id`, as the Queue already does, so corpus rows never appear as patient visits.

**Audit log shape.** A new table modelled on `Override`: an actor foreign key loaded with `lazy="joined"`, a validated-string action column constrained to a fixed set (the same pattern as the Override Reason constraint), a timezone-aware timestamp defaulting to `utc_now`, an optional detail column, and nullable subject foreign keys to the Patient, Encounter and Assessment involved. Append-only is enforced in the application layer with a `before_update` guard, mirroring the Triage Assessment guard — there are no database triggers (ADR 0001).

**Audit write discipline.** The audit entry is added to the session in the same transaction as the change it describes, and the route commits. Domain functions continue not to commit, following `overrides.perform_override`. Registration is the one exception worth care: `patients.find_or_create_patient` commits internally, so the audit entry must be added before that commit or the commit lifted out — the transaction boundary must be verified, not assumed.

**Audit read path.** Administrator-only, following the existing report routes. A Clinical user is refused, consistent with every other Administrator surface.

**Schema creation.** There is no migration tooling: tables are created from the models at startup. A new table appears automatically, but new *columns* on existing tables do not — an existing local database must be deleted and re-seeded. Tests use a fresh database per run and are unaffected.

## Testing Decisions

**What a good test is here.** Tests assert external behaviour: the recommendation returned for given inputs, the rows a mutation leaves behind, the result set a search returns. They never assert internal structure or that a rule "lives in function X". Because the engine is deterministic, constructed inputs still assert exact Urgency Levels; the retrain may re-anchor some expected levels, and where it does, the new expectation is stated deliberately rather than fitted to whatever came out.

**Respiratory rate.** Bounds are rejected above and below (boundary and just-past). Each tachypnoea band fires at the boundary and does not fire one below it, at a representative age in the band. The existing tests asserting the feature-vector length are updated to the new count. The snapshot round-trip carries respiratory rate into and out of a stored Assessment.

**Safety layer.** A presentation with a normal respiratory rate and no other flag is unaffected. A presentation with a dangerous respiratory rate is raised to High. The `vitals` attribution names `respiratory_rate_bpm` so the board highlights the right field.

**Patient search.** A partial name matches; a contact number matches; a blank query returns nothing; the result count honours the limit; an evaluation-run Encounter does not appear in a Patient's history.

**Audit log.** Each of the six mutations writes exactly one entry naming the correct actor and action; an Administrator can read the log and a Clinical user cannot; and an in-place edit of an existing entry is rejected. The transaction property is asserted directly: a mutation that rolls back leaves no audit entry.

**Regression.** The full existing suite must remain green. Its fixtures construct intake payloads and feature vectors in many places; those are updated mechanically to include respiratory rate, without loosening any existing assertion.

## Out of Scope

- Improving classifier accuracy. This effort makes respiratory rate available to the model and leaves the reported figures honest.
- Commuting the missing VC++ runtime into the repository. The local toolchain fix is recorded in the ticket comments; making it reproducible for other machines is a separate concern.
- Authentication events (login, logout, password change) in the audit log. The log covers clinical mutations.
- Audit-log retention, export, or tamper-evident hashing.
- Machine-quality search (fuzzy matching, phonetic matching, ranking by relevance).
- Any change to the identity-matching rule in `patients.find_or_create_patient`.
- A frontend automated test harness; the new screens are covered by smoke and manual testing, as the existing scope states.

## Further Notes

- **The proposal's §1.2.2 list is the acceptance reference.** Searchable patient history and audit logs are the two items it names that the build did not have; respiratory rate is the vital sign §1.3 names that intake did not collect.
- **ADR to write:** the audit log's shape and its append-only-in-application-layer decision, which follows ADR 0001's no-triggers constraint.
- **ADR 0005 to update:** its "51 of 57 features are constant" sentence becomes stale when the vector grows to 58 dimensions, and its statement of the accuracy remains the honest figure to carry forward.
- **The feature-vector change is the riskiest step.** It touches training, inference, the evaluation harness and the dashboard's accuracy report at once. It is deliberately sequenced last among the respiratory-rate work.
