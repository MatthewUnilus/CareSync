# Spec — TriageAssist: AI-Powered Patient Queue Prioritization

Status: **ready-for-agent**

Vocabulary throughout follows `CONTEXT.md`. Where a term is capitalised (Patient, Encounter, Triage Assessment, Urgency Level, Machine Recommendation, Final Decision, Override, Override Reason, Re-assessment, Departure, Queue, Prioritization Engine, Symptom Group, Report), it carries the meaning defined there.

---

## Problem Statement

During patient intake, healthcare staff must judge how urgently each patient needs to be seen and keep the waiting Queue ordered by that judgement. At peak volume this is done by hand, under time pressure, by staff with limited availability. The result is that urgent patients can wait behind less urgent ones, the ordering becomes inconsistent between staff and between shifts, and there is no record of *why* any particular patient was placed where they were. Administrators have no structured view of how the Queue actually performed.

Staff therefore need a tool that recommends an Urgency Level quickly and consistently, orders the Queue from that recommendation, and keeps a durable record of both the recommendation and any human disagreement with it — while never claiming to diagnose or treat the patient.

## Solution

TriageAssist is a clinical decision-support system. Staff register a Patient and open an Encounter, capture the presenting complaint as free text, a pain level, illness duration, and four vital signs. A Prioritization Engine produces a Machine Recommendation — one of three Urgency Levels (High / Medium / Low) — which places the Encounter in a Queue ordered by Urgency Level and then by arrival time. A member of the Clinical role reviews the recommendation and may Override it, recording an Override Reason; both the Machine Recommendation and the Final Decision are retained forever. Staff may Re-assess an Encounter explicitly, and Depart it from the Queue when the visit ends, recording a departure instant.

The system is presented through one responsive client codebase: a bedside intake experience and an administrator-facing reporting dashboard. Reports are read-only views derived on demand from Triage Assessment records — including an Accuracy Evaluation report that compares Machine Recommendations against ground-truth Urgency Levels, which is the project's central evidence.

The deliverable is an academic prototype (dissertation artefact) built to run locally first and be deployable as a hosted instance for demonstration. There is no real patient data; all records are simulated or drawn from published research datasets.

## User Stories

### Registration and intake

1. As a Clinical user, I want to log in securely, so that only authorised staff can access patient information.
2. As a Clinical user, I want to register a Patient with name, age, sex, and contact details, so that the visit is attributable to a person.
3. As a Clinical user, I want registering the same Patient again to reuse the existing Patient record rather than creating a duplicate, so that a returning person's history stays in one place.
4. As a Clinical user, I want opening an Encounter to record the arrival instant, so that waiting time can be measured.
5. As a Clinical user, I want to capture the presenting complaint as free text, so that I record what the patient actually said.
6. As a Clinical user, I want to record a pain level from 1 to 10, so that subjective severity is part of the assessment.
7. As a Clinical user, I want to record illness duration, so that persistence of symptoms is part of the assessment.
8. As a Clinical user, I want to record temperature, heart rate, blood pressure, and oxygen saturation, so that objective indicators are part of the assessment.
9. As a Clinical user, I want optional free-text notes on the Encounter, so that context that does not fit the structured fields is preserved.
10. As a Clinical user, I want the intake form to show which fields are required before an assessment can run, so that I do not submit incomplete data.
11. As a Clinical user, I want to correct intake values before the assessment runs, so that a typo does not skew the recommendation.
12. As a Clinical user, I want intake to work on a phone at the bedside, so that I am not tied to a desk.

### Prioritisation

13. As a Clinical user, I want the system to produce a Machine Recommendation as soon as intake is complete, so that the patient enters the Queue without delay.
14. As a Clinical user, I want the recommendation to return within three seconds, so that it does not slow intake.
15. As a Clinical user, I want the recommendation expressed as exactly one of High, Medium, or Low, so that the decision is unambiguous.
16. As a Clinical user, I want to see the free-text complaint mapped onto the Symptom Groups the engine recognised, so that I can tell when it misunderstood the text.
17. As a Clinical user, I want a documented red-flag safety layer to be able to raise the recommendation to High even when the model would not, so that obvious critical presentations are never missed.
18. As a Clinical user, I want a complaint that matches no known Symptom Group to still receive a recommendation via a fallback path, so that unusual wording does not block the patient.
19. As a Clinical user, I want the fallback path to be cached, so that the same complaint always receives the same recommendation.
20. As a Clinical user, I want the fallback to resolve to a safe default and be visibly flagged when the external service is unavailable or slow, so that I know the recommendation needs my review.
21. As a Clinical user, I want the recommendation to be stored and immutable once produced, so that it can never be quietly altered later.

