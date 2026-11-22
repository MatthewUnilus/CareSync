# 25: Remove the accuracy evaluation and the triage reports

**What to build:** The Accuracy Evaluation Report and the evaluation apparatus behind it are gone, and the administrator surface keeps only the reporting that describes a visit. This is the first dent in the demolition, and it is separated from ticket 26 because the two together are far more than one context window can carry.

**Blocked by:** 24 (the label map must stop being a client concern first).

**Status:** ready-for-agent

- [ ] The whole `backend/evaluation/` tree is deleted: the harness, the generator, the rubric, the labeller, the corpus builder, the materialisation, the training pipeline, the dataset loaders, the artefact versioning, `RUBRIC.md`, the provenance and dataset READMEs, and the results README.
- [ ] `backend/evaluation/corpus/esi-v4-rubric-v1.0.0.json` (1,525 lines) and `backend/evaluation/results/accuracy-evaluation-v1.0.0.json` (1,100 lines) are deleted.
- [ ] `backend/models/urgency-classifier-v1.1.0.json` is deleted and the directory is removed.
- [ ] `backend/app/accuracy.py` (1,587 lines) is deleted.
- [ ] `GET /api/administrator/reports/accuracy-evaluation` and its response builder are deleted, and the route is refused as unknown rather than served empty.
- [ ] `GET /api/administrator/reports/priority-distribution` is deleted. It counts Urgency Levels, which no longer exist.
- [ ] `GET /api/administrator/reports/performance` keeps the waiting figure, which is arrival to end of visit, and loses `assessed_at` and `processing_seconds`, which measure the engine rather than the visit.
- [ ] `GET /api/administrator/reports/daily-queue` is renamed to describe a day's visits and admissions, and stops filtering on `evaluation_run_id`.
- [ ] The `accuracy_run_path` setting is deleted from `backend/app/config.py`.
- [ ] The 28 tests in `test_accuracy_report.py`, the 18 in `test_evaluation_harness.py`, the 8 in `test_evaluation_corpus.py`, the 5 in `test_evaluation_materialisation.py`, the 16 in `test_ground_truth_rubric.py`, the 6 in `test_training_pipeline.py` and the 8 in `test_triage_datasets.py` are deleted with the modules they cover.
- [ ] The 9 triage tests in `test_activity_reports.py` are deleted; the 2 covering the day's volume and the half-open day boundary survive.
- [ ] The client's `AccuracyRunView`, `OverrideFigures` and `AccuracyEvaluation` sections are deleted from `AdministratorReports.tsx`, and `api.ts` loses the `accuracyEvaluationReport` and `priorityDistributionReport` methods and their types.
- [ ] The surviving suite passes, and `npm run build:web` type-checks.

## Notes

- `app/accuracy.py` is the largest single module in the backend and the only consumer of `accuracy_run_path`, so deleting it and the setting is one change.
- `reports.py` is roughly half pure Encounter workflow and half assessment reads. `utc_day_bounds` and the volume/throughput counting are the workflow half and are what ticket 26 leaves standing. Read it before cutting.
- The evaluation-run concept exists only for corpus rows. Nothing else creates `evaluation_run_id`, so once the corpus is gone the column is dead and ticket 26 drops it along with the four surviving call sites that filter on it.
- The dissertation will want to cite what the engine scored. That is what ticket 22's tag is for, and ADR 0014 is where the numbers and the reason for the removal belong, not in a surviving artefact.
- If the four removed documents (`accuracy-evaluation-report.md` and its siblings) are still needed as sources for a chapter, keep them under a clearly named archive directory rather than deleting them here. Ticket 26 makes that call once, not twice.
