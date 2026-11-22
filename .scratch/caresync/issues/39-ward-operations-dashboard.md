# 39: Ward operations dashboard

**What to build:** The administrator role has something real to look at, and it is read-only. Occupancy and length of stay, the proportion of doses recorded on time, the count of results still awaiting review, and tasks completed against tasks raised. The audit log stays as it is. This keeps oversight separate from care, which is the reason the role exists.

**Blocked by:** 31, 33, 35, 36 (every figure is counted from what those tickets record).

**Status:** ready-for-agent

- [ ] The ward census: how many patients are on the ward, by location and in total.
- [ ] Length of stay: the distribution across the current patients, and the average over a period.
- [ ] Doses recorded on time, against doses recorded late and doses not given, as a proportion over a period.
- [ ] Results still awaiting review, as a count, and how long the oldest has waited.
- [ ] Tasks completed against tasks raised over a period.
- [ ] Every figure is derived at read time from stored rows and never stored. A test asserts the reads write nothing.
- [ ] An administrator is refused every clinical route, and the existing refusal test's case list grows to cover the new ward routes.
- [ ] The dashboard is added in the style the existing reports use: a card per figure group, tables through the shared table vocabulary, and a caption stating what the figure counts.
- [ ] The audit log card is untouched and still works, and its action list reflects the enlarged action set from ticket 24.
- [ ] Tests: each figure counts what it says it counts on constructed rows; the reads write nothing; an administrator is refused every clinical ward route.

## Notes

- The three of these that answer the nurse's problems directly are doses on time, results awaiting review and tasks completed. Occupancy and length of stay are the ward's standing measures and belong on the same screen, but the other three are the ones to foreground.
- Keep the questions the figures answer answerable in one sentence each, and put that sentence on the screen. A count of results awaiting review with no period attached is a number nobody can act on.
- The reports discipline is to derive on demand from stored rows and never to store a snapshot, so these cannot be cached overnight or computed by a scheduled job. That also means they are cheap to add and cannot drift.
- The study's comparison baseline may want one of these figures from before the system existed. If the hospital can supply it, note it here: a before-and-after on documentation lag is a stronger claim than either figure alone.
- The administrator role and the Clinical role are the only two, and this ticket does not add a third. If a ward manager wants a view between the two, that is a scope question to raise rather than absorb.