### Queue management

22. As a Clinical user, I want the Queue ordered by Urgency Level and then by arrival time, so that equally urgent patients are seen in the order they arrived.
23. As a Clinical user, I want the Queue to update immediately when anything changes an Encounter's Final Decision, so that the displayed order is always current.
24. As a Clinical user, I want the board to show each awaiting Encounter as a compact card with Urgency Level, patient name, short complaint, and time waiting, so that I can scan it at a glance.
25. As a Clinical user, I want to expand a card to see the full vitals, pain level, duration, and notes, so that I can judge without leaving the board.
26. As a Clinical user, I want a visual flag on any card whose Final Decision differs from its Machine Recommendation, so that I can see at a glance where humans disagreed with the system.
27. As a Clinical user, I want time waiting to be computed from arrival time, so that I can spot patients who have waited too long.
28. As a Clinical user, I want the board to show only Encounters that are still awaiting, so that departed Encounters do not clutter the working view.
29. As an Administrator using the web dashboard, I want the same Queue shown as a dense table, so that I can survey many Encounters at once.

### Override

30. As a Clinical user, I want to Override a Machine Recommendation and set a different Urgency Level, so that my clinical judgement takes precedence when I disagree.
31. As a Clinical user, I want to pick an Override Reason from a fixed list, so that my disagreement is recorded consistently.
32. As a Clinical user, I want the ability to add free text only when I choose the "other" reason, so that unusual cases are still explainable.
33. As a Clinical user, I want the Override to record who performed it, so that the action is accountable.
34. As a Clinical user, I want the Override to take effect immediately in the Queue, so that the patient is repositioned at once.
35. As an Administrator, I want never to be able to Override, so that clinical decisions remain with clinical staff.
36. As an examiner reading the record, I want the Machine Recommendation to survive the Override untouched, so that accuracy can still be measured afterwards.

### Re-assessment

37. As a Clinical user, I want to explicitly Re-assess an Encounter already in the Queue, so that I can re-triage a patient whose condition has changed.
38. As a Clinical user, I want a Re-assessment to produce a fresh Triage Assessment with its own Machine Recommendation, so that the new decision is recorded independently.
39. As a Clinical user, I want the most recent Triage Assessment's Final Decision to govern the Encounter's position in the Queue, so that the current judgement wins.
40. As a Clinical user, I want earlier Triage Assessments to be retained, so that the history of the Encounter is complete.
41. As a Clinical user, I want re-assessment to happen only when I ask for it, so that the Queue never reorders behind my back.

### Departure

42. As a Clinical user, I want to Depart an Encounter from the Queue, so that it no longer appears as awaiting.
43. As a Clinical user, I want a departure instant recorded automatically, so that waiting time and throughput can be computed.
44. As a Clinical user, I want departure to be a manual action only, so that the system never removes a patient on its own.

### Reporting

45. As an Administrator, I want a Daily Queue Report, so that I can see the day's volume and throughput.
46. As an Administrator, I want a Priority Distribution Report, so that I can see how Urgency Levels were distributed across encounters.
47. As an Administrator, I want a Performance Report showing time waiting and processing time, so that I can judge whether flow improved.
48. As an Administrator, I want an Accuracy Evaluation Report showing a confusion matrix and per-tier precision and recall, so that the engine's correctness is evidenced.
49. As an Administrator, I want the Accuracy Evaluation Report to show False High-Priority and False Low-Priority rates separately, so that missed urgent cases are visible as their own risk.
50. As an Administrator, I want the Override rate and the distribution of Override Reasons, so that I can see where the system disagrees with staff.
51. As an Administrator, I want Reports computed on demand from stored Triage Assessments, so that they cannot drift from reality.
52. As an Administrator, I want Reports visible on the web dashboard, so that I can review them without the mobile client.
53. As an Administrator, I want no ability to perform clinical actions, so that oversight stays separate from care.

### Access and administration

54. As a system operator, I want two roles only — Clinical and Administrator — so that permissions are simple to reason about and demonstrate.
55. As a Clinical user, I want to change my password, so that I can maintain my own account.
56. As a system operator, I want passwords stored hashed, so that a database leak does not expose credentials.
57. As a system operator, I want sessions to expire, so that an unattended device does not stay logged in indefinitely.

### Evaluation and research

