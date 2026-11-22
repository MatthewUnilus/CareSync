# 0001 — Run SQLite locally, Postgres in production

**Status:** Accepted (2026-11-03)

## Context

The spec names two seams: the backend HTTP API, "exercised against a real Postgres", and the Prioritization Engine pure function. The development machine has neither Docker nor a local PostgreSQL server, and the build is greenfield. Blocking every ticket on a container install would stall the whole graph.

## Decision

One SQLAlchemy model layer, one `DATABASE_URL`. Local development and the API-level test suite run against SQLite. The demonstration deployment runs against Postgres, and a Compose file remains the documented way to bring Postgres up.

Application code stays dialect-neutral so the switch is a connection string:

- no `JSONB`, no `ARRAY`, no Postgres enums — enums are stored as validated strings
- no dialect-specific SQL, no `ON CONFLICT` shortcuts
- timestamps stored as timezone-aware UTC `DateTime`
- append-only behaviour enforced in the application layer, not by database triggers

## Consequences

- The suite runs fast, offline, and with no external service, which keeps the ticket frontier moving.
- The "real Postgres" property is documented but unproven locally. It is covered by running the deployed instance against Postgres, and by keeping the model layer portable.
- If the engine's evaluation ever needs Postgres-only features, or dialect drift produces a genuine defect, this decision is reopened rather than worked around.
- Deviation from the spec's Testing Decisions is deliberate and recorded here, not absorbed silently.

## Amendment (2026-11-22)

The decision stands unchanged: one dialect-neutral model layer, SQLite locally,
Postgres in production, append-only enforced in the application layer and not by
database triggers. The two later ward decisions lean on it directly. Medication
Orders are frozen and Medication Administrations are append-only by the same
application-layer guard, and the Audit Entry is written in the mutation's
transaction for the same reason. None of those can use a trigger.

The context above named a second seam, the Prioritization Engine pure function.
ADR 0014 removes the engine, so that seam is empty. The data layer is unaffected:
the model layer was never engine-specific, and the constraint it imposes applies
to the ward entities exactly as it applied to the triage ones.
