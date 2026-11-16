# 0007 — Audit log written in the mutation's transaction, append-only in the application layer

**Status:** Accepted (2026-11-16)

## Context

The proposal's enhanced functions promise audit logs. Until now only an Override
recorded who performed it; registration, opening an Encounter, intake
correction, Re-assessment and Departure changed state with no attributable
record beyond the row they mutated. An examiner reading the record could see
*what* a stored Encounter contained but not *who* put it there or *when* the
decision was made.

Three things had to be decided, and each has a real alternative:

1. **Where the entry is written.** In the same transaction as the change, or
   alongside it as a best-effort side write.
2. **How append-only is enforced.** In the application layer, or with a database
   trigger or a permissions grant.
3. **What is stored.** The actor as a foreign key, or the actor's name
   denormalised onto every row.

## Decision

A single `audit_entries` table records every clinical mutation. Each row carries
the actor (a foreign key to `users`, loaded with joined fetch as the Override's
actor is), a validated action from a fixed set, a timezone-aware timestamp
defaulting to `utc_now`, an optional free-text detail, and nullable subject
foreign keys to the Patient, Encounter and Triage Assessment involved. The fixed
action set lives once, in `backend/app/audit_actions.py`, and is constrained the
same way the Override Reason set is: a validated string column with an
application-layer check, not a database enum.

The entry is added to the session **in the same transaction as the change it
describes**, and the route commits. Domain functions continue not to commit,
following `overrides.perform_override`. A mutation that rolls back therefore
leaves no audit row — a change without its record is impossible, which is the
property the ticket tests directly.

Append-only is enforced in the application layer with a `before_update` event
guard, mirroring the Triage Assessment frozen-field guard, for the reasons ADR
0001 already gives: one dialect-neutral model layer, no triggers, no
dialect-specific SQL.

The actor is stored as a foreign key, not as a copy of their name, so a renamed
or deactivated user is reflected consistently and the log holds one row per
action rather than per action-plus-name.

## Consequences

- Every state-changing clinical action is attributable and time-ordered, and the
  two failure modes that matter are structurally excluded: an unrecorded change,
  and an edited record.
- The transaction discipline is not free — it constrains how mutation functions
  are written. `patients.find_or_create_patient` commits internally, so
  registration needed its commit boundary examined rather than assumed; the
  audit row is added before that commit so the two stay together.
- Administrator-readable only, like every other oversight surface. The log is
  read, never written, from the API.
- Authentication events (login, logout, password change) are deliberately **not**
  in this log. The proposal's audit-log promise is about clinical actions, and
  mixing session events into the clinical record would blur what the view means.
  If auth auditing is wanted it should be a separate, clearly named surface.
- No retention policy, export, or tamper-evident hashing is claimed. Those are
  operational concerns a local prototype cannot honestly demonstrate, the same
  position ADR 0001 takes on availability and encryption at rest.
