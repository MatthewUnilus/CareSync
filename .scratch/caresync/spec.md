# Spec — CareSync: Nursing Workflow Management

Status: **ready-for-agent**

Vocabulary throughout follows `CONTEXT.md`. Where a term is capitalised (Patient, Encounter, Admission, Discharge, Observation, Nursing Note, Note Template, Medication Order, Medication Administration, Medication Round Time, Investigation, Task, Ward Board, Report, Audit Entry), it carries the meaning defined there.

This spec supersedes the triage scope. The Prioritization Engine, the Queue, Override, Re-assessment, Departure, Symptom Groups and the Accuracy Evaluation Report are removed by tickets 25 and 26.

---

## Problem Statement

A nurse's day on a private hospital ward starts before 08:00 with patient reviews: medical histories, vital signs, care plans, treatment plans and laboratory results. Ward rounds follow, where a doctor's instructions are given verbally and must be acted on. The rest of the day is monitoring, administering prescribed medications, chasing investigation results, completing nursing tasks and preparing a handover.

Three problems come out of that day, in the nurse's words:

1. **Documentation.** Writing nursing notes, updating patient charts and recording nursing interventions is time-consuming. An organised template would help.
2. **Access to information.** Attending to a patient in another department means walking back to the ward to check that patient's latest vital signs, medication records or treatment plan.
3. **Task management.** Tracking outstanding investigations, laboratory results, medication schedules and treatment instructions is difficult when caring for several patients at once.

The existing system does not address any of them. It was built to score how urgently a patient needs to be seen and to order a waiting queue.

## Solution

CareSync is a nursing workflow management system. A Patient is registered and, when they are an inpatient, given an Admission to a ward. Staff chart Observations, write Nursing Notes from Note Templates, record the doctor's Medication Orders and the administrations that follow, track Investigations to their result and review, and carry Tasks raised from a ward round or by hand. A Ward Board shows the open Admissions ordered by outstanding work, so the nurse can see at a glance who needs what next. Sheets print for the handover and the medication round, which the paper record continues to run alongside.

The system is presented through one responsive client codebase: a ward surface for clinical staff, usable at a desktop and on a shared tablet, and a read-only operations dashboard for administrators. The deliverable is an academic prototype built for a real private hospital, deployable on their network.

### What this system does not do

These boundaries are deliberate and each has an ADR behind it. They exist because a nursing workflow system sits next to clinical decision-making, and the line has to be drawn where it can be defended.

- It does not diagnose, recommend treatment, calculate doses, or check drug interactions or allergies. A Medication Order is the transcription of an instruction a doctor already gave.
- It does not interpret an Investigation result. It tracks that a result arrived and that somebody reviewed it.
- It does not decide who to treat first. The Ward Board orders by outstanding work, counted from the record, not scored.
- It does not verify by barcode. An administration records what a nurse attests to.
- It does not replace the paper nursing record. It runs alongside it, and the printed sheets are worklists.

## Users

- **Clinical staff (ward nurses).** The primary user. Admits patients, charts Observations, writes Nursing Notes, records Medication Orders and administrations, tracks Investigations, manages Tasks, hands over.
- **Administrator.** Read-only oversight: the operations dashboard and the Audit Log. No clinical actions.
- **The dissertation examiner.** The first audience design decisions must satisfy. Requirements traceability and honest evidence matter more than feature count.
- **The researcher.** Runs the usability study and reads the time-on-task figures.

## User Stories

### Identity and admission

64. As a Clinical user, I want to capture a hospital number when I register a Patient, so that two patients with the same name are never confused.
65. As a Clinical user, I want a patient who shares a name and a phone with another to stay separate once both have hospital numbers, so that a family phone number does not merge two people.
66. As a Clinical user, I want to admit a Patient to a ward with a bed or location, so that the stay is recorded against them.
67. As a Clinical user, I want to link an Admission to the Encounter it came from when the patient was seen first, so that the visit and the stay are one history.
68. As a Clinical user, I want to discharge a Patient at the end of the stay, so that the Admission is closed and the ward census is right.
69. As a Clinical user, I want a patient's location move to be recorded, so that the board always shows where they are.

### Observation charting

70. As a Clinical user, I want to chart a set of vital signs against a patient's Admission, so that the ward has a current picture rather than a single admission value.
71. As a Clinical user, I want the chart to show the previous reading beside the current one, so that I can see the direction of travel without reading back.
72. As a Clinical user, I want each reading stamped with the time it was taken and attributed to me, so that the record is accountable.
73. As a Clinical user, I want a reading outside its normal range marked as such, so that an abnormal value is visible on the chart.
74. As a Clinical user, I want an abnormal mark to be display only, so that the system never changes what I recorded.
75. As a Clinical user, I want a charted Observation to be unchangeable once saved, so that the record cannot be quietly rewritten.

