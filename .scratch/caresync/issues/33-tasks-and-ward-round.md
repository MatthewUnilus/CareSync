# 33: Tasks and the ward round

**What to build:** The instructions given on a ward round become tasks a nurse can work, and every nurse has one list across all their patients rather than a different list per patient. This is the third of the nurse's three problems: tracking treatment instructions and outstanding work across several patients at once.

**Blocked by:** 32 (a ward round entry is a Nursing Note, and it is what raises the Tasks).

**Status:** ready-for-agent

- [ ] A new `tasks` table records the Admission, a description, an optional due time, an optional assignee, a state and the author.
- [ ] A Task can be raised by hand from a patient's page.
- [ ] A Task can be raised from a Ward Round Entry, and a Task raised that way belongs to the patient on that note.
- [ ] A round entry can raise several Tasks in one go, because a round gives several instructions in one conversation.
- [ ] A Task is open or done, and marking it done records who and when.
- [ ] A Task can carry an optional due time, and work with a deadline is distinguishable in the list from work without one.
- [ ] A Task can be assigned or left unassigned, so both an assigned caseload and a shared ward work.
- [ ] A cross-patient task list shows open Tasks across all the patients on the ward, filterable to the ones assigned to the signed-in user.
- [ ] Overdue Tasks are marked in the list. Nothing acts on them.
- [ ] The ward board's open Task count starts returning a real figure, replacing the zero that ticket 31 stubbed.
- [ ] Raising a Task, marking one done and assigning one each write exactly one Audit Entry in the same transaction as the change.
- [ ] Tests: a round entry raises Tasks on the right patient; the cross-patient list covers several patients and filters to one assignee; marking done removes it from the open list and keeps it in the record; an overdue Task is marked; the list writes nothing.

## Notes

- Assignment is optional on purpose. A ward that assigns patients to nurses and a ward that works a shared list are both real, and forcing an assignee would break the second one.
- The "my patients" filter needs a notion of which patients are mine. If the hospital assigns patients to nurses, that is a field on the Admission; if they work a shared list, the filter is by Task assignee only. Ask before building either, and until then implement the assignee filter, which works in both worlds.
- Raising several Tasks from one round entry is what makes the ticket worth doing. A single-task-at-a-time form turns a five-instruction round into five form submissions.
- Overdue marking is display only, restating ADR 0010's rule for a second case. A task is not escalated, reassigned or closed by the system.
- `usePolling` at `frontend/src/usePolling.ts` is the existing pattern for a live view, at 5 seconds for operational data. A cross-patient list is operational data. Do not add a push mechanism: real-time messaging is out of scope.
