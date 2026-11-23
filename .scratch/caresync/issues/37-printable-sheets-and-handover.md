# 37: Printable sheets and handover

**What to build:** Three sheets print: a handover sheet of the ward's patients, a medication round sheet to work the round from, and a worklist of outstanding tasks and investigations. Each carries the time it was generated. The paper record keeps running alongside, and these are what makes that possible rather than a half-move to a screen nobody can carry.

**Blocked by:** 32, 33, 34, 35, 36 (each sheet prints what those tickets built).

**Status:** done

- [x] A handover sheet prints the ward's patients with the detail a handover needs: identity, location, why they are there, their latest Observation, their medication situation, their open Tasks and their unreviewed results.
- [x] A medication round sheet prints the doses due in a chosen window, in the order they will be worked, with a space to record each one and the patient's identity against each dose.
- [x] A ward worklist prints outstanding Tasks and Investigations awaiting a result or a review, grouped by patient.
- [x] Every sheet carries its generation time, printed where it can be seen once the sheet is on a clipboard.
- [x] Every sheet carries the line "verify against the system", so a stale sheet is recognisable as stale rather than authoritative.
- [x] `styles/print.css` and the `@media print` rules are added. There are no print styles anywhere in the frontend today.
- [x] Print rules drop the navigation, the controls and the interactive affordances, and use a legible size rather than the screen's type scale.
- [x] A patient with a long history prints the current picture and not the whole record.
- [x] A photo of each printed sheet, or the print preview, is checked by hand rather than by test, since there is no frontend test harness in scope.
- [x] The manual checklist gains print preview of all three sheets at the paper size the ward uses.

## Notes

- ADR 0009 is the reason for the generation stamp and the verify line: nothing printed is a legal record, and the hospital's paper chart remains that. Printing patient data is also a data-protection question, and worklists rather than records is the answer to it.
- There is no existing print stylesheet, so this is greenfield. The theme is built on semantic tokens with a dark mode and a teal brand re-tint, and none of that belongs on paper: print rules should force a light, high-contrast presentation rather than inherit the screen theme.
- Table styling already exists as a vocabulary in `frontend/src/design.ts`, which is the right thing to build the sheets from. Do not invent a second table style for print.
- The sheets are the practical answer to the ward's shared wifi and to a tablet carried between rooms, and they are also the most likely thing to be used in the study. Consider printing one during a study session and asking the participant to work from it.
- A four-clinical-view segmented control plus print buttons on a tablet is a lot of chrome. If the sheet printing crowds the header, that is the point to reconsider the workspace navigation rather than to add a second menu.

## Comments

Built on `ticket/37-printable-sheets`, merged to
`integration/caresync-ward-features`. `npm run build:web` green.

**Three sheets, one module.** `frontend/src/PrintSheets.tsx` holds
`HandoverSheet`, `MedicationRoundSheet` and `WardWorklistSheet`, plus a
`PrintSheetLauncher` that mounts the chosen one from the Ward Board. The
handover sheet carries identity, location, the linked Encounter, the latest
Observation with its abnormal count, the medication situation, open Tasks and
unreviewed results. The round sheet reads the due list for a chosen UTC day and
prints one row per dose with a status column to work from. The worklist groups
open Tasks and unreviewed/awaiting Investigations by patient.

**Print styles are greenfield.** `frontend/styles/print.css` is imported from
`globals.css`. It forces white-on-black, drops the header, controls, buttons and
the segmented control, sets legible point sizes and uses the `print-table`
vocabulary built from the same table shapes `design.ts` already defines — no
second table style was invented.

**ADR 0009 on every sheet.** Each carries its generation time and the line
"verify against the system", so a stale sheet is recognisable rather than
authoritative.

**A long history prints the current picture.** The handover sheet shows the
latest Observation and the counts, not the whole record, and the worklist shows
outstanding work only.

**Manual check, as the ticket asks.** Printing is verified by hand: the three
sheets render in the browser's print preview at A4. There is no frontend test
harness in scope, so this stays manual; the checklist item is the print preview
of all three sheets at the paper size the ward uses.

**Follow-up: the manual checklist now exists (2026-11-23).** Ticket 37 and the
spec both refer to a "manual checklist", but no such file was ever committed.
`MANUAL-CHECKLIST.md` was added at the repo root: a 13-section smoke and manual
script covering authentication, the session lock, intake and identity, the ward
board and admission, the observation chart, nursing notes, tasks, medications,
investigations, the printable sheets, the administrator dashboard and audit log,
study instrumentation, and the build and API suite. The README's "Run the tests"
section and Layout inventory now point at it.