### Nursing documentation

76. As a Clinical user, I want to write a Nursing Note from a Note Template, so that I do not start from a blank page.
77. As a Clinical user, I want templates for a shift assessment, a ward round entry, an intervention record, a handover entry and a discharge summary, so that the common cases are covered.
78. As a Clinical user, I want a new note to prefill from the patient's latest Observation, so that I am not retyping numbers the system already has.
79. As a Clinical user, I want my notes stamped with the time and my name, so that each entry is attributable.
80. As a Clinical user, I want to correct a note by adding a new one that says it corrects the first, so that the original stays in the record.
81. As a Clinical user, I want to see a patient's notes in time order, so that I can read the shift back.
82. As the system operator, I want template fields defined in one place on the server, so that a change to a template needs no database change and no client change.

### Ward rounds and tasks

83. As a Clinical user, I want to record the instructions from a ward round, so that they are not lost between the round and the shift.
84. As a Clinical user, I want a ward round entry to raise Tasks against the patient, so that an instruction becomes something I can work.
85. As a Clinical user, I want to raise a Task by hand, so that a request that did not come from a round is still trackable.
86. As a Clinical user, I want each Task to have an optional due time, so that work with a deadline is distinguishable from work without one.
87. As a Clinical user, I want to assign a Task or leave it unassigned, so that both an assigned caseload and a shared ward work.
88. As a Clinical user, I want a list of my Tasks across all my patients, so that I can work from one list without visiting each patient.
89. As a Clinical user, I want to mark a Task done, so that the list shows what is left.
90. As a Clinical user, I want to see which Tasks are overdue, so that nothing quietly slips.

### Medications

91. As a Clinical user, I want to record the doctor's medication instruction as a Medication Order, so that it appears once and is not rewritten each round.
92. As a Clinical user, I want an order to carry drug, dose, route, frequency and who instructed it, so that the record is complete.
93. As a Clinical user, I want to change a dose by stopping the order and recording a new one, so that the change is visible in the record.
94. As a Clinical user, I want a list of doses due across the ward, so that I can work a medication round from one place.
95. As a Clinical user, I want the due list derived from the orders and the round times, so that it cannot drift from the orders.
96. As a Clinical user, I want to record a dose as given, withheld, refused or unavailable, so that not giving a dose is as recordable as giving it.
97. As a Clinical user, I want to record a reason when a dose is not given, so that the omission is explained.
98. As a Clinical user, I want a dose slot to be recordable only once, so that a double entry cannot inflate the record.
99. As a Clinical user, I want an overdue dose marked as overdue and nothing else to happen, so that the system never changes an order on its own.
100. As a Clinical user, I want the round times a frequency maps to to be documented, so that I know the convention being applied.

### Investigations

101. As a Clinical user, I want to record an Investigation a doctor requested, so that it is not lost.
102. As a Clinical user, I want its progress to have four states, so that I can tell a test not yet taken from one whose result is waiting for me.
103. As a Clinical user, I want to record a free-text result note, so that what the laboratory said is preserved.
104. As a Clinical user, I want to mark a result reviewed and have that attributed to me, so that the review is accountable.
105. As a Clinical user, I want a list of results awaiting review across the ward, so that nothing goes unread.
106. As a Clinical user, I want a list of tests still awaiting a result, so that I know what to chase.

### Handover and print

107. As a Clinical user, I want a handover sheet of my patients, so that the next shift has the picture without me reciting it.
108. As a Clinical user, I want a medication round sheet, so that I can work the round on paper if that is faster.
109. As a Clinical user, I want a ward worklist of outstanding tasks and investigations, so that the shift end is not the first time I notice what is left.
110. As a Clinical user, I want every printed sheet stamped with its generation time, so that a stale sheet is recognisable as stale.

### Access and safety on a shared device

111. As a Clinical user, I want my session to lock after a period of no activity on a shared tablet, so that the next person to pick it up does not see my patients.
112. As a Clinical user, I want an explicit lock and switch-user action, so that I can hand the tablet over deliberately.
113. As the system operator, I want session cookies marked secure when served over HTTPS, so that a session token is not sent in clear text.

### Oversight

114. As an Administrator, I want the ward census and length of stay, so that I can see how the ward is running.
115. As an Administrator, I want the proportion of doses recorded on time, so that the medication round is visible as a figure.
116. As an Administrator, I want the count of results still awaiting review, so that documentation lag is visible.
117. As an Administrator, I want tasks completed against tasks raised, so that the ward's workload is visible.
118. As an Administrator, I want the Audit Log of every clinical action, so that the record is accountable.
119. As an Administrator, I want never to be able to perform a clinical action, so that oversight stays separate from care.

### Evaluation

