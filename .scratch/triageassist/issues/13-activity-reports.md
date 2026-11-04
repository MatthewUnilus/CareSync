# 13: Activity Reports

**What to build:** Three Reports on the Administrator dashboard — Daily Queue, Priority Distribution, and Performance — each derived on demand from stored Triage Assessments rather than from live queue state or a stored snapshot.

**Blocked by:** 11.

**Status:** done

- [ ] The Daily Queue Report shows a day's volume and throughput.
- [ ] The Priority Distribution Report shows how Urgency Levels were distributed across Encounters.
- [ ] The Performance Report shows time waiting and processing time.
- [ ] Every Report is computed on demand from stored Triage Assessments and departure instants, never from a materialised snapshot.
- [ ] A Report's figures change when the underlying records change, and change back when they are reverted.
- [ ] An Administrator can view all three Reports on the web dashboard.
- [ ] Reports are read-only: viewing one performs no clinical action and changes no record.

## Comments

Resolved on `integration` (merge `6e2e130`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
