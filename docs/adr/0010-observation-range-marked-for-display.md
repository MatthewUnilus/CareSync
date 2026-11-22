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

The thresholds the deleted red-flag layer cited cannot be reused as the normal
range. That layer drew them from the Emergency Severity Index handbook (ESI v4),
and every one is an emergency *danger* cut-off, not a normal value: it fired when
an adult heart rate was above 100, respiratory rate above 20, temperature above
38.0 °C, oxygen saturation below 92 percent, or systolic pressure below 90 mmHg.
A danger cut-off is one-sided and sits where a presentation becomes an emergency,
so it lies outside the healthy range — the ESI fever threshold of 38.0 °C is over
half a degree above the top of the normal resting range. Calling a danger cut-off
"normal" would stretch the normal range to just short of an emergency and mark a
genuinely normal adult reading as abnormal. The normal range therefore has to be
sourced in its own right, from a published adult resting reference range, and
kept distinct from the ESI danger cut-offs.

## Decision

The normal range for a reading is the published adult *resting* reference range.
A reading outside its range is marked as such on the chart, beside the previous
reading:

| Reading | Adult resting reference range |
| --- | --- |
| Temperature | 36.5 to 37.3 °C |
| Pulse | 60 to 100 beats per minute |
| Respiratory rate | 12 to 18 breaths per minute |
| Blood pressure | systolic 90 to 120, diastolic 60 to 80 mmHg |
| Oxygen saturation | 95 to 100 percent |

The temperature, pulse, respiratory rate and blood pressure ranges are the ones
NLM MedlinePlus publishes for "the average healthy adult while resting"
(MedlinePlus, *Vital signs*, https://medlineplus.gov/ency/article/002341.htm).
The oxygen saturation range is MedlinePlus's normal level for pulse oximetry
(MedlinePlus, *Pulse oximetry*, https://medlineplus.gov/lab-tests/pulse-oximetry/).

These are the adult ranges, and they are not applied to a patient under 18.
For a patient under 18 the range does not apply, so no reading is marked against
the adult range rather than marking a child against adult values; the chart says
so in place of marks. The recorded values are still returned unchanged — only
the mark is withheld. A paediatric reference range is not invented here and is
out of scope.

The mark is display only. The system never alters a recorded value, never
reorders anything on the strength of one, and never raises an alert. There is no
scoring, no early-warning aggregate score, and no escalation.

The mark is a comparison, not clinical advice: it says a reading sits outside a
published resting range and nothing more. It carries no interpretation, no
diagnosis and no instruction.

## Consequences

- An abnormal value is visible at a glance and the user decides what it means.
  The system contributes a comparison, not a judgement.
- A false mark and a missed mark are both display artefacts. Neither changes a
  stored value, so neither can corrupt the record.
- There is nothing to calibrate and no threshold that carries clinical weight.
  The thresholds are a reference range for marking and are labelled as such in
  the code so a reader does not mistake them for a rule.
- The marked range is not the ESI danger cut-offs the deleted layer cited, so a
  reader cannot trace a mark back to an emergency threshold and read the mark as
  one. A normal value and a danger value are held apart by design.
- The rule now outlives the engine it was written beside. ADR 0006 is Superseded
  by ADR 0014 because its subject, the queue, is gone; the reason it recorded
  narrows to this one and continues to hold.
