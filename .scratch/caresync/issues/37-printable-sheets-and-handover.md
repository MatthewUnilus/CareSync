# 37: Printable sheets and handover

**What to build:** Three sheets print: a handover sheet of the ward's patients, a medication round sheet to work the round from, and a worklist of outstanding tasks and investigations. Each carries the time it was generated. The paper record keeps running alongside, and these are what makes that possible rather than a half-move to a screen nobody can carry.

**Blocked by:** 32, 33, 34, 35, 36 (each sheet prints what those tickets built).

**Status:** ready-for-agent

- [ ] A handover sheet prints the ward's patients with the detail a handover needs: identity, location, why they are there, their latest Observation, their medication situation, their open Tasks and their unreviewed results.
- [ ] A medication round sheet prints the doses due in a chosen window, in the order they will be worked, with a space to record each one and the patient's identity against each dose.
- [ ] A ward worklist prints outstanding Tasks and Investigations awaiting a result or a review, grouped by patient.
- [ ] Every sheet carries its generation time, printed where it can be seen once the sheet is on a clipboard.
- [ ] Every sheet carries the line "verify against the system", so a stale sheet is recognisable as stale rather than authoritative.
- [ ] `styles/print.css` and the `@media print` rules are added. There are no print styles anywhere in the frontend today.
- [ ] Print rules drop the navigation, the controls and the interactive affordances, and use a legible size rather than the screen's type scale.
- [ ] A patient with a long history prints the current picture and not the whole record.
- [ ] A photo of each printed sheet, or the print preview, is checked by hand rather than by test, since there is no frontend test harness in scope.
- [ ] The manual checklist gains print preview of all three sheets at the paper size the ward uses.

## Notes

- ADR 0009 is the reason for the generation stamp and the verify line: nothing printed is a legal record, and the hospital's paper chart remains that. Printing patient data is also a data-protection question, and worklists rather than records is the answer to it.
- There is no existing print stylesheet, so this is greenfield. The theme is built on semantic tokens with a dark mode and a teal brand re-tint, and none of that belongs on paper: print rules should force a light, high-contrast presentation rather than inherit the screen theme.
- Table styling already exists as a vocabulary in `frontend/src/design.ts`, which is the right thing to build the sheets from. Do not invent a second table style for print.
- The sheets are the practical answer to the ward's shared wifi and to a tablet carried between rooms, and they are also the most likely thing to be used in the study. Consider printing one during a study session and asking the participant to work from it.
- A four-clinical-view segmented control plus print buttons on a tablet is a lot of chrome. If the sheet printing crowds the header, that is the point to reconsider the workspace navigation rather than to add a second menu.
