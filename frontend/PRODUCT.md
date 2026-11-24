# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Ward nurses** (Clinical staff) — register Patients, admit and discharge them, chart Observations, write Nursing Notes, record Medication Orders and Medication Administrations, track Investigations, manage Tasks, and print the handover. They work at a desktop on the ward and, more often, on a shared tablet at the bedside. **Primary user.**
- **Laboratory staff** — acknowledge Investigation requests sent by the ward and publish free-text results.
- **Administrators** — read-only oversight: the operations dashboard and the Audit Log. The API refuses them every clinical action; the role exists so oversight stays separate from care.
- **The dissertation examiner** — confirmed 2026-11-18 as the first audience design must win. Requirements traceability and honest evidence matter more to them than feature count; they read the spec against what runs, and surfaces that pull in different directions resolve in their favour.
- **The researcher** (the project owner) — runs the usability study with ward nurses and reads the time-on-task figures. Works through the study materials and the repo, not the ward surface.

## Product Purpose

CareSync is a nursing workflow management system for a hospital ward. It answers the three problems a ward nurse names — documentation, access to information away from the ward, and tracking outstanding work across several patients — by keeping one clinical record and deriving the worklists from it. A Patient is registered and, when they are an inpatient, admitted to a ward; staff chart Observations, write Nursing Notes from Note Templates, record the doctor's Medication Orders and the administrations that follow, track Investigations to a reviewed result, and carry Tasks from a ward round or raised by hand. A Ward Board shows the open Admissions ordered by outstanding work.

It is an academic prototype built for a private hospital and deployable on their network. It never diagnoses, recommends treatment, calculates a dose, checks an interaction or allergy, interprets a result, or decides who is treated first. Success is an examiner finding the requirements fit honest and traceable, and a usability study that speaks to the ward problems that prompted the build.

## Positioning

The line is drawn where it can be defended, and the mechanism a neighbouring product could not truthfully copy is that **the system records and derives, and never decides**. Every clinical fact is something a nurse entered or a doctor instructed: a Medication Order is a transcription, an administration is an attestation, a result note is what the laboratory said. Nothing the system shows is a judgement of its own — an Observation outside its reference range is marked for display and nothing more, and the Ward Board orders by a count of outstanding work tallied from the record, not a score. That count and every figure are recalculated on read and stored nowhere, so a displayed number can never drift from the rows behind it. A scoring or triage product makes a different claim and could not copy this one; the value here is that everything on screen traces back to a recorded act or an instruction, in a log written in the same transaction as the act itself.

## Operating Context

- A ward nurse's day starts before 08:00 with patient reviews — medical histories, vital signs, care plans, treatment plans, laboratory results. Ward rounds follow, where a doctor's instructions are given verbally and must be acted on; the rest of the day is monitoring, administering prescribed medications, chasing investigation results, completing tasks and preparing a handover.
- The setting is a real private hospital ward. The prototype is built for that hospital and is deployable on their network; there is no live deployment to a care setting and no real patient data in any environment. All data is simulated.
- The ward surface is used at a desktop and, primarily, on a shared tablet at the bedside; the Administrator dashboard is the dense desktop surface. The same client serves both roles from one responsive codebase.
- CareSync runs alongside the paper nursing record, which continues to run the ward. Printed sheets are worklists that verify against the system, not the legal record (ADR 0009).
- Local development runs SQLite; the demonstration deployment runs Postgres (ADR 0001). The frontend consumes the Python HTTP API under `backend/`.
- A native Capacitor shell wraps the same Vite build for iOS and Android. It is shipped, it shares the responsive codebase with no forked screen or separate mobile UI, and it requires network connectivity — there is no offline mode.
- A usability study with ward nurses is the evidence path: set tasks, SUS, and time on task instrumented by the system. It needs the hospital's agreement and probably the university's ethics review, both of which have lead time.
- Vocabulary discipline: `CONTEXT.md` (repo root) is the source of truth for every capitalised domain term. Drift — a new state, a clinical score, an "in-treatment" flag — is a scope change to raise, not a rename to absorb.

