# The Accuracy Evaluation Report

The flagship reporting view. It compares the Prioritization Engine's **Machine
Recommendation** with an independent **ground-truth Urgency Level** and shows
where staff disagreed with the engine. It is read-only: computing it writes no
row and performs no clinical action.

Route: `GET /api/administrator/reports/accuracy-evaluation` · Administrator only.

## Why it is built this way

Two records are deliberately kept apart in the domain (`CONTEXT.md`):

- the **Machine Recommendation** on a Triage Assessment is immutable;
- the **Final Decision** is what an Override moves.

The Report reads `machine_recommendation` and never `final_decision`. An
Override therefore appends its record and changes the Queue, but it cannot move
a single cell of the confusion matrix, a precision or recall figure, or either
false-priority rate. The tests assert that property directly.

Ground truth never comes from the engine. It is stored in its own nullable
`ground_truth_level` column on an evaluation-run Assessment, beside — never in —
`machine_recommendation` and `final_decision`; a live Assessment leaves it null.
The Report accepts runs from three sources, described under **Where the runs
come from** below: stored evaluation-run Assessments (preferred when present),
the offline harness's versioned artefact, or a legacy per-case manifest whose
cases each name a stored Assessment.

If no labelled run is available, the Report shows an explicit empty state. It
does not show `0`: that would be a claim, not a measurement. Ticket 06's shipped
classifier is at or below the majority baseline on the data it was trained on,
and nothing in this view is smoothed, rounded up, or tuned to hide that.

## Where the runs come from

The Report has four run sources and a fixed precedence. It never merges them
into one score. Every run payload carries its `source` (`evaluation`,
`assessments` or `harness`), and the view labels it.

1. **A stored evaluation run.** When any Assessment carries a
   `ground_truth_level` and its Encounter names an `evaluation_run_id`, the
   Report scores those stored rows and ignores the files below. The rows are
   materialised from the rubric-labelled corpus by the documented command
   (see `backend/evaluation/results/README.md`), each Machine Recommendation
   produced by the real engine in its own column. This is the strongest
   evidence because the figures read stored, immutable records.
2. **An explicit path.** Otherwise `TRIAGEASSIST_ACCURACY_RUN_PATH` wins when
   it is set. The document's shape decides whether it is a legacy per-case
   manifest or a harness artefact.
3. **The legacy per-case manifest.** Otherwise, if
   `backend/evaluation/results/accuracy-evaluation.json` exists, it is read.
   Each case names a stored Assessment; the Report scores the immutable
   `machine_recommendation` from that row.
4. **The offline harness artefact.** Otherwise the Report reads
   `backend/evaluation/results/accuracy-evaluation-<version>.json`, the file the
   harness itself names from its version constant (`evaluation.artefact`). With
   the committed artefact this is the default, so the flagship view is populated
   with no manual configuration.

A missing file and no stored evaluation run is the explicit empty state. A file
that exists but is malformed, or whose `schema_version` is not the supported
version, is refused with the reason. Neither state is a `500` and neither is a
silent zero.

### What the harness artefact supplies

The offline harness is deliberately database-free. Its runs carry their own
confusion matrix, per-class precision and recall, false-priority rates,
majority baseline, macro F1 and sample size. Those figures are copied into the
Report as-is. They are the reproducible evidence and must not start depending
on database state.

The harness writes the matrix with **ground-truth rows and Machine
Recommendation columns**. The Report transposes it once into its own
`(machine_recommendation, ground_truth)` cells. The three runs appear in this
order:

- `cross_validated` — **primary**: stratified 5-fold cross-validation of the
  **composed engine** on the published dataset, 2205 Encounters. Its `metrics`
  are Machine Recommendations (out-of-fold classifier plus the red-flag safety
  layer), and its `majority_baseline` comparison is shown explicitly, including
  when the engine is below it. The classifier alone is surfaced beside it under
  `classifier_only` and labelled as a secondary diagnostic, **not** a Machine
  Recommendation.
- `pipeline` — the whole pipeline on the rubric-labelled synthetic corpus with
  the fallback disabled. Its 27 scored Encounters are shown as the sample size,
  so a small result cannot be mistaken for a large study.
