# 23: Ward vocabulary, ADRs and the pivot spec

**What to build:** The vocabulary and the decisions come before any code, so the demolition is not the first time the pivot is written down. This ticket closes with `CONTEXT.md` describing a nursing workflow system, seven new ADRs recording why, the superseded ones marked as such, and the spec registered as the authoritative contract.

**Blocked by:** none.

**Status:** done

- [ ] `CONTEXT.md` gains eleven terms in its existing style: Admission, Discharge, Observation, Nursing Note, Note Template, Medication Order, Medication Administration, Medication Round Time, Investigation, Task, Ward Board.
- [ ] `CONTEXT.md` loses the triage terms: Triage Assessment, Urgency, Urgency Level, Machine Recommendation, Final Decision, Override, Override Reason, Re-assessment, Queue, Prioritization Engine, Symptom Group, Departure. ESI goes with them, because it existed as the evaluation's reference standard and there is no evaluation left for it to reference.
- [ ] `CONTEXT.md` keeps and trims Patient, Encounter, Roles, Report and Audit Entry. Encounter stops mentioning the Queue; Report stops deriving from Triage Assessment records; Audit Entry loses its Assessment subject.
- [ ] ADR 0008 is written: an Admission is separate from an Encounter, and vital signs move out of the Encounter into one Observation time series.
- [ ] ADR 0009 is written: the system runs alongside the paper nursing record, and a printed sheet is a worklist, not the record.
- [ ] ADR 0010 is written: an Observation outside its reference range is marked for display and nothing more. It restates ADR 0006's rule, which outlives the engine because the reason for it does.
- [ ] ADR 0011 is written: a Medication Order transcribes an instruction, with no dose calculation and no interaction or allergy checking, and an order's clinical fields are frozen so a change is a stop and a new order.
- [ ] ADR 0012 is written: an Investigation tracks progress and the review act, and never reads or interprets a result.
- [ ] ADR 0013 is written: Note Templates are a fixed code vocabulary with one row per field, because there is no migration tool and the hospital's real forms will change the templates.
- [ ] ADR 0014 is written: the triage engine is removed, what replaces its evidence, and the patient-identity rule that changes with it. It records that this changes the proposal's stated focus, so the reason is written down even though no approval gate applies.
- [ ] ADRs 0002 to 0006 are marked **Superseded**, not deleted, each naming 0014 as what supersedes it. ADR 0007 (audit log) and 0001 (data layer) are kept and amended.
- [ ] `docs/prioritisation-in-context.md`, `docs/red-flag-safety-layer.md`, `docs/cached-fallback.md` and `docs/accuracy-evaluation-report.md` are marked as describing removed subsystems, or moved to a clearly named archive directory, so a reader does not take them for current design. They are deleted outright in ticket 26 only if nothing in the dissertation needs to cite them.
- [ ] `.scratch/caresync/spec.md` is in place and its Status is `ready-for-agent`.

## Notes

- `docs/agents/domain.md` says to use `CONTEXT.md`'s vocabulary and to surface an ADR conflict explicitly rather than silently overriding it. Marks 0002 to 0006 as Superseded is that rule being followed, and the ADR format already has a place for it.
- ADR 0006 needs care. It rejected reordering by wait and auto-escalation in a system that had a queue. The rule survives the pivot but the reason narrows to "the system never acts on a timer", which is what ADR 0010 should say.
- The terms to add are chosen so that every user story in the spec is sayable in the glossary's language. If a story needs a word that is not in the list, that is the signal `docs/agents/domain.md` describes, and it should be resolved here rather than in code.
- Ethics approval for the usability study starts here, not after the system is built. A study with ward staff needs the hospital's agreement and probably the university's review, and both have lead time.

## Comments

Done. `CONTEXT.md` is now a CareSync glossary: the eleven ward terms (Admission, Discharge, Observation, Nursing Note, Note Template, Medication Order, Medication Administration, Medication Round Time, Investigation, Task, Ward Board) are in, the triage terms and the ESI material are out, and Patient, Encounter, Roles, Report and Audit Entry are kept and trimmed. The header's "glossary only" rule holds: no schema, no table names, nothing about the API.

Seven ADRs 0008 to 0014 written in the existing format, status "Accepted (2026-11-22)". 0002 to 0006 marked Superseded, each naming 0014. 0001 and 0007 kept and amended: 0001 gains an amendment saying the application-layer no-triggers rule is what the ward entities lean on; 0007 gains the action-set growth, the Admission subject replacing the Assessment subject, and the label-set move to one source of truth.

The four subsystem docs moved to `docs/archive/` with a removal header pointing at 0014, not deleted.

Two judgement calls.

- The archived red-flag doc's reference range is the one ADR 0010 keeps, so the archive header on `red-flag-safety-layer.md` points at 0010 as well as 0014. The range outlives the engine, so a reader arriving at that doc should see where it went.
- The move broke two things that referenced the old paths: `backend/tests/test_red_flags.py` read `docs/red-flag-safety-layer.md` by literal path, and `README.md` linked all four docs. Both were updated to the `docs/archive/` paths. Nothing under `backend/` or `frontend/` source changed; the test edit is a path string only, and the ticket's "tests must still pass" is the reason it moved rather than being left broken.

Every spec story from 64 to 122 is sayable in the glossary's language. No story needed a term the list does not hold. "Doctor" and "ward round entry" appear in stories but are not domain entities: a Medication Order and a ward round Nursing Note name the doctor as the instruction's source, and a Task names the round entry it came from, so neither needs its own glossary term.

Tests: `uv run pytest -q` green (the worktree's fresh `.venv` hits a Windows `thinc` `numpy_ops` DLL load failure unrelated to these changes, so the suite was run with the main checkout's working interpreter against the worktree's code; 425 passed, 10 skipped, 0 failures).
