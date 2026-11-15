# 0006 — Escalate the display of a long wait, never the decision

**Status:** Accepted (2026-11-10)

## Context

The Queue is ordered by Final Decision (urgency) and then arrival time, and the board showed every card at one uniform weight: the urgency word, the patient name and the elapsed wait were all 14px, and the wait sat greyed at the right edge. Two problems followed.

First, the board could not be read at a glance. A triage nurse scanning it under time pressure had no visual ranking of what was most urgent or most overdue; every card looked alike.

Second, and worse, a six-day wait was rendered as `147h 19m` and looked structurally identical to a five-minute wait. Nothing on the screen distinguished a boarding incident from a routine arrival. Because the ordering rule is urgency-first, a six-day Low legitimately sits *below* a shorter-waiting Medium — which reads as a bug unless the rule is stated, and there was no statement of it anywhere in the interface.

The obvious "fix" — reorder the Queue by waiting time, or auto-escalate a stale Encounter's Urgency Level — is out of scope. `spec.md` is explicit: static Urgency per assessment, no time-based escalation, no automatic re-triage, re-assessment is a manual Clinical action. Reordering the board by wait would also destroy the property the Accuracy Evaluation depends on, since the Queue is the sort over Final Decisions.

## Decision

Escalate the *presentation* of a wait, and leave every decision untouched.

- `queueDisplay.ts` bands a wait into `routine` (< 4h), `long` (>= 4h), `breach` (>= 12h) and `critical` (>= 24h). These are display thresholds, not clinical rules; they are deliberately generous so an ordinary day does not scream.
- The waiting figure is the largest thing on the card past the routine band (up to `text-title-2-semibold`, 20px, rose) with a plain-language label (`boarding 6d — escalate`). Size and weight carry the signal alongside colour, so escalation survives red-green colour blindness.
- Past a day the figure is expressed in days (`6d 4h`), because `147h 19m` does not read as six days.
- The card surface is **not** tinted for an escalated wait. Tinting measurably lowered the contrast of every other word on the card; the 4px urgency band, the enlarged rose figure and the label already carry it.
- The board states the ordering rule in its header: "Ordered by urgency, then arrival within a level. Long waits are highlighted but do not change this order."
- The Queue's sort in `app/queue.py` and every stored Urgency Level are unchanged. Nothing in this ADR can re-triage a patient.

## Consequences

- A clinician can see from across the room which patients are most urgent and which waits have become unreasonable, and can see that a long-waiting Low below a Medium is the documented rule rather than a defect.
- The escalation bands are a product judgement with no clinical citation behind them, unlike the red-flag thresholds. They are labelled as presentation-only in the code, and a reader must not mistake them for a triage rule. Choosing them differently changes only what looks loud.
- Because the decision path is untouched, no evaluation number moves and no stored record changes meaning.
- The residual honest gap: the board can *show* a six-day wait but cannot *act* on one. Automatic escalation is out of scope, so the loudest thing the system can do is say so.