- `pipeline_fallback_enabled` — the same pipeline with the fallback enabled.
  Its `coverage` is shown as its own statistic and is never folded into
  accuracy.

**Override rate and the Override Reason distribution still come from stored
Assessments.** They describe what actually happened in this database, not the
labelled sample, so they are unaffected by either run source.

## Figure definitions

All counts are per **Triage Assessment**, not per Encounter, so a Re-assessment
contributes its own decision.

The confusion matrix has one **row per Machine Recommendation** and one
**column per ground-truth Urgency Level**, in Queue order: High, Medium, Low.

For a level `L`:

- **Precision** = cases correctly called `L` / all cases the engine called `L`.
  A dash is shown when the engine never predicted `L`.
- **Recall** = cases correctly called `L` / all cases whose truth was `L`. A
  dash is shown when no case had that ground truth.

The two false-priority figures are one-vs-rest false-positive rates, and they
are never combined:

- **False High-Priority rate** = cases recommended **High** whose truth was not
  High, divided by every case whose truth was not High. This is over-triage.
- **False Low-Priority rate** = cases recommended **Low** whose truth was not
  Low, divided by every case whose truth was not Low. This is under-triage. A
  missed urgent case is one way it can occur, but it is not the denominator.

**High-class recall** = cases correctly recommended High / every case whose
truth was High. It is shown under its own name because its complement is the
missed-urgent-cases share; it is not False Low-Priority and the two are never
substituted for one another.

**Override rate** = stored Assessments carrying at least one Override, divided
by all stored Assessments. Overrides are counted outside the labelled sample,
because they describe where staff disagreed with the engine rather than how
accurate it was. The reason distribution counts Override rows by the fixed six
reasons, including reasons with zero occurrences.

**Fallback coverage** is only defined for a run with the fallback enabled:
resolved cases whose recommendation came from the fallback path, divided by all
resolved cases. **Unclassified rate** is the subset the fallback could not
classify. Neither enters the accuracy figure. A fallback-disabled run shows
coverage as "not exercised", not as zero.

## Run mode

Two mode facts are displayed separately and never inferred from Assessment
rows:

- the **run mode** (`cross_validated`, `pipeline`, or `assessment` for a legacy
  manifest);
- the **fallback mode** (`fallback-disabled` or `fallback-enabled`).

A legacy manifest is rejected if a `fallback-disabled` run claims a fallback or
unclassified case, or if a case is marked unclassified without the fallback
having run. Harness runs declare `fallback` explicitly and a fallback-enabled
run must carry its `coverage` object.

The cross-validated run is the primary reproducible score and is ordered first.
The whole-pipeline run is its own result; the fallback-enabled variant supplies
coverage as a separate statistic.

## Harness artefact contract

The producer and consumer share one naming module,
`backend/evaluation/artefact.py`: it defines the artefact schema version, the
harness version and the file name `accuracy-evaluation-<version>.json`. Bumping
the harness version therefore moves the default path with it; there is no second
place to edit.

`backend/evaluation/results/README.md` is the producer's contract for every run
and metric it writes. The consumer reads these run-level fields:

```text
id, mode, fallback, dataset, ground_truth, engine_artefact, metrics
```

plus the optional `coverage`, `predictions`, `description`, `procedure` and
`classifier_only`. `classifier_only` carries its own `description` and a full
`metrics` object; it is a secondary diagnostic, never a Machine Recommendation.
Inside `metrics` it reads:

```text
encounter_count, accuracy, macro_f1, majority_baseline,
confusion_matrix, per_class, false_high_priority, false_low_priority,
high_class_recall
```

A test pins both key sets against the committed artefact. If the harness adds a
run or metric field, that test fails until the consumer's contract is widened
deliberately — the two schemas cannot drift again without a red test.

The loader enforces:

- `schema_version` is `1`, in both document forms;
- run ids are unique;
- `fallback` is `disabled` or `enabled`;
- `metrics.encounter_count` is positive and equals the confusion-matrix sum and
  the number of `predictions` when that key is present;
