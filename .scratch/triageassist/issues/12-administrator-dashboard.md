# 12: Administrator dashboard and dense Queue table

**What to build:** The Administrator-facing surface of the same client: the Queue as a dense table suited to surveying many Encounters at once, with no clinical actions available anywhere in it.

**Blocked by:** 03.

**Status:** done

- [ ] An Administrator logged in reaches a dashboard showing the awaiting Queue as a dense table.
- [ ] Each row shows Urgency Level, patient name, short complaint, time waiting, and whether the Final Decision differs from the Machine Recommendation.
- [ ] The table reflects an Override or a Departure without a manual refresh.
- [ ] No clinical action — registering a Patient, capturing intake, Overriding, Re-assessing, Departing — is available to an Administrator anywhere in the dashboard or its API calls.
- [ ] The dashboard and the mobile intake client are served from one client codebase, not two.
- [ ] A Clinical user and an Administrator reach their own surfaces after logging in, without a client-side-only gate deciding it.

## Comments

Resolved on `integration` (merge `ab97e5a`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
