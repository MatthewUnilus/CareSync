# 30: The visit record and the Observation chart

**What to build:** Vital signs become a time series. A nurse charts a set of vitals against a patient and sees it beside the previous set, so the direction of travel is visible without reading back. This is the answer to the second of the nurse's three problems: checking a patient's latest vitals without walking back to the ward.

**Blocked by:** 28 (the rename lands first).

**Status:** ready-for-agent

- [ ] `Encounter` keeps patient, arrived, ended and a reason for the visit, and its ten vital-sign columns are gone. Ticket 26 already removed the engine's columns; this ticket removes the remaining vitals block so there is exactly one place vitals live.
- [ ] A new `observations` table records one set of vitals at a point in time: the eight readings, the time taken, and the actor who took them.
- [ ] An Observation attaches to either an Encounter or an Admission, with a constraint that exactly one is set, never both and never neither. This mirrors the one-column-per-subject pattern `AuditEntry` already uses and documents.
- [ ] The intake field bounds survive unchanged: pain 1 to 10, temperature 30 to 45, heart rate 20 to 300, respiratory rate 0 to 80, systolic 50 to 300, diastolic 20 to 200, systolic greater than diastolic, saturation 50 to 100.
- [ ] An Observation is append-only, enforced by a `before_update` guard in the application layer, following the pattern the deleted assessment and the Audit Entry use. There are no database triggers (ADR 0001).
- [ ] The chart shows each reading beside its previous value and the time it was taken, with the actor shown.
- [ ] A reading outside its reference range is marked as abnormal, and the mark is display only: nothing is altered, reordered, scored or escalated.
- [ ] New observations up to the latest are listed newest-first for a patient, and an empty chart says so rather than showing zeros.
- [ ] Opening a visit records the first Observation rather than storing vitals on the Encounter.
- [ ] Tests: an Observation cannot be edited after it is written; the exactly-one-subject constraint refuses both and neither; each reading's boundary is rejected above and below; a value at each reference-range threshold is marked and one inside it is not; the chart returns the previous value beside the current one.

## Notes

- The reference ranges are the published adult ranges, and they are the same thresholds the deleted `red_flags.py` already carried citations for. Take the thresholds before ticket 26 deletes that file, or re-derive them from the same source, but do not invent a second set. ADR 0010 records that they are display-only.
- `VitalsFields` and `NumberField` in `frontend/src/IntakeFields.tsx` are reusable as they stand and are the right thing to build the chart form from. `NumberField` exists because the composed `Input` cannot carry `min`, `max` and `step`; its docstring explains why, so read it before working around it.
- The chart is the screen the nurse described walking back to the ward for. It should be reachable from the patient without a search, which is what ticket 31's ward board provides, so build the chart to be embeddable rather than a standalone page.
- Keep `formatInstant` from `queueDisplay.ts` for stamping readings. Ticket 27 kept it deliberately.
- Do not add an early-warning aggregate score. The ranges are per-reading only, and ADR 0010 states why: a score is a clinical judgement the system is not making.
