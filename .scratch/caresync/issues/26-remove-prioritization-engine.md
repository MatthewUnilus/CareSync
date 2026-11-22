# 26: Remove the prioritization engine

**What to build:** No Urgency Level, no Queue, no Override, no Re-assessment, no scoring of any kind. What survives is the infrastructure a nursing workflow system needs: patients, visits, sessions, the audit log and the two roles. About 230 of the 302 test functions go, and the boundary files land in the same pass or the application stops importing.

**Blocked by:** 25 (the accuracy report is the first dent and this is the second).

**Status:** ready-for-agent

- [ ] Deleted: `prioritisation.py`, `classifier.py`, `features.py`, `red_flags.py`, `fallback.py`, `fallback_cache.py`, `symptom_groups.py`, `symptom_groups.json`, `assessments.py`, `queue.py`, `overrides.py`, `override_reasons.py`, `reassessments.py`.
- [ ] `models.py` loses `TriageAssessment` and its frozen-field guard, `FallbackCacheEntry`, and `Override`. `AuditEntry` loses its Assessment subject. `Encounter` loses `evaluation_run_id` and its ten vital-sign columns, keeping patient, arrived, ended and a reason for the visit.
- [ ] `schemas.py` loses every `Assessment*`, `Override*`, `RedFlag`, `Queue*`, `Urgency*` and `Accuracy*` model, and its four cross-imports of deleted modules at lines 15 to 20.
- [ ] `config.py` loses `fallback_provider_url`, `fallback_provider_api_key` and `fallback_timeout_seconds` alongside the `accuracy_run_path` that ticket 25 removed.
- [ ] `deps.py` loses the fallback dependency and its alias. `main.py` loses the fallback provider wiring and its `fallback_provider` parameter.
- [ ] `audit_actions.py` loses `override`, `reassessment` and `departure`. `open_encounter` and `correct_intake` are reworded to match the surviving vocabulary, and the check constraint follows the enum automatically.
- [ ] `reports.py` keeps the day's volume and throughput and loses the assessment-derived figures.
- [ ] `clinical.py` loses the queue, override-reasons, override, departure and reassessment routes, and keeps access, registration, search, history, encounter creation, encounter read and the recent list. Its `_assessment_response` and `_override_response` helpers go.
- [ ] `administrator.py` loses the dense queue route and the accuracy response builder.
- [ ] `departures.py` is **reduced, not deleted**. Keep `encounter_status` and the end-of-visit instant as `ended_at`, renamed so it stops meaning "left a queue". `EncounterStatus` survives because `schemas.py` consumes it. Rename `perform_departure` to an end-of-visit action with no queue semantics.
- [ ] `intake.py` keeps `apply_intake` and loses `has_triage_assessment`, `ensure_intake_editable` and the locked-intake detail, because nothing freezes intake any more.
- [ ] `patients.py`, `security.py`, `db.py`, `timeutils.py`, `seed.py`, `auth.py` and `meta.py` are untouched. Verify rather than assume: `seed.py` seeds two users and no domain rows.
- [ ] 20 test files are deleted whole, and the mixed files are trimmed: `test_audit_log.py` keeps 6 of 13, `test_encounter_intake.py` keeps 9 of 12, `test_patient_search.py` keeps 9 of 10, and `test_administrator_refused_clinical_routes.py` keeps its pattern with 7 of its 13 parameterised cases removed.
- [ ] `conftest.py`'s `LOW_INTAKE`, `MEDIUM_INTAKE` and `HIGH_INTAKE` fixtures are renamed to something neutral. Their comment says the classifier separates them and their ages of 24, 80 and 78 are classifier inputs, so the names encode a deleted taxonomy.
- [ ] The suite passes with roughly 43 test functions, and `import app.main` succeeds with no reference to a deleted module.

## Notes

- Order the edits by the import graph, or the app is unimportable at every step. `models.py` first, then `schemas.py`, then the modules that import both, then the routers.
- `departures.py` is the one module on the delete list that is workflow-shaped rather than triage-shaped. It is also the only thing that makes a visit look completed in a patient history, which the ward needs. Reduce it rather than removing it, and say so in the ADR if the decision is contested.
- `EncounterStatus` in `schemas.py` is a shared surface. Moving or deleting it is not a leaf change.
- Four surviving call sites filter on `evaluation_run_id` (`queue.py`, two in `reports.py`, and `clinical.py`). Two of those files are themselves partly deleted, so check `reports.py` carefully: it is the one most likely to keep a predicate on a column that no longer exists.
- After ticket 25 the corpus is gone and nothing creates the column, so this is the ticket that drops it.
- Keep the intake field bounds. Pain 1 to 10, temperature 30 to 45, heart rate 20 to 300, respiratory rate 0 to 80, systolic 50 to 300, diastolic 20 to 200, systolic greater than diastolic, and saturation 50 to 100 are all still the right validation for an Observation, which ticket 30 moves them to.
