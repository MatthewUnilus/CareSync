# 0011 — A Medication Order transcribes an instruction, and a change is a stop and a new order

**Status:** Accepted (2026-11-22)

## Context

On a ward round a doctor gives a medication instruction verbally, and the nurse
has to act on it. The instruction has to be recorded, or it is lost between the
round and the shift. The obvious implementation is to record it as a
prescription: capture the drug and dose, work out what is due, and carry the
order forward as the doctor's standing intent.

That implementation claims three things the system cannot support. It would have
to calculate a dose, which needs patient-specific clinical reasoning the system
does not do. It would have to check the dose against a maximum, and check
interactions and allergies, which needs allergy and interaction data the system
does not hold. And it would make the system the author of the prescription
rather than the transcriber of someone else's instruction.

There is also the question of how an order changes. A doctor has to be able to
raise a dose or stop a drug, and the record has to show that the change
happened.

## Decision

A Medication Order is the transcription of an instruction a doctor already gave.
It carries the drug, dose, route, frequency, start time and who instructed it,
and records nothing the system decided.

The system does not calculate a dose, does not check a dose against a maximum,
and does not check interactions or allergies. It is not a prescription.

The order's clinical fields are frozen when it is written. A change is a stop and
a new order, so both the stopped order and the order that replaced it stay in the
record and the change is visible.

## Consequences

- The record says what the doctor said and who recorded it, which is what a
  transcription is. Nothing in the order is the system's own judgement.
- The dose calculation and the interaction and allergy checks are foreclosed, not
  deferred. Adding them later would change what an order is, from a transcription
  to a prescription, and would require clinical data the system deliberately
  holds none of.
- A changed dose leaves two orders, not one edited order. Every due dose is
  produced by an order that existed at the time, so the schedule cannot be
  retroactively rewritten.
- The order is frozen by the same application-layer guard the deleted assessment
  and the Audit Entry use, because ADR 0001 forbids database triggers.
- A stopped order stops producing due doses. What is due is computed at read time
  from the open orders and the round times, so there is no stored schedule to
  bring back into line.
