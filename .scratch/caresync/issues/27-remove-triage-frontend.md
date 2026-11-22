# 27: Remove the triage surfaces from the frontend

**What to build:** The screens that show urgency, a queue or an override are gone, and what is left is a client that can register a patient, open a visit, chart vitals, search, read a history and show the audit log. The intake validation defect gets fixed here, because the ward forms are about to copy whatever pattern is in that file.

**Blocked by:** 26 (the API shapes it mirrors must be final first).

**Status:** ready-for-agent

- [ ] `QueueBoard.tsx` (791 lines) is deleted, along with its three action components.
- [ ] `TriageKitGallery.tsx` (460 lines) and the entire `frontend/components/triage/` directory are deleted, and the `/triage-kit` branch is removed from `App.tsx`. That gallery is the only consumer of the kit, so nothing else breaks.
- [ ] `api.ts` loses every triage type and method: `UrgencyLevel`, `OverrideReason`, `AssessmentSnapshot`, `OverrideRecord`, `RedFlag`, `Assessment`, `QueueEntry`, `QueueSnapshot`, `AdministratorQueueEntry`, `AdministratorQueueSnapshot`, `UrgencyLevelCount`, `UrgencyDistributionReport`, and the `queue`, `overrideReasons`, `overrideFinalDecision`, `reassessEncounter` and `administratorQueue` methods.
- [ ] `queueDisplay.ts` keeps its generic half, being `SEX_OPTIONS`, `sexLabel`, `formatInstant`, `formatWaiting`, `formatWaitingLong`, `formatArrival` and `formatArrivalFull`, and loses the urgency class maps, the wait bands and `abnormalVitalFields`.
- [ ] `PatientHistoryScreen.tsx` loses the urgency border, the badge and the machine-versus-final difference note, and keeps search and the encounter list.
- [ ] `IntakeScreen.tsx` loses the re-assessment form, its state, its handler and its render block, and keeps registration, the encounter form and the recent list.
- [ ] `AdministratorDashboard.tsx` loses the awaiting-queue table and keeps the reports mount and the audit log card.
- [ ] `brand.tsx` is reworked. `LogoMark` is three bands in rose, yellow and lime, which is the urgency colour scheme rendered as a logo.
- [ ] `platform.ts` and `platform.test.ts` lose the queue arm of `ClinicalView` and the assertion that web lands on `"queue"`.
- [ ] **The intake validation defect is fixed.** At `IntakeScreen.tsx:118-121`, age is reported through `painLevel`, sex through `durationHours`, phone through `temperatureC`, and the full-name error is overwritten by the complaint error on the next line, so it can never be seen. The duplicate block at 170-176 goes with the re-assessment form.
- [ ] `npm run build:web` type-checks and the surviving tests pass.

## Notes

- Order: `api.ts` first, because every screen imports from it and its types are what the compiler will use to find the dead call sites. Deleting the screens first leaves a monolith full of unresolved references.
- `api.ts` is 557 lines with no per-domain split. Splitting it is out of scope here; prune it in place and leave the split for whenever the ward work makes one file awkward.
- The kit's general members (`button`, `card`, `confirmation-modal`, `connection-banner`, `labeled-input`, `queue-state`, `vital-signs-card`) are triage-themed in props and copy only. They go with the directory because nothing in the product imports them, and the product screens use `components/base/` instead. Copy a pattern if a ward screen wants one; do not keep the directory alive for it.
- `TappableInfo` in `components/base/utils/` has an Override example in its docstring only. No code coupling, but the example should change with the vocabulary.
- The `abnormalVitalFields` helper is deleted here and its behaviour returns in ticket 30 against the Observation chart, built from the same cited thresholds rather than a second table.
