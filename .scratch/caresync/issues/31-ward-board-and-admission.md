# 31: Ward admission, discharge and the ward board

**What to build:** A patient is admitted to the ward, appears on a board with the other patients, and is discharged at the end of the stay. The board is the ward's working view: for each patient, their latest Observation, their outstanding medication, their open Tasks and their unreviewed results, ordered so the patients with overdue work come first. This is the front door for everything the later ward tickets add to.

**Blocked by:** 30 (the board shows the latest Observation, so the chart must exist).

**Status:** ready-for-agent

- [ ] A new `admissions` table records the Patient, the ward, the bed or location, the admission instant, the discharge instant, and an optional link to the Encounter the patient was seen in first.
- [ ] Admitting a patient directly, with no prior visit, works.
- [ ] Admitting from an existing Encounter links the two, so the visit and the stay read as one history.
- [ ] A location move is recorded and shows on the board, so the board always says where a patient is.
- [ ] Discharging ends the stay. A discharged patient leaves the board and keeps their full history, including their Observations and everything the later tickets attach.
- [ ] `GET /api/ward/board` returns the open Admissions with, for each, the latest Observation, the outstanding medication count, the open Task count and the count of results awaiting review. The counts return zero where the later features do not exist yet, so this ticket lands before them and still works.
- [ ] The board orders by outstanding work: patients with overdue medication doses first, then doses due now, then results awaiting review, then open Tasks, with bed order breaking ties.
- [ ] The board recalculates on every read and stores nothing. A test asserts that reading it adds no rows.
- [ ] A new `WardBoard.tsx` is added as a view in `ClinicalWorkspace.tsx`, following the three-line pattern the existing views use.
- [ ] Admission and discharge each write exactly one Audit Entry in the same transaction as the change, and a location move does too.
- [ ] Tests: admit, see on the board, discharge, gone from the board and still in history; the board's order changes when an item becomes overdue; a discharged Admission keeps its data; the board's read writes nothing.

## Notes

- ADR 0008 is why Admission is separate from Encounter. An Encounter is a visit with a reason and an end; an Admission is a period of inpatient care with a location. Do not collapse them, and do not add a ward or a bed to an Encounter.
- Follow `departures.py`'s reduced shape for the discharge instant rather than inventing a second end-of-stay pattern. Ticket 26 kept `EncounterStatus` and the end-of-visit instant for exactly this reason.
- The board's counts are the seam the later tickets fill in. Build them as a small read model with a function per count, each returning zero, so medicine, tasks and investigations each replace one function rather than rewriting the board.
- `ClinicalWorkspace.tsx` is 59 lines and the view pattern is documented in its own comment: add the id to the union type, add a `SegmentedControlItem` with `min-h-11 px-4`, extend the guard, add the render branch. Four clinical views will not fit a segmented control comfortably on a tablet, so if it starts to crowd, that is a real design question worth raising rather than squeezing.
- Audit actions for admission, discharge and location move are added to the enum, and ticket 24's label table is what keeps the administrator view readable.
- The board is the answer to the nurse's third problem and it is the screen the usability study will put in front of participants. Build it to carry its own weight visually, not as a placeholder for the later tickets.
