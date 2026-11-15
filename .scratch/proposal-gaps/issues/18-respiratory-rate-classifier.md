# 18: Respiratory rate — classifier feature, artefact bump and retrain

**What to build:** Respiratory rate becomes a dimension of the classifier feature vector, and the shipped artefact is retrained and version-bumped so inference and training agree. This is the contract move described in the spec: the vector is a single definition used by both training and inference, and the loader raises when the artefact's feature list disagrees with the code's.

**Blocked by:** 17.

**Status:** open

- [ ] `SCALAR_FEATURE_NAMES`, `FeatureInputs` and `build_feature_vector` in `features.py` include `respiratory_rate_bpm`, appended after the existing dimensions, with the module docstring's dimension list updated.
- [ ] The training loader supplies a missing-value sentinel for respiratory rate, following the existing `MISSING_PAIN_LEVEL` / `MISSING_ILLNESS_DURATION_HOURS` convention (the source records no respiratory rate). The sentinel sits outside the intake's producible domain.
- [ ] The evaluation pipeline carries respiratory rate end-to-end: the corpus generator's `EncounterIntake`, `_to_encounter` (which currently drops it despite the scenario dicts carrying it), `materialise.py`, and both `harness.py` adapters.
- [ ] The classifier artefact is retrained and written as **v1.1.0**, and every reference to the version moves with it: `app/classifier.py`, `evaluation/triage_datasets.py`, `evaluation/train_classifier.py`, `evaluation/artefact.py`.
- [ ] The accuracy result artefact is regenerated so its recorded `feature_count` and artefact hash match the retrained model.
- [ ] The accuracy report still renders, and the reported figures remain the honest ones — the added dimension is constant in training and is not presented as an improvement.
- [ ] Tests asserting the feature-vector length and the artefact/code agreement are updated to the new count.
- [ ] Predictions that shift because of the retrain are re-anchored deliberately, with the new expectation stated in the test rather than fitted to output.

## Notes

- The hard gate is the loader's comparison of the artefact's `feature_names` against the code's `FEATURE_NAMES`; a missed retrain surfaces as a runtime error on the first assessment, and the classifier test fails first.
- Expect a near-zero coefficient: the training source records no respiratory rate, exactly as it records no pain level or illness duration. Do not describe the retrain as improving accuracy.
- Confirm the full suite is green before reporting done, and report the retrained accuracy figure plainly.

## Comments
