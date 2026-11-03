# 0002 — Retain the Machine Recommendation beside the Final Decision

**Status:** Accepted (2026-11-03)

## Context

Clinical staff must be able to disagree with a Machine Recommendation. The obvious implementation is to let the Override overwrite the stored level: one field, one source of truth, nothing to keep in sync. That also destroys the only record of what the system actually predicted.

The Accuracy Evaluation Report, the False High-Priority and False Low-Priority rates, and the Override rate all compare the system's judgement against a human's. If the Override overwrites, every Override quietly improves the system's apparent accuracy, and the project's central evidence measures nothing.

## Decision

A Triage Assessment stores both values, permanently:

- `machine_recommendation` — written once when the Assessment is created, frozen by a guard that rejects any update
- `final_decision` — mutable, initially equal to the Machine Recommendation, changed only by an Override

An Override appends an `overrides` row recording the actor, the reason from the fixed list, and any free text. It never writes to the Machine Recommendation.

## Consequences

- Accuracy is measurable per Assessment, and an Override cannot launder a wrong prediction.
- Every read path has to be explicit about which value it means: the Queue orders on Final Decision, Reports on accuracy use Machine Recommendation.
- Two values can drift apart, which is the point, and the board must show that drift — the override flag is what makes the separation visible to an examiner.
- If a future change collapses the two fields, the Accuracy Evaluation Report loses its meaning. That is the test of whether this decision still holds.
