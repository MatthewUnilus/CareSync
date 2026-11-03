# 08: Cached fallback for unrecognised complaints

**What to build:** A complaint that matches no Symptom Group still receives a recommendation instead of blocking the patient. The fallback is cached so identical wording always yields the identical result, times out to the safety layer alone, and is visibly flagged on the card so the Clinical user knows the recommendation needs their review.

**Blocked by:** 07.

**Status:** ready-for-agent

- [ ] A complaint matching no known Symptom Group still produces a Machine Recommendation rather than an error or an empty result.
- [ ] The same complaint text submitted twice returns the identical recommendation, with the second result served from cache.
- [ ] When the external fallback service is unavailable or exceeds its timeout, the recommendation is resolved from the safety layer alone and is marked as unclassified.
- [ ] An unclassified recommendation is visibly flagged on the Encounter's card, distinguishable from an override flag.
- [ ] A cached fallback result is stored against the complaint so it survives a process restart.
- [ ] Complaints that do match a Symptom Group never take the fallback path.
