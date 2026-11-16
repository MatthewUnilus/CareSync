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

## Materialising a stored evaluation run

Ticket 04 keeps ground truth distinct from Machine Recommendations in the
stored data, and ticket 14 requires the accuracy figures to be computed from
stored, immutable Triage Assessments. From `backend/`:

```powershell
uv run python -m evaluation.materialise
# rebuild an existing run id instead of refusing it:
uv run python -m evaluation.materialise --replace
# optional:
uv run python -m evaluation.materialise --run-id my-run --database-url sqlite:///./my.db
```

The command writes one Patient, one Encounter and one Triage Assessment per
corpus Encounter. Each Assessment is scored through the real
`app.assessments.create_triage_assessment` path, with the rubric label in its own
`ground_truth_level` column. The Encounter carries the run identifier.
Evaluation rows are excluded from the Queue and from the activity and
performance Reports. When any stored evaluation run exists, the Accuracy
Evaluation Report scores those rows and labels the run source `evaluation`;
otherwise it falls back to this artefact as before.

There is no migration tool yet, so a local database created before the
`ground_truth_level` and `evaluation_run_id` columns existed has to be deleted
and reseeded (README, "There is no migration tool yet").

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
  `rate`, both one-vs-rest false-positive rates. False High is recommended High
  with a non-High truth, over every non-High truth (over-triage). False Low is
  recommended Low with a non-Low truth, over every non-Low truth (under-triage).
  A missed High is one way a False Low can occur, but it is not the denominator.
- `high_class_recall` — `count`, `denominator` and `rate` for the High class.
  This is the missed-urgent-cases signal: its complement is the share of
  ground-truth High Encounters the engine did not recommend High.

### `cross_validated`

Stratified 5-fold cross-validation of the **composed engine** on the published
training dataset. The model is refit inside each fold, out-of-fold predictions
then pass through the deterministic red-flag safety layer, and the resulting
Machine Recommendation is what `metrics` scores. The published source supplies
its own three-level triage category; `ground_truth.rubric_version` is therefore
`null`, and the run says so.

`classifier_only` holds the same out-of-fold predictions **without** the safety
layer. It is a secondary diagnostic, explicitly not a Machine Recommendation;
its `matches_recorded_artefact` is true when those figures reproduce the
`cross_validation` block already stored in
`models/urgency-classifier-v1.1.0.json`. Accuracy can be lower for the composed
engine because the safety layer may over-triage; that is the engine's real
behaviour and is shown, not hidden.

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

- Composed cross-validated accuracy is **0.342**, against a majority baseline
  of **0.533**. The engine is below the baseline, and worse than its
  classifier-only variant (**0.422**): the safety layer raises cases that the
  published labels did not call High, so it over-triages on this dataset. This
  is reported as it is, not rounded away. The training source records no
  complaint, pain level or illness duration.
- Whole-pipeline accuracy is **0.593**, against a majority baseline of
  **0.556**. It barely beats always predicting High, and never predicts Medium.
  High-class recall is **0.600** (9 of 15); False Low-Priority is **0.500** (10
  of 20 non-Low truths).
- Fallback coverage is **0.370** (10 of 27 Encounters). No provider is
  configured offline, so all 10 are flagged unclassified.

The report must show these comparisons, not just the accuracy figure.

## How the Accuracy Evaluation Report consumes it

The Report and the harness share `evaluation/artefact.py`, which owns the schema
version, the harness version and the file name
`accuracy-evaluation-<version>.json`. The committed artefact above populates the
flagship view when no stored evaluation run exists, with no configuration.

Precedence is:

1. a **stored evaluation run**, when `evaluation.materialise` has written one:
   the Report scores the stored, immutable Assessments and labels the run
   source `evaluation`;
2. `TRIAGEASSIST_ACCURACY_RUN_PATH`, whose shape (harness artefact or legacy
   per-case manifest) is detected;
3. `accuracy-evaluation.json` in this directory, if an environment still writes
   the live per-case manifest;
4. this versioned artefact.

From a harness run the Report copies `metrics.confusion_matrix`,
`metrics.per_class`, both `false_priority` objects, `metrics.high_class_recall`,
`metrics.accuracy`, `metrics.macro_f1`, `metrics.majority_baseline`,
`metrics.encounter_count` and the optional `coverage`. It also surfaces the
`classifier_only` variant, labelled as a secondary diagnostic rather than a
Machine Recommendation. It transposes the matrix from ground-truth rows into
its own `(Machine Recommendation, ground truth)` cells and shows
`encounter_count` as the sample size. Nothing here is recomputed from the
database, so the evidence stays reproducible offline. A stored evaluation run
is the opposite by design: its scores are recomputed from the immutable rows.

`cross_validated` is presented first and labelled primary. Its
`majority_baseline.model_minus_baseline` is shown with its sign, including when
it is negative. `pipeline_fallback_enabled.coverage` is shown as its own
statistic, never folded into accuracy. Override rate and reason distribution
continue to come from stored Assessments and are unaffected by this file.

The Report's required run keys are pinned by a test against this document. A
new run or metric field fails that test until the consumer deliberately reads
it.
