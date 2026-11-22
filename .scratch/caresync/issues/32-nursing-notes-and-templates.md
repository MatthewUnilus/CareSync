# 32: Nursing notes and Note Templates

**What to build:** A nurse writes a nursing note from a template rather than from a blank page, and the note starts with the patient's latest vitals already filled in. This is the first of the nurse's three problems, and the prefill is the part that actually saves time: retyping numbers the system already holds is the slowest part of charting.

**Blocked by:** 31 (a note belongs to an Admission).

**Status:** done

- [x] New tables: `nursing_notes`, holding the Admission, the template, the author and the time, and `nursing_note_fields`, holding one row per field.
- [x] Five Note Templates are defined: Shift Assessment, Ward Round Entry, Intervention Record, Handover Entry, Discharge Summary.
- [x] Template definitions live in one module as a fixed vocabulary and are served by `GET /api/ward/note-templates`. Adding a field to a template is a code change with no schema change and no client change.
- [x] The five templates carry field sets drawn from standard nursing documentation practice, since the hospital has not supplied their chart yet. Expect to revise them.
- [x] A new note prefills from the patient's latest Observation, so the vitals are already there to confirm or amend rather than to retype.
- [x] Each note is stamped with its time and its author, and the author is a foreign key exposed through a relationship rather than a copied name.
- [x] Correcting a note appends a new note that points at the one it corrects. The corrected note stays in the record and is shown as corrected.
- [x] A patient's notes read in time order, so the shift reads back front to back.
- [x] Field values are free text. No coded clinical values, because there is no controlled terminology in scope.
- [x] Writing a note and correcting a note each write exactly one Audit Entry in the same transaction as the change.
- [x] The board's outstanding-work counts are unaffected by this ticket, which is correct: a note is not outstanding work.
- [x] Tests: a note from each of the five templates saves and reads back with its fields; a correction leaves the corrected note in place and linked; a note renders with the latest Observation's values prefilled; the template route serves all five with their fields; writing a note appends one audit entry.

## Notes

- The field-per-row design is ADR 0013 and the reason is the missing migration tool. A table is created at startup but a new column is not, so a template stored as columns would need the local database deleted every time the hospital's real form differed from ours. One row per field absorbs that change without a schema change.
- Design the templates from standard nursing documentation: a shift assessment covers general condition, mobility, skin, pain, intake and output; an intervention record covers what was done and the response; a handover entry covers the situation, background, current state and what to watch; a discharge summary covers the stay and the state at leaving. Keep the field lists short. A template with twenty fields will not be filled in.
- The prefill is the headline behaviour and should be visible in the interface, not silent. A nurse who cannot see that the numbers came from the last Observation will retype them anyway.
- `supersedes_assessment_id` on the deleted `TriageAssessment` is the pattern for a correction link. It is gone by this ticket, so take the shape from `git show triage-engine-final` if it helps, and keep the same one-directional link.
- The Intervention Record and the Ward Round Entry are adjacent: one records what was done, the other what was asked for. Ticket 33 makes the round entry raise Tasks, so leave the round entry's fields easy to map onto a Task.
