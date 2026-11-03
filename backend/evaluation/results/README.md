# Accuracy evaluation results

`accuracy-evaluation-v1.0.0.json` is the versioned artefact produced by the
offline evaluation harness. It is committed so the Accuracy Evaluation Report
can read it without re-running cross-validation, and so a dissertation examiner
can inspect the exact figures behind the report.

## Producing it

From `backend/`:

```powershell
uv run python -m evaluation.harness
```

The command downloads the published training datasets if they are not cached
(verifying each file's SHA-256 against `evaluation/datasets/provenance.json`),
then writes the artefact. There is no timestamp and no sampling: running it
twice over the same fixed inputs produces byte-identical output.

## Shape

| Key | Meaning |
| --- | --- |
| `schema_version` | Artefact schema version. |
| `harness_version` | Version of the code that produced the run; a change in scoring or procedure bumps the file name. |
| `class_order` | `["High", "Medium", "Low"]`. Rows and columns of every matrix and the key order of every `per_class` object. |
| `metric_definitions` | Plain-English definition of every metric, so a report never has to guess. |
| `engine` | The classifier artefact identity: version, path, SHA-256, model family, vocabulary version, training datasets and known limitations. |
| `runs` | Three independent runs, below. |

Each run carries `id`, `mode` (`cross_validated` or `pipeline`), `fallback`
(`disabled` or `enabled`), `dataset`, `ground_truth`, `procedure`,
`engine_artefact` and `metrics`.

`metrics` always contains:

- `encounter_count`
- `accuracy`
- `macro_f1`
- `majority_baseline` — `class`, `accuracy`, `model_minus_baseline`,
  `beats_baseline`. `beats_baseline` is true only when the model is strictly
  better than always predicting the commonest ground-truth class.
- `confusion_matrix` — `labels` and `rows`; rows are ground truth, columns are
  Machine Recommendation.
- `per_class` — `High`, `Medium`, `Low`, each with `precision`, `recall`, `f1`
  and `support`. Precision and recall use zero-division-as-zero.
- `false_high_priority` and `false_low_priority` — `count`, `denominator` and
  `rate`. False High is the share of ground-truth Medium/Low Encounters
  recommended High. False Low is the share of ground-truth High Encounters
  recommended Medium or Low.

### `cross_validated`

Stratified 5-fold cross-validation of the learned classifier on the published
training dataset. The model is refit inside each fold, so this is not a
resubstitution score. The published source supplies its own three-level triage
category; `ground_truth.rubric_version` is therefore `null`, and the run says
so. `matches_recorded_artefact` is true when the figures reproduce the
`cross_validation` block already stored in `models/urgency-classifier-v1.0.0.json`.

`safety_layer` holds the same out-of-fold predictions with the deterministic
red-flag layer applied. It is a variant, not the primary cross-validated score.

### `pipeline`

The whole pipeline on `evaluation/corpus/esi-v4-rubric-v1.0.0.json`: complaint
text → Symptom Group recognition → classifier → safety layer → Machine
Recommendation. Ground truth comes only from the independent ESI v4 rubric.
`predictions` lists every Encounter's ground truth, Machine Recommendation,
recognised groups and fallback flags.

### `pipeline_fallback_enabled`

The same pipeline with the fallback enabled. It is separate on purpose: its
`coverage` object reports `fallback_used`, `rate`, `unclassified` and
`unclassified_rate`. The primary `pipeline` run has no `coverage` key. Do not
fold this run's accuracy into the primary score; show coverage as its own
statistic.

## What the current run says

- Cross-validated accuracy is **0.422**, against a majority baseline of
  **0.533**. The model is below the baseline. This is expected: the training
  source records no complaint, pain level or illness duration.
- Whole-pipeline accuracy is **0.593**, against a majority baseline of
  **0.556**. It barely beats always predicting High, and never predicts Medium.
- Fallback coverage is **0.370** (10 of 27 Encounters). No provider is
  configured offline, so all 10 are flagged unclassified.

The report must show these comparisons, not just the accuracy figure.

## How the Accuracy Evaluation Report consumes it

The Report and the harness share `evaluation/artefact.py`, which owns the schema
version, the harness version and the file name
`accuracy-evaluation-<version>.json`. The Report's default path is that file
under this directory, so the committed artefact above populates the flagship
view with no configuration.

`TRIAGEASSIST_ACCURACY_RUN_PATH` is the explicit override. Precedence is:

1. the explicit path, whose shape (harness artefact or legacy per-case
   manifest) is detected;
2. `accuracy-evaluation.json` in this directory, if an environment still writes
   the live per-case manifest;
3. this versioned artefact.

From a harness run the Report copies `metrics.confusion_matrix`,
`metrics.per_class`, both `false_priority` objects, `metrics.accuracy`,
`metrics.macro_f1`, `metrics.majority_baseline`, `metrics.encounter_count` and
the optional `coverage`. It transposes the matrix from ground-truth rows into
its own `(Machine Recommendation, ground truth)` cells and shows
`encounter_count` as the sample size. Nothing here is recomputed from the
database, so the evidence stays reproducible offline.

`cross_validated` is presented first and labelled primary. Its
`majority_baseline.model_minus_baseline` is shown with its sign, including when
it is negative. `pipeline_fallback_enabled.coverage` is shown as its own
statistic, never folded into accuracy. Override rate and reason distribution
continue to come from stored Assessments and are unaffected by this file.

The Report's required run keys are pinned by a test against this document. A
new run or metric field fails that test until the consumer deliberately reads
it.