58. As the researcher, I want to reach the Prioritization Engine as a pure function, so that I can score it against labelled data without the database in the way.
59. As the researcher, I want to train the classifier on a published triage dataset, so that the model has citable provenance.
60. As the researcher, I want to run the accuracy evaluation with the fallback path disabled, so that the reported numbers are reproducible.
61. As the researcher, I want to report the fallback path's coverage rate separately, so that the long-tail behaviour is visible without contaminating the main score.
62. As the researcher, I want the whole system evaluable end-to-end on synthetic encounters, so that the pipeline is proven on the inputs it was designed for.
63. As the researcher, I want the ground-truth labels to come from a rubric independent of the engine's own rules, so that the accuracy claim is honest.

## Implementation Decisions

**Domain model.** Three entities in a strict hierarchy: a Patient owns many Encounters; an Encounter owns many Triage Assessments; a Triage Assessment is the unit of Urgency decision and of scoring. The Queue is a sort over Encounters, not a stored sequence, and holds only awaiting Encounters. Each of these is a term in `CONTEXT.md`; the model must not collapse them (notably, never let "a patient in the queue" become a Patient-level fact).

**Prioritisation Engine composition.** The engine is layered, in this order: (1) a trained supervised classifier over a structured feature vector; (2) a deterministic red-flag safety layer that can raise — never lower — the output; (3) a cached fallback for complaints matching no Symptom Group, with a timeout that delegates to the safety layer alone and visibly flags unclassified results. The engine exposes a single pure boundary and returns a Machine Recommendation. This boundary is Seam B and must be callable with controlled inputs and no database.

**Feature representation.** The classifier consumes a structured feature vector built from recognised Symptom Groups, pain level, illness duration, age, and the four vitals — not raw text. Symptom Group recognition (spaCy entity extraction onto the fixed vocabulary) is the NLP step. The vocabulary is authored clinically first, anchored on ESI red-flag and common presentations, then extended with the most frequent complaint tokens observed in training data. The vocabulary is a concrete list; there is no synonym table and no inference.

**Safety layer scope.** A moderate, documented set of red-flag vital thresholds and red-flag symptoms derived from ESI (order of 15–20 rules), each carrying a clinical citation. Large enough to matter to the False Low-Priority metric and to answer "what if the model misses a critical case?"; deliberately not a full ESI rule engine, so the classifier remains the contribution.

**Machine Recommendation vs. Final Decision.** Every Triage Assessment stores both, plus the Override (who, which fixed reason, optional free text) when one occurred. The Machine Recommendation is immutable. The Final Decision drives the Queue. This is required for the Accuracy Evaluation Report and the False High/Low-Priority metrics to exist at all. (ADR candidate — see Further Notes.)

**Urgency mapping.** Three Urgency Levels map to the external ESI 5-level scale: High = ESI 1–2, Medium = ESI 3, Low = ESI 4–5. ESI is used only as evaluation ground truth and never appears in the UI.

**Ground truth.** A scoring rubric derived from published ESI v4 criteria, deliberately richer than the engine's feature set, authored independently of the engine's rules so the comparison is not self-referential. Training/evaluation data: a published dataset as primary (credentialed access required — start the credentialing process immediately; it is the long pole), an open dataset as the interim development set, and a smaller published set as an independent validation set. Synthetic encounters, labelled by the rubric, form the end-to-end pipeline evaluation.

**Queue ordering and reordering.** Static Urgency per assessment; ties broken FIFO by arrival time. No automatic re-triage, no scheduled re-evaluation, no time-based escalation in this scope; re-assessment is a manual action producing a new assessment whose Final Decision governs. Verification of "the most recent assessment governs" is a first-class behaviour to test.

**Departure.** Manual only; records a departure instant that is required for every departed Encounter. Scope recognises exactly two conditions — awaiting (on the Queue) or departed (off it). No in-treatment or left-without-being-seen states.

**Reports.** Derived on demand from immutable Triage Assessment rows; never materialised snapshots, never computed from live queue state. Four reports: Daily Queue, Priority Distribution, Performance (waiting/processing time), and Accuracy Evaluation (confusion matrix, per-tier precision/recall, False High/Low-Priority rates, Override rate and reason distribution).

**Clients.** One codebase serving both targets: a React + TypeScript application, shipped as a web dashboard and, via a native shell (Capacitor), as a mobile client for bedside intake. The dashboard is the dense-tabular surface; the mobile client is the intake surface. Both consume the same backend API. Queue board presentation: compact cards with urgency colour, patient name, short complaint, time waiting, and an override flag, expandable to full vitals and actions; the dashboard additionally offers a dense table view over the same data.

**Backend and data.** Python service exposing the HTTP API, backed by Postgres. Authentication by server-side sessions with hashed passwords (argon2/bcrypt) and session expiry; authorisation by the two roles Clinical and Administrator. Local development via containers so the stack is reproducible; a hosted instance for demonstration. No exotic infrastructure (no message bus, no worker fleet) in this scope.

