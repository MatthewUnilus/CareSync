# 0003 — Compose a trained classifier with a cited deterministic safety layer

**Status:** Superseded (2026-11-22) by [ADR 0014](0014-remove-triage-engine.md)

## Context

The system must recommend one of three Urgency Levels and must not miss a critical presentation. Three compositions were available:

1. **Pure rules.** Auditable and deterministic, but then the project's contribution is a small ESI rule engine, and "AI-powered" is a misnomer.
2. **A pure LLM.** Flexible on free text, but non-deterministic, unexplainable at the level a clinician needs, and unable to guarantee that a red flag raises the level.
3. **A trained classifier plus a deterministic safety layer.**

## Decision

Option 3. The Prioritization Engine is layered, in this order:

1. a supervised classifier over a structured feature vector (recognised Symptom Groups, pain level, illness duration, age, five vitals)
2. a deterministic red-flag layer of cited rules (twenty when written; twenty-three since respiratory rate was captured in ticket 17), which can raise the output to High and can never lower it
3. a cached fallback for complaints matching no Symptom Group (ADR 0004)

The whole composition sits behind one pure function, callable with constructed inputs and no database.

The safety layer is deliberately moderate: on the order of twenty rules, each carrying a citation traceable to ESI v4. It is not a full ESI rule engine, because then the classifier would stop being the contribution.

## Consequences

- A critical presentation can be rescued even when the model misses it, and the rescue is traceable to a named, cited rule.
- The layer over-triages by design: any adult heart rate above 100, any recognised chest pain, and adult systolic pressure below 90 all raise to High. Sensitivity was preferred to specificity for a safety net.
- Two failure modes must be reasoned about separately: a model that predicts badly, and a layer that fails to cover a presentation it should. The layer cannot rescue pain-only presentations, adult fever without a crossed vital threshold, or negated text ("no chest pain" still recognises *chest pain*).
- The composed result is what is stored, so the Accuracy Evaluation Report measures the system as shipped. Isolating the model's own contribution requires computing classifier-only separately, which the harness does.
