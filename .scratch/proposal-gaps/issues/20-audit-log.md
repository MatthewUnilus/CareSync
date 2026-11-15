# 20: Audit log

**What to build:** Every clinical mutation leaves an append-only, attributable record: who did it, what they did, to which Patient/Encounter/Assessment, and when. An Administrator can read the log. This is the proposal's "audit logs" enhanced function; today only Overrides record their actor.

**Blocked by:** none.

**Status:** open

- [ ] A new table records the actor, a validated action from a fixed set, a timezone-aware timestamp, an optional detail, and nullable subject references to the Patient, Encounter and Assessment involved.
- [ ] The action column is constrained to a fixed set of values using the same pattern as the Override Reason constraint (validated string, application-layer enforcement, no database triggers — per ADR 0001).
- [ ] The table is append-only: an in-place edit of an existing entry is rejected by a `before_update` guard mirroring the Triage Assessment guard.
- [ ] All six clinical mutations write exactly one entry: register Patient, open Encounter, correct intake, Override, Re-assessment, Departure.
- [ ] Each entry names the actor who performed the action, and the actor is loaded with joined fetch as the Override's actor is.
- [ ] The audit entry is written in the same transaction as the change it describes: a mutation that rolls back leaves no audit entry.
- [ ] Registration is handled correctly despite `patients.find_or_create_patient` committing internally — the transaction boundary is verified by test, not assumed.
- [ ] An Administrator-only route reads the log, following the existing report routes; a Clinical user is refused.
- [ ] The log can be filtered to a single Encounter, so one visit's history can be reconstructed.
- [ ] Tests: each of the six mutations writes one correct entry; the rollback property holds; an edit is rejected; Administrator can read and Clinical cannot.

## Notes

- Model the table on `Override`: actor foreign key, validated string column, `DateTime(timezone=True)` defaulting to `utc_now`, subject foreign keys.
- Follow `overrides.perform_override`'s discipline: the domain function adds to the session and the route commits. Do not commit inside the audit helper.
- `patients.find_or_create_patient` commits internally — check this carefully. Either add the audit entry before that commit or lift the commit out, whichever keeps one transaction. Verify with a rollback test.
- Store the actor as a foreign key and expose the name through the relationship, as `Override` does, rather than denormalising the name onto every row.
- The Administrator surface is the natural home for the read view; add it under ticket 21's documentation pass if a UI section is included.

## Comments
