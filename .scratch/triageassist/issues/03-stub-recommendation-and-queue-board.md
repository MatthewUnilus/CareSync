# 03: Stub recommendation and the live Queue board

**What to build:** Completing intake produces a Machine Recommendation through the Prioritization Engine boundary and the Encounter joins the Queue, which is rendered as a working board. The engine boundary here is a documented deterministic stub; a later ticket replaces the stub with the real classifier without the Queue, the Assessment record, or the board changing shape.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] The Prioritization Engine is reachable as a pure function taking captured inputs and returning one Machine Recommendation, callable with constructed inputs and no database.
- [ ] Completing intake creates a Triage Assessment holding the captured inputs and the Machine Recommendation, and the recommendation is immutable once written.
- [ ] The Machine Recommendation is exactly one of High, Medium, or Low.
- [ ] The Queue is ordered by Urgency Level, with ties broken by arrival time so equally urgent Encounters are seen first-in-first-out.
- [ ] The board shows only Encounters that are still awaiting, and never a departed one.
- [ ] Each awaiting Encounter appears as a compact card showing Urgency Level, patient name, short complaint, and time waiting computed from arrival.
- [ ] A card expands to show full vitals, pain level, duration, notes, and the available actions.
- [ ] The board reflects a change in an Encounter's Final Decision without a manual refresh.
