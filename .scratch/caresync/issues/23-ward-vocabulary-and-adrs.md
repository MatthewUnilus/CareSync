# 23: Ward vocabulary, ADRs and the pivot spec

**What to build:** The vocabulary and the decisions come before any code, so the demolition is not the first time the pivot is written down. This ticket closes with `CONTEXT.md` describing a nursing workflow system, seven new ADRs recording why, the superseded ones marked as such, and the spec registered as the authoritative contract.

**Blocked by:** none.

**Status:** ready-for-agent

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
