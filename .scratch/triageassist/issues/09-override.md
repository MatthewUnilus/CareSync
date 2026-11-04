# 09: Override with reason and audit

**What to build:** A Clinical user can disagree with a Machine Recommendation and set a different Final Decision, recording why. The Encounter repositions immediately, the card is flagged so human disagreement is visible at a glance, and the Machine Recommendation survives untouched so accuracy can still be measured afterwards.

**Blocked by:** 03.

**Status:** done

- [ ] A Clinical user sets a Final Decision different from the Machine Recommendation for an awaiting Encounter.
- [ ] The Override Reason is drawn from the fixed set defined in `CONTEXT.md`, and free text is accepted only when the reason is *other*.
- [ ] An Override submitted without a reason is refused.
- [ ] The Override records which user performed it.
- [ ] The Queue reorders immediately on Override, without a manual refresh.
- [ ] The card carries a flag whenever Final Decision differs from Machine Recommendation, distinguishable from the unclassified flag.
- [ ] The Machine Recommendation stored on the Triage Assessment is unchanged by the Override and remains readable afterwards.
- [ ] An Administrator is refused an Override.

## Comments

Resolved on `integration` (merge `7fa3ccb`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
