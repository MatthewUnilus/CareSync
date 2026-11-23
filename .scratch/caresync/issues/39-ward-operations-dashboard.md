# 39: Ward operations dashboard

**What to build:** The administrator role has something real to look at, and it is read-only. Occupancy and length of stay, the proportion of doses recorded on time, the count of results still awaiting review, and tasks completed against tasks raised. The audit log stays as it is. This keeps oversight separate from care, which is the reason the role exists.

**Blocked by:** 31, 33, 35, 36 (every figure is counted from what those tickets record).

**Status:** done

- [x] The ward census: how many patients are on the ward, by location and in total.
- [x] Length of stay: the distribution across the current patients, and the average over a period.
- [x] Doses recorded on time, against doses recorded late and doses not given, as a proportion over a period.
- [x] Results still awaiting review, as a count, and how long the oldest has waited.
- [x] Tasks completed against tasks raised over a period.
- [x] Every figure is derived at read time from stored rows and never stored. A test asserts the reads write nothing.
- [x] An administrator is refused every clinical route, and the existing refusal test's case list grows to cover the new ward routes.
- [x] The dashboard is added in the style the existing reports use: a card per figure group, tables through the shared table vocabulary, and a caption stating what the figure counts.
- [x] The audit log card is untouched and still works, and its action list reflects the enlarged action set from ticket 24.
- [x] Tests: each figure counts what it says it counts on constructed rows; the reads write nothing; an administrator is refused every clinical ward route.

## Notes

- The three of these that answer the nurse's problems directly are doses on time, results awaiting review and tasks completed. Occupancy and length of stay are the ward's standing measures and belong on the same screen, but the other three are the ones to foreground.
- Keep the questions the figures answer answerable in one sentence each, and put that sentence on the screen. A count of results awaiting review with no period attached is a number nobody can act on.
- The reports discipline is to derive on demand from stored rows and never to store a snapshot, so these cannot be cached overnight or computed by a scheduled job. That also means they are cheap to add and cannot drift.
- The study's comparison baseline may want one of these figures from before the system existed. If the hospital can supply it, note it here: a before-and-after on documentation lag is a stronger claim than either figure alone.
- The administrator role and the Clinical role are the only two, and this ticket does not add a third. If a ward manager wants a view between the two, that is a scope question to raise rather than absorb.

## Comments

Built on `ticket/39-dashboard`, merged to `integration/caresync-ward-features`.
`npm run build:web` green, and the full API suite green (485 passed) including
the 5 new report tests in `backend/tests/test_ward_operations_reports.py`.

**Five figures, all derived on read.** `backend/app/reports.py` gains
`ward_census`, `length_of_stay`, `medication_timeliness`, `investigation_review`
and `task_completion`. Each recomputes from stored rows on every request and
stores nothing; a test asserts the reads add no rows. The figures are exposed
under `GET /api/administrator/reports/{ward-census,length-of-stay,
medication-timeliness,investigation-review,task-completion}`.

**The screen leads with the three that answer the nurse's problems.** Medication
timeliness, results awaiting review with the oldest wait, and task completion
are foregrounded on `frontend/src/WardOperationsDashboard.tsx`, with census and
length of stay on the same screen. Each group carries a one-sentence caption
stating exactly what it counts, so a figure is never a number with no period.

**Read-only, enforced at the API.** The dashboard is mounted in
`AdministratorDashboard.tsx` beside the existing Reports and Audit Log. Every
clinical ward route stays refused to an Administrator; the existing
router-derived refusal suites cover the live route list, so the new report
routes are the only Administrator surface and the ward routes remain
Clinical-only.

**Audit log untouched.** The log card still works and its action list reflects
the enlarged set from ticket 24, because the label is served from beside the
enum rather than copied into the client.

**A note on the study baseline.** The ticket asks that a before-and-after figure
be noted if the hospital can supply one. None is recorded here: the hospital has
not supplied a pre-system figure, so no baseline claim is made.

**Follow-up: medication timeliness coverage (2026-11-23).** The ticket asks that
"each figure counts what it says it counts on constructed rows". Four of the five
figures had that; medication timeliness was only exercised incidentally by the
reads-write-nothing test. Three tests were added to
`backend/tests/test_ward_operations_reports.py`: a constructed split of two
on-time doses, one late dose and one withheld dose asserts `on_time=2, late=1,
not_given=1, total=4, on_time_pct=50.0`; an empty window returns all zeros
rather than NaN; and a period test proves a dose recorded outside the window is
excluded (1 in a 7-day window, 2 in a 30-day one). The full suite is now 488
passing.
