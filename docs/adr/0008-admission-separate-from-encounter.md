# 0008 — Admission is separate from Encounter, and vitals have one home

**Status:** Accepted (2026-11-22)

## Context

The system it replaces held a Patient, an Encounter and a Triage Assessment. An
Encounter was the unit of a visit and carried the vitals captured during intake.
That shape fitted a queueing tool where every visit was scored and left.

CareSync is a ward system. A Patient is registered, and when they are an
inpatient they are given an Admission to a ward with a bed or location. The
nursing work hangs off that stay: Observations, Nursing Notes, Medication Orders
and their administrations, Investigations and Tasks all belong to the Admission,
not to a visit. A patient can also arrive through an outpatient visit first, and
that visit and the subsequent stay are one history.

Two things had to be decided, and each has a real alternative:

1. **Whether an Admission is a kind of Encounter or a thing of its own.** The
   cheap option is one entity with a nullable ward and bed, reusing the visit.
2. **Where vital signs live.** They can stay on the Encounter, or move to a
   dedicated Observation.

## Decision

A Patient owns many Encounters and many Admissions, and they are separate
entities. An Encounter is a visit with a reason and an end. An Admission is a
period of inpatient care with a location, and it may link back to the Encounter
it came from so the two read as one history.

Vital signs move out of the Encounter entirely. The Encounter loses the
vital-sign columns it was written to hold. Every set of vitals is an Observation,
which attaches to either an Encounter or an Admission, never both and never
neither. The Observation chart becomes the single time series for a Patient.

## Consequences

- "How long has this Patient been an inpatient" is answerable from the Admission
  alone. Collapsing the two would have made it unanswerable without a second
  concept, and would have forced every outpatient visit to carry a ward and a bed.
- There is one place that holds the truth about vitals, which removes the
  question of which of two places is authoritative. A set of vitals charted on
  the ward and a set charted in a clinic are the same kind of record.
- This is a rewrite of the intake tests, taken deliberately. The tests that assert
  vitals on an Encounter no longer describe the system.
- The Admission becomes the anchor for every ward entity: a note, an order, an
  investigation and a task all name an Admission. Anything that names an Encounter
  instead has to justify why it is about the visit rather than the stay.
- A discharged Admission is closed, not deleted. Its Observations, notes, orders
  and tasks remain part of the record and leave only the working views.
