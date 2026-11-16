# 0005 — Train the interim classifier on an open dataset that lacks the complaint

**Status:** Accepted (2026-11-03), explicitly interim

## Context

The spec names a credentialed published dataset as primary, an open dataset as the interim development set, and a smaller published set for independent validation. The credentialed dataset has a days-to-weeks lead time and had not been granted when the engine was built. The build could not wait.

Two open candidates were examined.

**MIMIC-IV-ED Demo 2.2** — open, ODC-ODbL, and the only one carrying pain level, complaint and ESI. Its open subset is 100 patients / 222 rows, of which **two** are ESI 4–5. A three-class model cannot be cross-validated on that, and combining it with another dataset put two label scales and two missingness regimes into one intercept, collapsing predictions to High.

**Hoseini (2022)**, Harvard Dataverse V1.1, `doi:10.7910/DVN/7SOYC7`, CC0 — 2,205 ED admissions with a three-level triage category, age, temperature, heart rate, systolic and diastolic pressure, and SpO2/FiO2. Downloaded, checksum-pinned, and used.

## Decision

Ship the classifier trained on Hoseini, and say plainly what it is.

The consequence is material: the dataset records **no pain level, no illness duration, no complaint and no respiratory rate**, so 52 of 58 features are constant in training and carry zero coefficient. The model is effectively a six-coefficient age-and-vitals model. Five-fold cross-validated accuracy is **0.422 against a 0.533 majority-class baseline**; macro F1 0.358.

(Respiratory rate joined the feature vector in ticket 18 and the artefact moved to `urgency-classifier-v1.1.0`. It is constant in training for the same reason as the other three, so the cross-validated figures above are unchanged — the retrain kept the contract honest, it did not improve the score.)

This is recorded in the artefact's own metadata, in `backend/evaluation/datasets/README.md`, and in the rejected-candidate notes, so the search is auditable rather than looking like an oversight.

## Consequences

- The engine is real and citable, but it is **not** evidence that the feature set works. Its scores sit below the majority baseline, and the reports must show that rather than obscure it.
- The safety layer (ADR 0003) carries more of the clinical weight than originally intended. That is a consequence of this decision, not a separate one.
- The training code is dataset-agnostic: the loader takes a corpus and produces a feature matrix, so swapping in the credentialed dataset is a data change and a retrain, not a rewrite.
- Retraining will change the level predicted for most constructed inputs, so behavioural test fixtures will need re-anchoring. That is expected and is the signal that the swap happened.
- Until a dataset carrying complaint, pain and duration is available, no claim about those features can be supported by a cross-validated score.
