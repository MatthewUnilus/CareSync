# 06: Trained classifier replaces the stub

**What to build:** The stub behind the Prioritization Engine boundary is replaced by a supervised classifier trained on a published triage dataset. It consumes a structured feature vector — recognised Symptom Groups, pain level, illness duration, age, and the four vitals — and not raw text. The recommendation the Clinical user sees now comes from the model.

**Blocked by:** 05.

**Status:** done

- [ ] The feature vector is built from recognised Symptom Groups, pain level, illness duration, age, and the four vitals, and contains no raw complaint text.
- [ ] The classifier is trained on a published, citable dataset, with the dataset and its provenance recorded alongside the trained artefact.
- [ ] Cross-validated scores for the trained classifier are produced and recorded with the artefact.
- [ ] The engine boundary keeps its existing shape: still pure, still returning exactly one Urgency Level, still callable with constructed inputs and no database.
- [ ] An Encounter taken through intake receives a recommendation produced by the classifier rather than the stub.
- [ ] The same constructed inputs always produce the same Machine Recommendation.

## Comments

Resolved on `integration` (merge `2bcd13e`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