120. As the researcher, I want to measure time on task for a set of study tasks, so that the system can be compared against the paper process.
121. As the researcher, I want the study instrumentation to be switchable off, so that it never runs in normal ward use.
122. As the researcher, I want the system evaluated with ward nurses on the tasks they actually do, so that the evidence speaks to the problems that prompted the build.

## Implementation Decisions

**Domain model.** A Patient owns many Encounters and many Admissions. An Encounter is a visit; an Admission is an inpatient stay on a ward. An Observation records one set of vital signs and attaches to either an Encounter or an Admission, never both and never neither. A Nursing Note belongs to an Admission. A Medication Order belongs to an Admission; its Medication Administrations belong to the order. An Investigation and a Task belong to an Admission. This is ADR 0008.

**Why Admission is separate from Encounter.** An Encounter is a visit with a reason and an end. An Admission is a period of inpatient care with a location. Collapsing them would force every outpatient visit to carry a ward and a bed, and would make "how long has this patient been an inpatient" unanswerable without a second concept.

**Patient identity.** A hospital number is captured at registration, optional and indexed. Matching order: equal numbers mean the same Patient; different numbers mean different Patients; with neither number present, the existing rule applies, being the normalised name together with the normalised contact phone. This supersedes the identity rule that `proposal-gaps` deliberately froze, because a ward with several patients sharing a surname is the case that rule fails.

**Vital signs live in one place.** The Encounter loses the vital-sign columns it was written to hold. Every set of vitals is an Observation. This makes the Observation chart the single time series for a patient, and removes the question of which of two places holds the truth. It is a rewrite of the intake tests, taken deliberately in ADR 0008.

**Observation reading ranges.** The normal range for a reading is the published adult reference range, and it is the same set of thresholds the deleted red-flag layer already cited. They are used for display marking only. There is no scoring, no early-warning aggregate score, and no escalation. This is ADR 0010.

**Abnormal marking is display only.** The system never alters a recorded value, never reorders anything on the strength of one, and never raises an alert. A user sees that a value is outside its range and decides. This restates ADR 0006's rule in a system with no scoring engine to protect, and is the reason the rule outlives the engine.

**Note templates are code, served by the API.** Template definitions live in a module as a fixed vocabulary and are served by `GET /api/ward/note-templates`. Each field becomes one row per note. Adding or changing a template field is a code change, needing no schema change and no client change, which matters because there is no migration tool and the hospital's real forms will change the templates. Field values are free text: there is no controlled clinical terminology in scope. This is ADR 0013.

**Medication Orders are transcribed instructions.** An order is not a prescription. The system does not calculate a dose, does not check a dose against a maximum, and does not check interactions or allergies, because it holds no allergy or interaction data and because generating a prescription is outside the project. Drug, dose, route, frequency and start time are frozen when the order is written: a change is a stop and a new order, so the change is visible. This is ADR 0011.

**Medication Round Time is a documented convention, not a recommendation.** A frequency maps to fixed clock times in one module. The mapping is shown to the user and stated in the interface, so nobody mistakes it for clinical advice. An overdue dose is marked; nothing is escalated and no order changes.

**The due list is derived, never stored.** What is due is computed at read time from the open orders and the round times. Storing it would let it drift from the orders, the same failure the reports discipline already guards against.

**Administrations are append-only and unique per slot.** One row per order and due time, so a slot cannot be recorded twice. Append-only is enforced in the application layer by the same `before_update` guard pattern the deleted assessment and the Audit Entry use, because ADR 0001 forbids database triggers.

**Investigations track progress, never interpretation.** Four states: requested, sample taken, result available, reviewed. The result note is free text, recorded as the laboratory gave it. Marking reviewed is the accountable act and records who and when. The system never reads a value, never flags an abnormal result, and never suggests anything from it. This is ADR 0012.

**Tasks carry an optional assignee.** Assignment is optional so both an assigned caseload and a shared ward work. A Task may be raised by hand or from a ward round entry. There is no automatic reassignment.

**The Ward Board orders by outstanding work.** Overdue medication doses, then doses due now, then results awaiting review, then open Tasks, with bed order breaking ties. This is a count of what the record shows is outstanding, recalculated on every read. It is not a score, not a clinical judgement, and not stored.

**Printing is a worklist, not the record.** Sheets carry a generation time and the line "verify against the system". Nothing printed is a legal record, which is the hospital's paper chart's job, and this is ADR 0009.

**The audit log covers every clinical mutation.** The action set grows to cover ward actions, and admission, discharge, location move, note, order, administration, investigation and task mutations each append one entry in the same transaction as the change. The action's human label is served from one source of truth beside the enum, not hard-coded in the client, because the set is now large enough that a client-side copy would drift. ADR 0007 is kept and amended.

