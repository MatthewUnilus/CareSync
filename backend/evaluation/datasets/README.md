# Training data provenance

The Urgency classifier is trained from published, openly downloadable triage
data. `provenance.json` is the machine-readable record that the training step
reads and copies into the artefact, so the artefact never has to be trusted
about where it came from.

## Sources

| Source | Citation | Licence | Records |
| --- | --- | --- | --- |
| `hoseini-2022-triage-levels` | Hoseini, Benyamin (2022), Harvard Dataverse, V1.1, <https://doi.org/10.7910/DVN/7SOYC7> | CC0 1.0 Universal | 2,205 ED admissions with a three-level triage category, age and vital signs |
| `mimic-iv-demo-family-2.2` | Not used. PhysioNet, ODC-ODbL 1.0, <https://doi.org/10.13026/jzz5-vs76> | ODC-ODbL 1.0 | 222 triage rows, 2 of them ESI 4-5 |

The second entry is recorded under `considered_but_not_used`: it was the
preferred candidate because it is the only open source found that records pain,
a presenting complaint and acuity together, but its open subset cannot support a
three-class model and combining it with the first source put two label scales
and two missingness regimes into one intercept, which collapsed the predictions.
Recording the rejection is what makes the search auditable rather than a
silent choice.

## Fetching

Nothing from these sources is committed. The training command downloads each
file into `backend/data/datasets/` (already ignored), verifies its SHA-256
against `provenance.json`, and refuses to continue on a mismatch:

```powershell
cd backend
uv run python -m evaluation.train_classifier --fetch-only
```

## Known gaps

The used source records no pain level, no illness duration and no presenting
complaint. Those dimensions exist in the feature vector — the classifier is
trained and scored through the same vector the engine builds — but they are
constant in training, so the shipped artefact gives them a zero coefficient. The
artefact lists them under `training.constant_features`.

The credentialed primary dataset named in the spec is the intended fix: it
supplies the missing dimensions without a change to the pipeline. Adding it
means one adapter in `evaluation/triage_datasets.py` and one entry here.
