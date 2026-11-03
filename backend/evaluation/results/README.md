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