**Two roles and two seams, unchanged.** Clinical and Administrator remain the only roles. Seam A remains the HTTP API. Seam B was the Prioritization Engine's pure function and is now empty: with no engine there is no second seam, so the evaluation surface becomes the usability study rather than a scoring harness.

**No third seam, and no frontend test harness.** This was the triage scope's decision and it is retained, but the risk is higher now. A screen that fails during a study session wastes that session and a participant's time, so a smoke check per screen is worth arguing for separately.

## Testing Decisions

**What a good test is here.** Tests assert external behaviour: the Ward Board's resulting order, what is due for a patient at a given time, which rows exist after an action, and what is refused. They never assert internal structure or the fact that a rule lives in a particular function. Because the due list and the board order are derived, tests can construct orders and observations and assert exact outputs.

**Seam A — the HTTP API, primary.** Flows are driven end to end: register with a hospital number, admit, chart, note, round, order, administer, investigate, review, discharge. Behaviours to cover specifically:

- Two Patients sharing a name and a phone stay separate once both carry hospital numbers.
- A Medication Order changed by a new order leaves the first order intact and stopped.
- A dose slot cannot be recorded twice.
- An Order that is stopped stops producing due entries.
- A Medication Administration that is not given requires a reason.
- An Observation cannot be edited after it is written.
- A Nursing Note correction leaves the corrected note in place.
- A Task raised from a ward round entry belongs to the patient on that entry.
- The Ward Board orders by outstanding work, and the order changes when something becomes overdue.
- A discharged Admission leaves the board and keeps its history.
- An Administrator is refused every Clinical route.
- Derived figures, the due list and the board order, write nothing.

**Observation range marking.** Boundary values at each threshold, asserted as display output rather than as scoring.

**Derived reads write nothing.** A test asserts that reading the due list, the board and the reports adds no rows. This is the guard against a derived figure quietly becoming stored state.

**Frontend.** Smoke and manual testing only, as before. The manual checklist gains the ward board and admission screen at a tablet viewport, the due list across a clock that crosses a scheduled time, and print preview of each sheet.

**The study.** Task-based testing with ward nurses on set tasks, scored with SUS, plus time on task instrumented by the system. The instrumented figure supports the observer's stopwatch rather than replacing it, because an interruption that is not recorded makes the timing wrong. Instrumentation measures the system, never a nurse, and the participant materials must say so.

## Out of Scope

- Diagnosis, treatment recommendations, prescription generation, dose calculation, interaction or allergy checking, and medical image analysis.
- Integration with hospital laboratory or electronic-health-record systems. An Investigation is recorded by hand, and no result is fetched.
- Barcode or wristband verification of a patient or a drug.
- Reading or interpreting a result value. The result note is free text.
- Beds as managed entities, transfers between wards as a workflow, rosters, shifts, and off-duty planning.
- Doctors logging in. Nurses record the doctor's instructions.
- Real-time messaging, paging, push notification, SMS or email alerts.
- Offline operation. The system needs the network, and says so honestly rather than pretending.
- Auto-saving or scheduled anything: the system never acts on a timer.
- Encryption at rest, backup and recovery as tested behaviours. These are operational requirements for the hospital, documented rather than claimed.
- A frontend automated test harness.
- Availability, retention and tamper-evident hashing for the Audit Log.

## Further Notes

- **The pivot is a change of project focus.** Section 1.2.4 of the proposal states the prototype will focus on triage support and queue prioritization only. This spec replaces that focus. No approval gate applies; the change is recorded rather than authorised, and ADR 0014 is where the reason for the removal and what replaces its evidence belong.
- **The dissertation's evidence changes.** The removed Accuracy Evaluation Report is described elsewhere in this repository as the project's central evidence and its flagship artefact. What replaces it is requirements fit against the hospital's stated problems, plus a usability study with SUS and time on task. The project is now health informatics rather than applied machine learning, and the marking criteria to write against follow from that.
- **The triage work is worth keeping findable.** Ticket 22 tags the commit before the deletion. Deleted code that a chapter discusses should be citable, and a tag costs nothing.
- **Terms that vanish.** Triage Assessment, Urgency, Urgency Level, Machine Recommendation, Final Decision, Override, Override Reason, Re-assessment, Queue, Prioritization Engine, Symptom Group and Departure all leave `CONTEXT.md`. ESI leaves the vocabulary with them: it existed here as the evaluation's reference standard, and there is no evaluation left for it to reference.
- **Ethics has lead time.** A usability study with ward staff needs the hospital's approval and probably the university's ethics review. Start it during ticket 23, not after the system is built.
- **The hospital's real forms will change the templates.** Templates are designed from standard nursing documentation practice because the hospital has not supplied their chart, round sheet or observation chart. Expect a revision pass once they do, which the field-per-row template design is built to absorb.
