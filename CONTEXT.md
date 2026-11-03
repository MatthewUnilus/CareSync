# Context — TriageAssist

Glossary only. No implementation details, no schemas, no technology choices.

## Terms

### Patient
A person. Persists indefinitely, independent of any visit. Is *not* the thing that sits in a queue.

### Encounter
A single visit by one Patient to a facility. Has a start and an end. A Patient may have many Encounters over time. The queue holds Encounters, not Patients.

### Triage Assessment
One urgency decision, produced at a point in time from the symptoms and vital signs captured during an Encounter. An Encounter may have more than one Assessment (e.g. re-triage). Accuracy is measured per Assessment.

### Urgency
The clinical property being assessed — how soon a Patient needs to be seen. Distinct from Priority (see below) and from Acuity, which we do not use as a term.

### Urgency Level
The output category of a Triage Assessment. Exactly one of three values:

- **High** — maps to ESI 1–2
- **Medium** — maps to ESI 3
- **Low** — maps to ESI 4–5

ESI (Emergency Severity Index) is the external 5-level reference standard. Our three levels are a coarsening of it; ESI is used only as ground truth for evaluation, never shown in the UI.

### Machine Recommendation
The Urgency Level produced by the prioritization engine for a Triage Assessment. Immutable once produced. Drives evaluation only — never mutated into, and never overwritten by, the Final Decision.

### Final Decision
The Urgency Level that actually governs where the Encounter sits in the queue. Equal to the Machine Recommendation unless an Override occurred. Authoritative and separate from it.

### Override
A human act of setting the Final Decision to a different Urgency Level than the Machine Recommendation. Records who performed it and why. Both values survive; neither replaces the other.

### Override Reason
The stated justification for an Override. Drawn from a fixed set — *vitals inconsistent with recommendation, symptom not captured, clinical gestalt, patient deteriorating, duplicate entry, other* — with free text permitted only when the reason is *other*. A reportable dimension, not mere commentary. Only a member of the Clinical role may perform an Override.

### Re-assessment
An additional Triage Assessment created when staff explicitly request one for an Encounter already in the queue. Never created automatically in the current scope. The most recent Assessment's Final Decision is the one that governs the Encounter's place in the queue; earlier Assessments are retained and remain part of the record.

### Departure
The act of discharging an Encounter from the queue. Performed manually by staff; the system never removes an Encounter on its own. A Departure records a departure instant, which is required for every departed Encounter — without it there is no waiting-time or throughput figure. There is no *left-without-being-seen* or *in-treatment* state in the current scope: an Encounter is either awaiting (on the queue) or departed (off it).

### Queue
An ordering of Encounters by Urgency Level, with ties broken by arrival time (first-in-first-out). A sort, not a sequence — entries are not consumed in the usual queue sense.

### Prioritization Engine
The component that produces a Machine Recommendation from a Triage Assessment's captured inputs. Referred to as "clinical decision support", not as providing diagnosis or treatment.

### Symptom Group
A canonical clinical concept (e.g. *chest pain*, *shortness of breath*, *fever*) that a free-text complaint is mapped onto. The classifier consumes Symptom Groups, not raw text. The vocabulary was authored clinically first — anchored on ESI red-flag and common presentations — and then extended with the most frequent complaint tokens observed in the training data. It is a concrete list, not a rule engine (no synonym table, no inference).

### Roles
Two roles, and only two:

- **Clinical** — register Patients, capture intake, perform Re-assessments, and perform Overrides. Matches the PRD's *Healthcare Workers* and *Triage Nurses* merged.
- **Administrator** — view Reports only; no clinical actions.

### Report
A read-only view derived on demand from Triage Assessment records — never a stored snapshot, never computed from mutable queue state.

