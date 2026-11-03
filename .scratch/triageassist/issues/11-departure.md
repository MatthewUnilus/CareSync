# 11: Departure

**What to build:** A Clinical user Departs an Encounter from the Queue when the visit ends, and the system records the departure instant. The Encounter leaves the awaiting board and nothing else.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] A Clinical user Departs an awaiting Encounter, and it disappears from the awaiting board immediately.
- [ ] Every departed Encounter has a departure instant, recorded automatically at the moment of Departure.
- [ ] Departure is available only as a manual action; no Encounter is ever removed on the system's own initiative.
- [ ] The only two conditions an Encounter can hold are awaiting and departed.
- [ ] A departed Encounter remains readable afterwards, with its Patient, Triage Assessments, and Overrides intact.
- [ ] A departed Encounter can no longer be Overridden or Re-assessed.
