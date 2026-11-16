# 19: Patient search and per-Patient history

**What to build:** A Clinical user can find a Patient by name or contact number, and open one Patient's Encounters over time with each visit's Urgency Level and Final Decision. This is the proposal's "searchable patient history" enhanced function, which the build did not have.

**Blocked by:** none.

**Status:** done

- [ ] `GET /api/clinical/patients?q=&limit=` returns Patients whose name or contact number matches the query, capped by `limit` following the existing `GET /encounters` pattern.
- [ ] A blank or whitespace-only query returns an empty list, not the whole Patient table, so the view cannot be used as a bulk export.
- [ ] `GET /api/clinical/patients/{patient_id}/encounters` returns that Patient's Encounters, each rendered through the existing encounter-response helper.
- [ ] Encounters carrying an `evaluation_run_id` are excluded from Patient history, as the Queue already excludes them, so corpus rows never appear as visits.
- [ ] An unknown Patient id returns a 404, consistent with the existing encounter lookup.
- [ ] Both routes require the Clinical role; an Administrator is refused, as with every other clinical route.
- [ ] The frontend gains a Patient-history view reachable from the Clinical workspace, with a search box and a results list, and an empty state both for "no query yet" and "no matches".
- [ ] The search box does not fire a request for an empty query, and the view shows the selected Patient's Encounters with their Urgency Level and Final Decision.
- [ ] Tests: partial-name match, contact-number match, blank query returns nothing, the limit is honoured, evaluation-run Encounters are excluded, and role separation holds.

## Notes

- Search is deliberately looser than identity resolution. `patients.py` documents that a name alone never *matches an identity* — that rule is untouched. Preserve the distinction in code comments so a future reader does not collapse search into identity matching.
- Model the new routes on `list_recent_encounters` in `routers/clinical.py` (limit-only, capped, no offset), and reuse the existing encounter-response helper rather than building a second renderer.
- Sub-views in the Clinical workspace are React state, not URL routes; add the view to the workspace's view union rather than to the router.
- Add the new endpoints to the README API table under ticket 21, not here.

## Comments

Resolved on `proposal-gaps`. Suite green: 435 passed.
