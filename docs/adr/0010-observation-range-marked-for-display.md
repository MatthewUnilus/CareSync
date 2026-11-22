# 0010 — An Observation outside its reference range is marked for display and nothing more

**Status:** Accepted (2026-11-22)

## Context

An Observation charted by a nurse can fall outside its normal range. The useful
thing to do with that fact is to make it visible, so a nurse scanning a chart
sees an abnormal value without reading every number. The tempting thing to do is
to act on it: score it, aggregate it into an early-warning figure, escalate it,
or reorder the ward on the strength of it.

The system this replaces had a scoring engine and a red-flag safety layer, and
ADR 0006 rejected reordering the queue by wait and auto-escalation. It did so in
a system that had a queue and an urgency level to escalate. CareSync
has neither, so the rule has to be restated for a system with no engine to
protect. What survives is the reason under the old rule, which was never about
the engine: the system does not act on a timer, and it does not decide.

## Decision

The normal range for a reading is the published adult reference range, and it is
the same set of thresholds the deleted red-flag layer already cited. A reading
outside its range is marked as such on the chart, beside the previous reading.

The mark is display only. The system never alters a recorded value, never
reorders anything on the strength of one, and never raises an alert. There is no
scoring, no early-warning aggregate score, and no escalation.

## Consequences

- An abnormal value is visible at a glance and the user decides what it means.
  The system contributes a comparison, not a judgement.
- A false mark and a missed mark are both display artefacts. Neither changes a
  stored value, so neither can corrupt the record.
- There is nothing to calibrate and no threshold that carries clinical weight.
  The thresholds are a reference range for marking and are labelled as such in
  the code so a reader does not mistake them for a rule.
- The rule now outlives the engine it was written beside. ADR 0006 is Superseded
  by ADR 0014 because its subject, the queue, is gone; the reason it recorded
  narrows to this one and continues to hold.
