# 36: Investigations and the chase list

**What to build:** A test the doctor requested is recorded, followed to its result, and marked reviewed. Two worklists fall out of it: results nobody has read yet, and tests nobody has a result for yet. This is the rest of the nurse's third problem, which named laboratory results and outstanding investigations explicitly.

**Blocked by:** 31 (an Investigation belongs to an Admission).

**Status:** done

- [x] A new `investigations` table records the Admission, the name of the test, who requested it, the state, an optional free-text result note, and the review act's actor and time.
- [x] The state set is fixed and four values long: requested, sample taken, result available, reviewed.
- [x] A result note is free text, recorded as the laboratory gave it. The system never reads a value, never flags an abnormal result and never suggests anything from one.
- [x] Marking a result reviewed records who and when. It is the accountable act.
- [x] A result can be marked reviewed only once it is available. Marking an unavailable result reviewed is refused.
- [x] A worklist shows every result awaiting review across the ward, so nothing goes unread.
- [x] A second worklist shows every test still awaiting a result, so the nurse knows what to chase.
- [x] The ward board's results-awaiting-review count starts returning a real figure, replacing the zero that ticket 31 stubbed.
- [x] Recording an investigation, moving its state and marking a result reviewed each write exactly one Audit Entry in the same transaction as the change.
- [x] Tests: the four states move in order and an out-of-order move is refused; a result cannot be reviewed before it is available; the review records its actor and time; both worklists cover several patients; an interpretation is never produced, asserted by the absence of any value parsing.

## Notes

- ADR 0012 is the boundary: this tracks progress and the review act. The system is not a results viewer and does not read a value. That is why the result note is free text rather than a structured value with a reference range.
- Temptation to flag an abnormal result will be strong, since the Observation chart already marks out-of-range values. Resist it: an Observation's range is a published reference range for a reading the nurse just took, and a laboratory result's range is assay-specific and printed by the laboratory. The two are not the same thing.
- The four states are the minimum that answers "what do I chase" and "what have I not read". If the hospital's workflow has a fifth, such as a sample rejected and needing a repeat, add it here rather than leaving nurses to encode it in the free text.
- Free-text test names will be inconsistent. A controlled vocabulary is out of scope, so expect variation and do not add fuzzy matching. If the hospital has a standard list, that is a revision pass, which the free text absorbs.
- Two worklists in one ticket is right because they are one table read two ways. Build them as two filters over the same read, not two features.