**Two seams, highest first.** Seam A is the backend HTTP API — the primary behavioural seam, exercised against a real Postgres. Seam B is the Prioritization Engine pure function — the scoring seam, exercised without a database. No third seam; the frontend is verified by smoke and manual testing in this scope.

**Schema changes (shape, not paths).** New tables conceptually covering: patients; encounters (with arrival instant, departure instant nullable, status); triage assessments (inputs snapshot, machine recommendation, final decision, supersession link to prior assessment); overrides (assessment link, actor, reason enum, free text); users (role, password hash); sessions; and a cache table for fallback results keyed by complaint hash. Assessment rows are append-only. Encounters carry a status whose only in-scope values are awaiting and departed.

## Testing Decisions

**What a good test is here.** Tests assert external behaviour — the Queue's resulting order, the recommendation returned for given inputs, the presence and values of records after an action — never internal structure, private helpers, or the fact that a rule "is implemented in function X". A test should survive a refactor of the engine's internals unchanged. Because the engine is deterministic, tests can assert exact Urgency Levels for constructed inputs; because behaviour is a sort and a set of durable records, tests assert orderings and stored values, not log lines.

**Seam A — backend HTTP API (primary).** Whole flows are driven against a real Postgres: registration through to Departure. Specific behaviours to cover, each as flow-level tests: an Encounter enters the Queue with a Machine Recommendation; Queue ordering is by Urgency Level with FIFO within a level; an Override reorders immediately and both recommendation values persist; an Override without a reason is rejected; an Administrator is refused a clinical action and vice versa; a Re-assessment creates a new assessment and the latest Final Decision governs the Queue; Departure removes the Encounter from the board and records the instant; Reports reflect only stored assessments. Prior art: none yet in this repo (greenfield); these establish the pattern of flow tests at the API boundary for the codebase.

**Seam B — Prioritization Engine (pure).** The engine is called directly with constructed inputs. Cover: each Urgency Level mapping; the safety layer raising a would-be Medium/Low to High for a red flag; the safety layer never lowering; unseen complaints routing to the cached fallback; identical complaint text returning an identical cached result; timeout defaulting and the unclassified flag. This seam also hosts the accuracy harness producing the confusion matrix and per-tier metrics from labelled data, which is the evidence the dissertation rests on.

**Evaluation methodology tests.** Cross-validated scores on the primary dataset (model learns), plus a full-pipeline evaluation on rubric-labelled synthetic encounters (the system behaves), reported separately. The accuracy evaluation runs with the fallback disabled for reproducibility; fallback coverage rate is reported as its own statistic.

**Frontend.** Smoke and manual testing only in this scope: intake on a mobile viewport, board reorder visible, override flow, dashboard reports render. No frontend test harness is built.

## Out of Scope

- Medical diagnosis, treatment recommendations, prescription generation, and medical image analysis.
- Integration with hospital EHR systems, ambulance dispatch, appointment management, and SMS notifications.
- Real patient data in any environment; live deployment to a real care setting.
- Automatic re-triage, scheduled re-evaluation, and time-in-queue escalation.
- Learned models trained on real hospital data; multi-language symptom analysis; predictive flow analytics.
- Availability, backup/recovery, and encryption-at-rest guarantees are documented as operational requirements, not claimed as tested behaviours (a local prototype cannot honestly demonstrate them).
- A frontend automated test harness.
- Any third seam beyond the API and the engine.

## Further Notes

- **ADRs to write when the engine is built** (each clears the bar of hard-to-reverse, surprising-without-context, and a real trade-off): (1) retaining both Machine Recommendation and Final Decision rather than overwriting; (2) the classifier-plus-cited-safety-layer as the "AI", rather than pure rules or a pure LLM; (3) the runtime LLM fallback with caching and rules-on-timeout, recording the determinism/reproducibility trade-off. Not written yet — no code exists to reference.
- **Immediate non-code action for the project owner:** begin the credentialed-dataset access process (training + agreement) immediately; it has a days-to-weeks lead time and gates the primary evaluation. Until granted, develop against the open dataset.
- **The Accuracy Evaluation report is the flagship artefact.** It is the screen that demonstrates the project's contribution and should be the most carefully designed reporting view.
- **The override flag on the queue board is load-bearing.** It is the visible proof of the Machine-Recommendation/Final-Decision separation, and its presence is what makes the accuracy metrics credible to an examiner.
- **Terminology discipline.** `CONTEXT.md` is the source of truth for vocabulary. If implementation drifts (e.g. inventing a fourth Urgency Level, or a left-without-being-seen state), that is a scope change and must be raised, not absorbed.