- `confusion_matrix.labels` cover High, Medium and Low, and each row matches the
  label order;
- every `per_class` support and diagonal count agrees with the matrix;
- a fallback-enabled run's `coverage` matches its own counts.

If any check fails, the Report returns an explicit refusal state with the
reason. It does not return a partial score.

## Legacy manifest contract

The old per-case form remains supported for live, assessment-derived runs. It is
the document read at step 2 of the precedence above.

```json
{
  "schema_version": 1,
  "runs": [
    {
      "run_id": "pipeline-fallback-disabled",
      "mode": "fallback-disabled",
      "dataset": "ESI v4 rubric corpus v1.0.0",
      "engine_artefact": "urgency-classifier-v1.0.0",
      "ground_truth": {
        "name": "ESI v4 rubric",
        "version": "esi-v4-rubric-v1.0.0",
        "citation": "Gilboy N, Tanabe P, Travers D, Rosenau AM. Emergency Severity Index (ESI): A Triage Tool for Emergency Department Care, Version 4. Implementation Handbook, 2012 Edition. AHRQ Publication No. 12-0014. Agency for Healthcare Research and Quality, Rockville, MD; November 2011.",
        "document": "evaluation/RUBRIC.md"
      },
      "cases": [
        {
          "assessment_id": 41,
          "ground_truth": "High",
          "machine_recommendation": "Medium",
          "fallback_used": false,
          "unclassified": false
        }
      ]
    }
  ]
}
```

Rules the loader enforces:

- each `run_id` is unique and non-empty;
- `mode` is exactly `fallback-disabled` or `fallback-enabled`;
- `ground_truth.name`, `.version` and `.citation` are present;
- each case names a positive `assessment_id` once, and a `ground_truth` of
  High, Medium or Low;
- `machine_recommendation` is optional. When present and different from the
  stored row, the stored row wins and the id is reported as inconsistent;
- `fallback_used` and `unclassified` default to `false`.

## Payload shape

```text
{
  available: boolean,
  empty_reason: string | null,
  runs: [{
    run_id, run_mode, source ("evaluation" | "assessments" | "harness"),
    primary,
    mode, dataset, engine_artefact,
    ground_truth: {name, version, citation, document},
    sample: {labelled_cases, resolved_assessments,
             missing_assessments, inconsistent_recommendations},
    confusion_matrix: [{machine_recommendation, ground_truth, assessments}],
    levels: [{urgency_level, ground_truth_count, predicted_count, correct,
              precision, recall}],
    total, correct, accuracy, macro_f1,
    majority_baseline: {majority_class, accuracy, model_minus_baseline,
                        beats_baseline} | null,
    false_high_priority: {count, denominator, rate},
    false_low_priority: {count, denominator, rate},
    high_class_recall: {count, denominator, rate},
    fallback: {enabled, fallback_used, unclassified, coverage,
               unclassified_rate},
    classifier_only: {description, total, correct, accuracy, macro_f1,
                      false_high_priority, false_low_priority,
                      high_class_recall} | null
  }],
  overrides: {
    assessments, overridden_assessments, overrides, rate,
    reasons: [{reason, overrides, share}]
  }
}
```

For a harness run, `sample.labelled_cases` and `sample.resolved_assessments`
are the number of scored Encounters and the view says so; there are no Assessment
ids to be missing or inconsistent. For a stored evaluation run they are the
number of labelled stored Assessments. For a legacy run they keep their
original meaning. `macro_f1` and `majority_baseline` are `null` only where the
source does not supply them; modern harness runs and stored evaluation runs
supply both.

## Assessment-derived runs

A stored evaluation run and a legacy manifest are both scored live: the Report
joins each case to its stored Assessment and reads the immutable
`machine_recommendation`. The evaluation run takes its ground truth from the
Assessment's `ground_truth_level` column; the legacy manifest takes it from the
case and reports any missing id or recommendation disagreement. The same
immutability property holds — an Override cannot move a matrix cell. A legacy
run whose cases do not resolve is the explicit empty state, not a zero.