## Capabilities and Constraints

- Three roles: Clinical, Laboratory and Administrator (`CONTEXT.md` "Roles"). The API guards every surface's data; the route a client takes is convenience, not the security boundary.
- A Patient carries an optional **hospital number**, captured at registration and indexed. Identity is decided in order: equal numbers are the same Patient, different numbers are different Patients, and only with neither number present does the older rule apply — the normalised name together with the normalised contact phone. A family phone number never merges two people who each have a hospital number.
- **Admission** is separate from **Encounter**: an Encounter is a visit with a reason and an end; an Admission is an inpatient stay on a ward with a bed or location, linked to the Encounter it came from when the patient was seen first (ADR 0008). A discharge closes the Admission, removes it from the Ward Board, and keeps its history.
- **Observations** hold every set of vital signs: one row per set, against an Encounter or an Admission, never both and never neither. They are the Patient's single time series — one place holds the current picture. Each reading is stamped with its time and attributed to the nurse who took it, and a set is unchangeable once saved. A reading outside its published adult reference range is marked for display only; the system never alters a value, reorders anything on the strength of one, or raises an alert (ADR 0010). There is no early-warning score and no escalation.
- **Nursing Notes** are written from fixed **Note Templates** — shift assessment, ward round entry, intervention record, handover entry, discharge summary — so a note starts from a shape rather than a blank page. Templates are a code vocabulary served by `GET /api/ward/note-templates`, one row per field, so a template change needs no schema change and no client change (ADR 0013). Notes are stamped with time and author; a correction is a new note that says it corrects the first, and the original is never edited.
- **Medication Orders** transcribe an instruction a doctor already gave. Drug, dose, route, frequency and start time are frozen when the order is written, so a change is a stop and a new order and the change stays visible (ADR 0011). The system does not calculate a dose, check a dose against a maximum, or check interactions or allergies.
- **Medication Round Times** are a documented convention, not advice: a frequency maps to fixed clock times in one module, shown to the user so nobody mistakes it for clinical judgement. **Medication Administrations** are append-only, one row per order and due time, so a slot cannot be recorded twice. A dose is given, withheld, refused or unavailable; a reason is required when it was not given. It records what a nurse attests to — there is no barcode or wristband verification. An overdue dose is marked and nothing else happens; no order changes.
- The **due list is derived, never stored**: what is due is computed at read time from the open orders and the round times, so it cannot drift from the orders.
- **Investigations** track progress through four states — requested, sample taken, result available, reviewed — with a free-text result note recorded as the laboratory gave it. Marking a result reviewed is the accountable act and records who and when. The system never reads a value, never flags an abnormal result, and never suggests anything from one (ADR 0012).
- **Tasks** carry an optional due time and an optional assignee, so both an assigned caseload and a shared ward work. A Task may be raised by hand or from a ward round entry; a Task raised from a round entry belongs to that patient. Tasks past their due time are shown as overdue. There is no automatic reassignment.
- The **Ward Board** orders open Admissions by outstanding work counted from the record: overdue medication doses, then doses due now, then results awaiting review, then open Tasks, with bed order breaking ties. It is recalculated on every read and stores nothing. It is not a score, not a clinical judgement, and it does not decide who is treated first.
- **Printing is a worklist, not the record.** Sheets carry a generation time and the line "verify against the system".
- The operations dashboard (Administrator) shows read-only **Reports**: ward census and length of stay, the proportion of doses recorded on time, the count of results still awaiting review, and Tasks completed against Tasks raised. Every figure is derived at read time from stored rows and never stored, so it cannot drift.
- The **Audit Log** is append-only, written in the same transaction as the change it describes, and names the actor, the action, the Patient, Encounter or Admission touched, and the time. The action's human label is served from one source of truth beside the enum, not hard-coded in the client. Admission, discharge, location move, note, order, administration, investigation and task mutations each append one entry.
- **No scoring of any kind survives.** The Prioritization Engine, Urgency Levels, the Queue, Override, Re-assessment, Departure, Symptom Groups and the Accuracy Evaluation Report are removed (ADR 0014). Seam B — the engine's pure-function boundary — is empty; the evaluation surface is the usability study rather than a scoring harness.
- Stack facts that constrain future work: React 19 + TypeScript + Vite + Tailwind CSS v4; the UI is built from source components under the components-first rules in `frontend/AGENTS.md`. The native shell is Capacitor. Frontend verification is smoke and manual only — there is no frontend automated test harness in scope.
- Deliberately out of scope, each with an ADR behind it: diagnosis, treatment recommendations, prescription generation, dose calculation, interaction or allergy checking, and medical image analysis; integration with hospital laboratory or electronic-health-record systems; barcode or wristband verification; reading or interpreting a result value; beds as managed entities, transfers between wards as a workflow, rosters, shifts and off-duty planning; doctors logging in (nurses record the doctor's instructions); real-time messaging, paging, push notification, SMS or email alerts; offline operation; auto-saving or any scheduled action — the system never acts on a timer; encryption at rest, backup and recovery as tested behaviours; availability, retention and tamper-evident hashing for the Audit Log.

## Brand Commitments

- Name: **CareSync**. Tagline in the chrome: "Nursing workflow management".
- Voice: precise, clinical, honest. The system states what it recorded, what was instructed, and what it does not know; copy never overclaims. It transcribes and attests — never "recommends", never "diagnoses", never "calculates".
- Terminology per `CONTEXT.md` is binding in all UI copy.
- **The incumbent visual direction is evidence, not commitment** (confirmed 2026-11-18): the IBM Plex / deep-teal accent / quiet-graphite-coded world may be preserved, expanded, or replaced by future design work. The product truth above stays fixed either way.

## Evidence on Hand

- Spec: `.scratch/caresync/spec.md` — 59 user stories (64–122), implementation and testing decisions; the authoritative product contract, superseding the triage scope.
- Domain glossary: `CONTEXT.md`. Decision records: `docs/adr/0001`–`0014`. ADRs 0002–0006 are **Superseded** by 0014; 0008–0014 record the ward work; 0001 (data layer) and 0007 (audit log) are kept and amended. The removed subsystem documents (`prioritisation-in-context.md`, `red-flag-safety-layer.md`, `cached-fallback.md`, `accuracy-evaluation-report.md`) sit in `docs/archive/` behind a header saying they describe a system that no longer ships.
- A working frontend and backend: authentication and the shared-device session lock, the three Roles, Patient registration and matching, the visit record, Admissions and the Ward Board, the Observation chart, Nursing Notes, Medication Orders and administrations, Investigations, the Laboratory dashboard, Tasks, printable sheets, the operations dashboard, the Audit Log and the study instrumentation all run end to end locally and in the native shell. The ward capabilities above are shipped; future work must not describe them as remaining scope.
- The native Capacitor shell (iOS and Android) already ships the same client; it is no longer a plan.
- Absences future work must not fabricate: no real patient data, no testimonials, no deployment claims, no dose or interaction or allergy checking, no interpretation of a result value, and no performance benchmarks.

## Product Principles

1. **Record, never decide.** The system transcribes and attests; it never diagnoses, doses, interprets or ranks clinically. The line is the product.
2. **The count is honest.** The Ward Board and every figure order by outstanding work counted from the record, not a score, and store nothing.
3. **Nothing shown can drift.** The due list, the board and the Reports are derived on demand from stored rows, never a snapshot, never cached.
4. **The paper record still runs the ward.** CareSync runs alongside it; printable sheets are worklists that verify against the system, not the legal record.
5. **Clinical acts are accountable acts.** Every clinical mutation appends an Audit Entry in the same transaction, naming who, what and when.

## Accessibility & Inclusion

- WCAG 2.1 AA is the floor; prefer AAA contrast where it is cheap to obtain (confirmed 2026-11-18).
- An abnormal reading is never colour alone: every out-of-range mark carries a word, so a clinician who cannot separate the hues reads the same chart.
- The ward surface must be fully operable one-handed on a shared tablet at the bedside.
