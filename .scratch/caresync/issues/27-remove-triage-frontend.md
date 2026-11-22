# 27: Remove the triage surfaces from the frontend

**What to build:** The screens that show urgency, a queue or an override are gone, and what is left is a client that can register a patient, open and end a visit, search, read a history and show the audit log. Vital-sign charting lands with the Observation chart in ticket 30. The intake validation defect gets fixed here, because the ward forms are about to copy whatever pattern is in that file.

**Blocked by:** 26 (the API shapes it mirrors must be final first).

**Status:** done

- [x] `QueueBoard.tsx` (791 lines) is deleted, along with its three action components.
- [x] `TriageKitGallery.tsx` (460 lines) and the entire `frontend/components/triage/` directory are deleted, and the `/triage-kit` branch is removed from `App.tsx`. That gallery is the only consumer of the kit, so nothing else breaks.
- [x] `api.ts` loses every triage type and method: `UrgencyLevel`, `OverrideReason`, `AssessmentSnapshot`, `OverrideRecord`, `RedFlag`, `Assessment`, `QueueEntry`, `QueueSnapshot`, `AdministratorQueueEntry`, `AdministratorQueueSnapshot`, `UrgencyLevelCount`, `UrgencyDistributionReport`, and the `queue`, `overrideReasons`, `overrideFinalDecision`, `reassessEncounter` and `administratorQueue` methods.
- [x] `queueDisplay.ts` keeps its generic half, being `SEX_OPTIONS`, `sexLabel`, `formatInstant`, `formatWaiting`, `formatWaitingLong`, `formatArrival` and `formatArrivalFull`, and loses the urgency class maps, the wait bands and `abnormalVitalFields`.
- [x] `PatientHistoryScreen.tsx` loses the urgency border, the badge and the machine-versus-final difference note, and keeps search and the encounter list with a manual end-visit action for open visits.
- [x] `IntakeScreen.tsx` loses the re-assessment form, its state, its handler and its render block, and keeps registration, the encounter form and the recent list.
- [x] `AdministratorDashboard.tsx` loses the awaiting-queue table and keeps the reports mount and the audit log card.
- [x] `brand.tsx` is reworked to remove the existing rose, yellow and lime urgency bands; `LogoMark` uses a neutral non-triage mark.
- [x] `platform.ts` and `platform.test.ts` lose the queue arm of `ClinicalView` and the assertion that web lands on `"queue"`.
- [x] **The intake validation defect is fixed.** At `IntakeScreen.tsx:118-121`, age is reported through `painLevel`, sex through `durationHours`, phone through `temperatureC`, and the full-name error is overwritten by the complaint error on the next line, so it can never be seen. The duplicate block at 170-176 goes with the re-assessment form.
- [x] `npm run build:web` type-checks and the surviving tests pass.

## Backend integration (exposed by ticket 26)

Ticket 26 finishes the API shapes this ticket mirrors. The prune is not deletion alone: the end-of-visit route and three response fields change name, and two fields disappear, so the frontend has to follow or it reads a payload that is no longer sent.

- **End a visit through `POST /api/clinical/encounters/{id}/end`, not the departure route.** `api.ts`'s `departEncounter` (now `POST .../departure`) becomes an end-of-visit call against `/end`. It still takes no body: the server stamps the instant. An already-ended visit is a `409`; an unknown Encounter is a `404`.
- **`Encounter` is `id`, `arrived_at`, `ended_at`, `status`, `patient`, `reason_for_visit`.** `departed_at` becomes `ended_at`; `status` is `"open" | "ended"` rather than `"awaiting" | "departed"`; `reason_for_visit` carries what `intake` used to show.
- **`assessment` and `assessments` are gone from `Encounter`, and so is `intake`.** The standalone `Intake` type shrinks to the reason-only shape a visit accepts — `presenting_complaint` alone, matching `VisitReasonPayload` — and its vitals fields go. `openEncounter` keeps sending that reason under the `intake` wrapper, because vitals posted to a visit are refused with a `422` by `extra='forbid'`.
- **`AuditEntry` drops `assessment_id`.** `patient_id` and `encounter_id` survive as the only subject references, both still nullable.
- **`PerformanceEntry`'s instant is renamed `ended_at` too**, in step with the Encounter, since neither report field means "left a queue" any more.

`api.ts` is still pruned in place (see Notes); this section only names the surviving contract the pruned file has to land on.

## Notes

- Order: `api.ts` first, because every screen imports from it and its types are what the compiler will use to find the dead call sites. Deleting the screens first leaves a monolith full of unresolved references.
- `api.ts` is 557 lines with no per-domain split. Splitting it is out of scope here; prune it in place and leave the split for whenever the ward work makes one file awkward.
- The kit's general members (`button`, `card`, `confirmation-modal`, `connection-banner`, `labeled-input`, `queue-state`, `vital-signs-card`) are triage-themed in props and copy only. They go with the directory because nothing in the product imports them, and the product screens use `components/base/` instead. Copy a pattern if a ward screen wants one; do not keep the directory alive for it.
- `TappableInfo` in `components/base/utils/` has an Override example in its docstring only. No code coupling, but the example should change with the vocabulary.
- The `abnormalVitalFields` helper is deleted here and its behaviour returns in ticket 30 against the Observation chart, built from the same cited thresholds rather than a second table.
