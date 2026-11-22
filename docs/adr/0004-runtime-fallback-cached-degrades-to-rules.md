# 0004 — Runtime fallback, cached, degrading to rules on timeout

**Status:** Superseded (2026-11-22) by [ADR 0014](0014-remove-triage-engine.md)

## Context

Symptom Group recognition matches a fixed vocabulary exactly. A complaint outside that vocabulary — unusual wording, a rare presentation, a second language — would otherwise block the patient entirely. The alternative to blocking is a runtime service call, which introduces latency, cost, and a dependency that can fail mid-intake.

## Decision

Complaints that match no Symptom Group take a runtime fallback path:

- a pluggable provider behind a seam, so the build and the test suite need no key, network, or paid service
- results cached by a SHA-256 of the exact complaint text, in the database, so identical wording always yields the identical recommendation and a cache hit survives a restart
- a configurable timeout (default two seconds); on failure, timeout, or an unconfigured provider, the level is resolved from the safety layer alone over a documented default of Medium, and the result is marked **unclassified**
- degraded results are never cached
- the safety layer is re-applied on every resolve, including cache hits, so one patient's cached complaint result can still be raised by another patient's vitals
- the unclassified flag is shown on the card, visually distinct from the override flag

## Consequences

- Unrecognised complaints always produce a recommendation, and the pathological path is visible rather than silent.
- Determinism is traded away for exactly one class of input, and bounded there: cached results repeat, but the first call's answer depends on an external service.
- The reproducibility of the reported accuracy therefore requires the fallback to be **disabled** in the primary evaluation run, with coverage reported as its own statistic. Folding fallback results into the confusion matrix would make the headline number unreproducible.
- Medium-as-default is a deliberate risk position: it is the level the warehouse can raise from, and it never claims High without evidence.
