# Context — CareSync

Glossary only. No implementation details, no schemas, no technology choices.

## Terms

### Patient
A person. Persists indefinitely, independent of any visit. Carries a hospital number, captured at registration and optional, so that two people who share a name are never confused. Two people sharing a name and a contact number are still two Patients once each has a hospital number: a family phone number does not merge them. A hospital number that differs from another means a different Patient.

### Encounter
A single visit by one Patient to a facility, with a reason and an end. A Patient may have many Encounters over time. An Encounter is a visit, not an inpatient stay, and does not by itself place the Patient on a ward. When a visit leads to admission, the Admission is linked to the Encounter it came from, so the visit and the stay read as one history.

### Admission
A period of inpatient care for one Patient on a ward, with a bed or location. It begins at admission and ends at Discharge. A Patient may have many Admissions. It is *not* an Encounter: an Encounter is a visit with a reason, an Admission is a stay with a location, and collapsing the two would force every outpatient visit to carry a ward and a bed and would make "how long has this Patient been an inpatient" unanswerable. The ward and the bed are where an Admission is, not what it is.

### Discharge
The act that ends an Admission, performed by a Clinical user. The Admission is closed and leaves the Ward Board; it is not deleted and its record is not changed, so a discharged Admission keeps its history. The system never discharges an Admission on its own.

### Observation
One set of vital signs, charted at a point in time against an Encounter or an Admission, never both and never neither. A Patient's Observations are their single time series for vitals, so one place holds the current picture rather than two. Each reading is stamped with the time it was taken and attributed to the Clinical user who took it, and a set is unchangeable once saved. A reading outside its normal range is marked for display and nothing more: the system never alters a recorded value, never reorders anything on the strength of one, and never raises an alert. An Observation is not an assessment and carries no score. The normal range is the published adult reference range.

### Nursing Note
A free-text entry written by a Clinical user against an Admission, from a Note Template. It is stamped with the time and the author. A correction is a new note that says it corrects the first; the corrected note stays in the record and the original is never edited. A Patient's notes are read in time order, so a shift can be read back. A Nursing Note is neither a Report nor a Task.

### Note Template
A fixed set of named fields for a common nursing document: a shift assessment, a ward round entry, an intervention record, a handover entry and a discharge summary. It gives a note a starting shape instead of a blank page. A template is a vocabulary, not a form with validation: every field value is free text, and there is no controlled clinical terminology. The templates are defined in one place as a fixed vocabulary, so a change to a template field needs no database change and no client change.

### Medication Order
The transcription of a medication instruction a doctor has already given, recorded against an Admission by a Clinical user. It carries the drug, dose, route, frequency, start time and who instructed it. It is *not* a prescription: the system does not calculate a dose, does not check a dose against a maximum, and does not check interactions or allergies, because it holds no allergy or interaction data and because generating a prescription is outside the project. Its clinical fields are frozen when it is written, so a change is a stop and a new order, and the change is visible in the record. A stopped order stops producing due doses.

### Medication Administration
The record that one dose from a Medication Order was given, withheld, refused or unavailable at a due time, made by a Clinical user. One row exists per order and due time, so a dose slot can be recorded once and a double entry cannot inflate the record. A reason is required when a dose was not given, so the omission is explained. It is append-only. It records what a nurse attests to; it is not a barcode or wristband verification.

### Medication Round Time
The clock time a frequency maps to, held in one place as a documented convention and shown to the user, so nobody mistakes it for clinical advice. An overdue dose is marked as overdue and nothing else happens: nothing is escalated and no order changes.

### Investigation
A test or procedure a doctor has requested, recorded against an Admission by a Clinical user. Its progress has four states: requested, sample taken, result available, reviewed. It carries a free-text result note, recorded as the laboratory gave it, and records who marked it reviewed and when. Marking a result reviewed is the accountable act. The system tracks that a result arrived and that somebody read it; it never reads or interprets a result value and never flags an abnormal result. An Investigation is not a diagnosis and not a treatment.

A Clinical user can send an Investigation to the laboratory after recording sample collection. A Laboratory user acknowledges the request and publishes a free-text result on the same Investigation. A published result for a discharged Admission stays in its history and can be reviewed from the late results list.

### Task
A unit of work raised against an Admission by a Clinical user, either by hand or from a ward round entry. It has an optional due time, so work with a deadline is distinguishable from work without one, and an optional assignee, so both an assigned caseload and a shared ward work. A Clinical user marks it done, and tasks past their due time are shown as overdue. A Task is how an instruction becomes something to work; it is not the instruction itself, and the system never reassigns a Task on its own.

### Ward Board
A view of the ward's open Admissions, ordered by outstanding work counted from the record: overdue medication doses, then doses due now, then results awaiting review, then open Tasks, with bed order breaking ties. It is recalculated on every read and stores nothing. It is a count of what the record shows is outstanding, not a score and not a clinical judgement, and it does not decide who is treated first.

### Roles
Three roles:

- **Clinical** — register Patients, admit and discharge them, chart Observations, write Nursing Notes, record Medication Orders and Medication Administrations, track Investigations and manage Tasks.
- **Laboratory** — see sent Investigations, acknowledge receipt, and publish results.
- **Administrator** — read-only oversight: the operations dashboard and the Audit Log. No clinical actions.

### Report
A read-only view derived on demand from the clinical record, never a stored snapshot and never computed from anything that could drift from it. The operations dashboard's figures are Reports: the ward census and length of stay, the proportion of doses recorded on time, the count of results still awaiting review, and tasks completed against tasks raised. An Audit Entry is not a Report.

### Audit Entry
An append-only record that one clinical mutation happened: who performed it, which action it was, which Patient, Encounter or Admission it touched, and when. Written in the same transaction as the change it describes, so a change cannot exist without its record and a rolled-back change leaves none. An Audit Entry is not itself a decision; it is the durable account of an action that was taken.

The **Audit Log** is the ordering of Audit Entries, read by an Administrator. It is neither a Report (it is not derived) nor a clinical action.
