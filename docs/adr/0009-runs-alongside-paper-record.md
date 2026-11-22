# 0009 — The system runs alongside the paper nursing record, and a printed sheet is a worklist

**Status:** Accepted (2026-11-22)

## Context

The hospital's paper nursing record is the legal chart. It is what the ward runs
on today, and it is not being withdrawn for this system. CareSync is an academic
prototype deployed on the hospital's network, and it cannot claim to be the
record of care: it has no signing authority, no retention guarantee and no
tamper-evident history.

That leaves the question of what a printed sheet is. A nurse wants paper at the
handover and on the medication round, because the round is worked with a trolley
and a printer is faster than a tablet. If a sheet is the record, then a sheet
printed at 08:00 must stay true all shift, and the system has to guarantee that
the paper matches the screen. It cannot.

## Decision

The system runs alongside the paper nursing record rather than replacing it. The
printed sheets are worklists, and nothing printed is a legal record.

Every printed sheet carries its generation time and the line "verify against the
system". A sheet of the handover, the medication round, or the ward's outstanding
tasks and investigations is a snapshot of the record at the moment it was
printed, and the reader is told so on the sheet itself.

## Consequences

- A stale sheet is recognisable as stale from its own header, so a sheet found on
  a desk is not mistaken for the current state.
- No print path has to enforce currency, which keeps the sheets a pure projection
  of the record and keeps the print code free of state.
- The system makes no claim to be the record of care, so availability, retention
  and encryption at rest stay operational requirements for the hospital rather
  than properties this prototype demonstrates. ADR 0001 already takes that
  position on the data layer.
- The medication round can be worked on paper if that is faster, without the
  system pretending the paper is authoritative. The round time and the overdue
  marking are documented so the paper sheet and the screen agree on the
  convention.
