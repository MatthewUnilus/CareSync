# 15: Offline evaluation harness

**What to build:** The reproducible evidence run behind the dissertation. It scores the Prioritization Engine offline against labelled data in two distinct ways — cross-validated scoring on the published dataset, and whole-pipeline evaluation on rubric-labelled synthetic Encounters — reported separately, with the fallback disabled in the primary run and its coverage reported on its own.

**Blocked by:** 04, 08.

**Status:** ready-for-agent

- [ ] The harness scores the engine against labelled data through the pure engine boundary, with no database involved.
- [ ] A cross-validated run on the published dataset produces per-level precision and recall plus the confusion matrix.
- [ ] A whole-pipeline run on rubric-labelled synthetic Encounters exercises intake inputs through to Machine Recommendation, and is reported separately from the cross-validated score.
- [ ] The primary accuracy run executes with the fallback path disabled, so the reported numbers are reproducible.
- [ ] Fallback coverage rate is reported as its own statistic from a separate run with the fallback enabled.
- [ ] Running the harness twice over the same fixed inputs produces identical figures.
- [ ] The harness records which dataset, which rubric version, and which engine artefact produced each result, and its output is consumable by the Accuracy Evaluation Report.
