# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Clinical staff** (triage nurses / healthcare workers) — register Patients, capture intake at the bedside (often on a phone), run the Prioritization Engine, Override, Re-assess, and Depart Encounters from the Queue. **Primary user.**
- **Administrators** — read Reports and the Audit Log only; the API refuses them every clinical action.
- **The dissertation examiner** — confirmed 2026-11-18 as the first audience design must win. They read the Accuracy Evaluation Report, the Queue board, and the Audit Log as evidence for the project's claims; surfaces that pull in different directions resolve in their favour.
- **The researcher** (the project owner) — trains and evaluates the engine; works through the offline harness and the repo, not the UI.

## Product Purpose

TriageAssist is a clinical decision-support system for emergency-department triage: it recommends an Urgency Level (High / Medium / Low) from intake inputs, orders the waiting Queue by Urgency Level then arrival time, and keeps a durable record of both the machine's recommendation and any human disagreement with it. It never diagnoses or treats — "clinical decision support" is the claim, and the claim has a hard edge.

It is an academic prototype — a dissertation artefact. Success is an examiner finding the accuracy claims honest, evidenced, and traceable: the Accuracy Evaluation Report is the flagship artefact, and the override flag on the Queue board is the visible proof of the recommendation/decision separation.

## Positioning

The mechanism a neighbouring product could not truthfully copy: **both records survive**. The Machine Recommendation is immutable; the Final Decision governs the Queue; an Override records who and why from a fixed reason set; neither value ever replaces the other. Everything downstream — the confusion matrix, the False High/Low-Priority rates, the override-rate report — exists only because of that separation, and the engine is scored against an independently authored ground-truth rubric, never against itself.

## Operating Context

- Emergency-department intake under time pressure: the Clinical surface must work on a phone at the bedside; the Administrator dashboard is the dense desktop surface.
- All data is simulated or drawn from published research datasets. No real patient data exists in any environment; there is no live deployment to a care setting.
- Local development runs SQLite; the demonstration deployment runs Postgres (ADR 0001). The frontend consumes the Python HTTP API under `backend/`.
- ESI (Emergency Severity Index) is the external 5-level reference standard, used only as evaluation ground truth — it never appears in the UI. The three Urgency Levels coarsen it: High = ESI 1–2, Medium = ESI 3, Low = ESI 4–5.
- Vocabulary discipline: `CONTEXT.md` (repo root) is the source of truth for every capitalised domain term. Drift (a fourth urgency level, an "in-treatment" state, "a patient in the queue") is a scope change to raise, not a rename to absorb.
- A mobile native shell (Capacitor) wrapping the bedside Intake surface is planned for iOS and Android. It will share the same responsive codebase; no separate mobile UI. Initial release requires network connectivity (no offline sync) and covers only the Intake screen — not the full application.

## Capabilities and Constraints

- Two roles only: Clinical and Administrator (`CONTEXT.md` "Roles"). The API guards every surface's data; the path is convenience, not the security boundary.
- Intake captures: free-text complaint, pain level 1–10, illness duration, temperature, heart rate, blood pressure, oxygen saturation, respiratory rate; optional free-text notes.
- Engine composition, in order: trained supervised classifier → red-flag safety layer that can raise but never lower → cached fallback with timeout that visibly flags unclassified results. Recommendation returns within three seconds.
- Override Reasons come from a fixed set (*vitals inconsistent with recommendation, symptom not captured, clinical gestalt, patient deteriorating, duplicate entry, other*); free text only with *other*. Only Clinical may Override. **The fixed reason set from CONTEXT.md is binding in the UI — no free-text override reasons outside "other".**
- Re-assessment is explicit only — the Queue never reorders behind staff's back. Departure is manual only and records a required departure instant. Exactly two Encounter states exist: awaiting and departed. **No "in-treatment" or intermediate states exist.**
- Reports are derived on demand from stored Triage Assessments — never snapshots, never computed from live queue state. Four reports: Daily Queue, Priority Distribution, Performance, Accuracy Evaluation. **Reports compute on demand from immutable assessment rows so they cannot drift from reality.**
- The Audit Log is append-only, written in the same transaction as the change it describes.
- ESI mapping is binding: High = ESI 1–2, Medium = ESI 3, Low = ESI 4–5. This mapping never appears in the UI but governs the Accuracy Evaluation Report.
- Stack facts that constrain future work: React 19 + TypeScript + Vite + Tailwind CSS v4; UI built on BoardUI source components (`components/base`, `components/application`) under the semantic-token and components-first rules in `frontend/AGENTS.md`. Frontend verification is smoke and manual only — no frontend test harness in scope.
- Planned but not yet present: a mobile native shell (Capacitor) shipping the same codebase for bedside intake.

## Brand Commitments

- Name: **TriageAssist**. Tagline in the chrome: "Clinical decision support".
- The LogoMark (three triage bands — rose over yellow over lime) is the one place urgency colour appears in the chrome.
- Voice: precise, clinical, honest. The system states what it recognised, what it flagged, and what it does not know; copy never overclaims ("decision support", never "diagnosis").
- Terminology per `CONTEXT.md` is binding in all UI copy.
- **The incumbent visual direction is evidence, not commitment** (confirmed 2026-11-18): the IBM Plex / deep-teal accent / quiet-graphite-coded world may be preserved, expanded, or replaced by future design work. The product truth above stays fixed either way.

## Evidence on Hand

- Spec: `.scratch/triageassist/spec.md` — 63 user stories, implementation and testing decisions; the authoritative product contract.
- Domain glossary: `CONTEXT.md`. Decision records: `docs/adr/0001`–`0007`. Engine positioning against ESI and queueing theory: `docs/prioritisation-in-context.md`. Safety layer: `docs/red-flag-safety-layer.md`. Fallback: `docs/cached-fallback.md`.
- Accuracy evaluation methodology and report format: `docs/accuracy-evaluation-report.md`, with a working offline harness and versioned artefact under `backend/evaluation/`.
- A working frontend (all screens implemented on BoardUI) and backend (Python app) — the product runs end to end locally.
- Absences future work must not fabricate: no real patients, no testimonials, no deployment claims, no performance benchmarks beyond the accuracy report's own figures.

## Product Principles

1. **Both records survive.** The machine's recommendation and the human's decision are separate, durable facts; no surface may blur them.
2. **Honesty is the feature.** The system displays its own limits — unclassified flags, engine blind spots, explicit empty states — because the examiner is measuring whether the claims are true.
3. **Urgency is the only hierarchy.** The Queue reads by Urgency Level then arrival time; presentation may draw attention to long waits, but nothing in the UI re-triages, reorders, or changes a stored decision.
4. **Clinical acts are accountable acts.** An Override carries a reason and an actor; every mutation writes an Audit Entry in the same transaction.
5. **Derived, never stored.** Reports compute on demand from immutable assessment rows so they cannot drift from reality.

## Accessibility & Inclusion

- WCAG 2.1 AA is the floor; prefer AAA contrast where it is cheap to obtain (confirmed 2026-11-18).
- Urgency is never colour alone: every urgency badge carries the word, so a clinician who cannot separate the hues reads the same queue.
- The intake surface must be fully operable one-handed on a phone at a bedside.