# 0014 — The triage engine is removed, its evidence is replaced, and patient identity changes with it

**Status:** Accepted (2026-11-22)

## Context

The proposal states in section 1.2.4 that the prototype will focus on triage
support and queue prioritisation only. The build did that: a Prioritization
Engine scored each Encounter's Urgency, a Queue ordered by that score, an Override
let staff disagree, and an Accuracy Evaluation Report compared the engine's
Machine Recommendation against an ESI-derived ground truth. The Accuracy
Evaluation Report is described elsewhere in this repository as the project's
central evidence and its flagship artefact.

The reported figures undercut that. On the interim open dataset (ADR 0005) the
composed engine scores below the majority baseline, and the middle tier is not
separable from the engine's inputs at all, because ESI separates ESI 3 from
ESI 4-5 by projected resource need and the engine collects no resource
information. The project's contribution, as measured, is a classifier that does
less well than always guessing the commonest class.

At the same time the ward problem the retired system never addressed is real and
narrower: nurses lose time to documentation, lose access to a patient's latest
information when working elsewhere in the hospital, and lose track of outstanding
investigations, medication and instructions across several patients.

The identity rule has to change with the focus. The `proposal-gaps` spec froze
the rule that a Patient matches on normalised name together with normalised
contact phone. That rule fails on a ward, where several inpatients can share a
surname and a family phone number is entered for more than one of them.

## Decision

The triage engine is removed. The Prioritization Engine, the Queue, Override,
Override Reason, Re-assessment, Departure, Symptom Groups and the Accuracy
Evaluation Report all leave the system. A ticket tags the commit before the
deletion so a dissertation chapter can cite the deleted code.

What replaces the Accuracy Evaluation Report as evidence is requirements fit
against the hospital's stated problems, plus a usability study with ward nurses:
task-based testing on the tasks they actually do, scored with SUS, with time on
task instrumented by the system. The instrumented figure supports an observer's
stopwatch rather than replacing it, because an interruption the system does not
record would make the timing wrong. The study measures the system, never a nurse,
and the participant materials say so. Ethics and hospital approval start now,
because both have lead time and the study gates the evidence.

The identity rule changes. A hospital number is captured at registration,
optional and indexed. Equal numbers mean the same Patient; different numbers mean
different Patients; with neither number present, the frozen name-and-phone rule
still applies. A family phone number no longer merges two people once each
carries a hospital number.

This changes the proposal's stated focus. No approval gate applies; the change is
recorded here rather than authorised, so the reason is written down.

## Consequences

- The project is health informatics, not applied machine learning. The marking
  criteria to write against follow from that, and the dissertation's central
  evidence changes from a model's accuracy to whether the system fits the ward's
  problems and is usable by the people who work there.
- The two seams change. Seam A remains the HTTP API. Seam B was the engine's pure
  function and is now empty: with no engine there is no second seam, so the
  evaluation surface is the usability study rather than a scoring harness. The
  removed subsystem documents move to `docs/archive/` so a reader does not take
  them for current design and so a chapter can still cite them.
- ADRs 0002 to 0006 are Superseded by this one, not deleted: each records a
  decision that was right for a system with an engine and is wrong or moot for a
  system without one. ADR 0001 (the data layer) and ADR 0007 (the audit log) are
  kept; the audit log's action set grows to cover the ward and its label set moves
  to one source of truth beside the enum.
- The rule ADR 0006 recorded, "the system never acts on a timer", narrows to that
  reason and survives in ADR 0010, which restates it for a system with no engine
  to protect.
- A hospital number that is absent leaves the old rule in force, so the change is
  additive: it separates people the old rule merged, and never merges people the
  old rule kept apart.
- Scope out of the window with the engine: diagnosis, treatment recommendation,
  prescription generation, dose calculation, interaction and allergy checking, and
  medical image analysis. All were already out of scope; none returns.
