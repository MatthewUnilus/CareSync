# 17: Respiratory rate — capture, safety layer and display

**What to build:** Respiratory rate becomes a first-class intake vital sign. It is captured, validated, frozen into the Triage Assessment snapshot, shown on the board and detail views, and backed by age-banded tachypnoea red-flag rules drawn from the ESI danger-zone thresholds already transcribed in the rubric. The classifier feature vector is **not** touched by this ticket — see 18.

**Blocked by:** none.

**Status:** open

- [ ] Intake accepts `respiratory_rate_bpm`, validated `ge=0 le=80` (matching `evaluation/rubric.py`'s `Presentation` bound), and rejects values outside that range with a clear error.
- [ ] `PrioritisationInputs` carries `respiratory_rate_bpm`, so the engine can see it.
- [ ] The frozen `TriageAssessment` snapshot and its append-only frozen-field guard both cover respiratory rate, so it cannot change after the fact.
- [ ] The Encounter row carries it with a `CheckConstraint` matching the validation bound.
- [ ] Intake correction (`PUT /encounters/{id}/intake`) carries the value through.
- [ ] Tachypnoea red-flag rules raise a would-be Medium/Low to High at each ESI age band: over 50 under 3 months, over 40 under 3 years, over 30 from 3 to under 8 years, over 20 at 8 years and over.
- [ ] Each rule carries a clinical citation in the established style, and names `respiratory_rate_bpm` in its `vitals` tuple so the board highlights the right field.
- [ ] The red-flag module docstring, which currently states respiratory rate is *not* assessed, is corrected.
- [ ] `docs/red-flag-safety-layer.md` lists the new rules.
- [ ] The frontend intake form sends and renders respiratory rate, including both empty-form literals in `IntakeScreen.tsx`.
- [ ] The queue board shows respiratory rate beside the other vitals.
- [ ] Tests: bounds rejected above/below, each band fires at its threshold and not one below, snapshot round-trip carries the value, and the abnormal-field attribution names the respiratory field.

## Notes

- The ESI bands are already transcribed in `evaluation/rubric.py` (`danger_zone_exceeded`, handbook Figure 5-1 p. 35). Reuse those thresholds; do not invent a second set.
- `age` is whole years, so the under-3-months band cannot be told from 3-months-to-under-3-years. Apply the same coarsening the heart-rate rules already use and say so in the docstring rather than hiding it.
- Existing test fixtures that build intake payloads will need the new field so the suite stays green; update them mechanically without loosening any assertion.

## Comments
