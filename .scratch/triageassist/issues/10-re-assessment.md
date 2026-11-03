# 10: Re-assessment

**What to build:** A Clinical user explicitly Re-assesses an Encounter already in the Queue. That produces a fresh Triage Assessment with its own Machine Recommendation, and the most recent assessment's Final Decision governs where the Encounter now sits. Earlier assessments are retained, so the Encounter's history is complete.

**Blocked by:** 09.

**Status:** ready-for-agent

- [ ] Re-assessment is available only as an explicit action by a Clinical user, and never happens automatically or on a schedule.
- [ ] Re-assessment creates a new Triage Assessment for the same Encounter, with its own captured inputs and its own Machine Recommendation.
- [ ] The Encounter's position in the Queue is governed by the most recent Triage Assessment's Final Decision, not by any earlier one.
- [ ] Earlier Triage Assessments remain stored and readable after a Re-assessment.
- [ ] Each assessment records which assessment it superseded, so the sequence is reconstructable.
- [ ] The board card reflects the most recent assessment's decision, flags, and recognised Symptom Groups.
- [ ] Nothing in the Queue reorders unless a Re-assessment or an Override was explicitly performed.
