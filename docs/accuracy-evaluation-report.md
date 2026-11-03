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

Ground truth cannot come from the engine, so it cannot live on the Assessment.
It is supplied by a **labelled evaluation run manifest** written by the offline
harness (ticket 15). The Report joins each labelled case to the stored
Assessment by id and takes the Machine Recommendation from the row. A missing
Assessment is reported as missing, never silently dropped.

If no labelled run is available, the Report shows an explicit empty state. It
does not show `0`: that would be a claim, not a measurement. Ticket 06's shipped
classifier is at or below the majority baseline on the data it was trained on,
and nothing in this view is smoothed, rounded up, or tuned to hide that.

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
  Low, divided by every case whose truth was not Low. This is under-triage, and
  it is where a missed urgent case appears.

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

Mode is recorded in the manifest (`mode`) and displayed on the view. It is never
inferred from Assessment rows: a stored Assessment records `unclassified`, but
it does not record whether a fallback provider was configured for the run. A
manifest is rejected if a `fallback-disabled` run claims a fallback or
unclassified case, or if a case is marked unclassified without the fallback
having run.

The primary, reproducible run is `fallback-disabled`; it is ordered first. A
separate `fallback-enabled` run supplies coverage.

## Manifest contract

The configured path is `TRIAGEASSIST_ACCURACY_RUN_PATH`; the default is
`backend/evaluation/results/accuracy-evaluation.json`. The file is optional. If
it is absent, the Report is in its empty state. If it exists but is invalid, the
API refuses it rather than showing a partial score.

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

- `schema_version` is `1`;
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
    run_id, mode, dataset, engine_artefact,
    ground_truth: {name, version, citation, document},
    sample: {labelled_cases, resolved_assessments,
             missing_assessments, inconsistent_recommendations},
    confusion_matrix: [{machine_recommendation, ground_truth, assessments}],
    levels: [{urgency_level, ground_truth_count, predicted_count, correct,
              precision, recall}],
    total, correct, accuracy,
    false_high_priority: {count, denominator, rate},
    false_low_priority: {count, denominator, rate},
    fallback: {enabled, fallback_used, unclassified, coverage,
               unclassified_rate}
  }],
  overrides: {
    assessments, overridden_assessments, overrides, rate,
    reasons: [{reason, overrides, share}]
  }
}
```

## What ticket 15 must produce

The harness must write the manifest above. Crucially, every case must carry the
id of a **stored** Triage Assessment, because the Report reads the Machine
Recommendation from the row. The harness can satisfy that by persisting its
rubric-labelled synthetic Encounters and Assessments before writing the
manifest, or by scoring Assessments already stored. It must also record:

- the run `mode`, explicitly;
- the ground-truth source name, version and citation;
- the dataset and engine artefact provenance;
- `fallback_used` per case, so coverage is measured rather than guessed;
- a separate fallback-enabled run if coverage is to be shown.

The whole-pipeline and cross-validated results stay separate: only a run whose
cases resolve to stored Assessments appears here.
