# 0012 — An Investigation tracks progress and the review act, and never reads the result

**Status:** Accepted (2026-11-22)

## Context

A doctor requests a test or a procedure, and it is easy to lose between the
request and the result. The nurse has to know what has been requested, what is
still waiting for a result to come back, and what has a result that nobody has
read. Those three are different problems, and a single "done" flag collapses
them.

Once a result arrives, the obvious thing to do with it is read it: parse the
value, flag an abnormal one, and tell the nurse. That would put the system in the
position of interpreting a clinical result, which is diagnosis by another name,
and it would need result formats and reference ranges for every test the ward
might order.

## Decision

An Investigation is recorded by hand against an Admission, and its progress has
four states: requested, sample taken, result available, reviewed.

The result note is free text, recorded as the laboratory gave it. Marking a
result reviewed is the accountable act, and it records who did it and when.

The system never reads a result value, never flags an abnormal result, and never
suggests anything from one. It tracks that a result arrived and that somebody
reviewed it.

## Consequences

- The nurse can tell a test not yet taken from one whose result is waiting, which
  is what stops something going unread. The two awaiting lists are derived from
  the states, so they cannot drift from the record.
- The review is attributable, which is what makes "nothing goes unread"
  checkable rather than asserted.
- Interpretation is foreclosed. Adding it later would change the system from
  tracking progress to reading results, and would need the test-specific
  knowledge the system does not hold.
- No result is fetched from anywhere. There is no integration with laboratory or
  electronic-health-record systems, and the note is what the nurse copied from
  the laboratory, which the system takes at face value.
