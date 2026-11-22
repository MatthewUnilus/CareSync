# 40: Study instrumentation

**What to build:** The system can time a study participant on a set task, so the usability study has a measured figure beside the SUS score. It is behind a setting that is off in normal ward use, and it measures the system rather than the nurse.

**Blocked by:** 37 (the tasks to be timed are the ward workflows, including the sheets).

**Status:** ready-for-agent

- [ ] A small `study_task_runs` table records a study task's label, its start and end instants, and the participant's anonymised identifier.
- [ ] A setting turns the instrumentation on and off, and it is off by default. A normal ward session records nothing.
- [ ] The instrumentation does not record who the participant is. It records a study identifier, so a timed run cannot be traced back to a nurse.
- [ ] Begin and end are explicit actions, one per study task, so a run is deliberate rather than inferred from activity. Do not infer time on task from clicks: an inference would be wrong in exactly the interrupted case a ward produces.
- [ ] A participant can abandon a run, and an abandoned run is recorded as abandoned rather than as a very long one.
- [ ] The runs export in a form the write-up can use, and the export states its own limitations.
- [ ] The instrumented figure is presented as supporting the observer's stopwatch, not replacing it, and the participant materials say so.
- [ ] Tests: instrumentation off records nothing; on, a run records a start and an end; abandoning a run is recorded as abandoned; no participant identity reaches the table.

## Notes

- The interruption problem is real and should be in the write-up. A ward nurse will be interrupted mid-task, and a stopwatch or an instrumented timer will both record a longer time unless somebody notes the interruption. A run that can be abandoned handles part of it; the observer's notes handle the rest.
- Measuring the system and never the nurse is an ethics point rather than a technical one, and it belongs in the participant information sheet and the consent conversation. A nurse who thinks they are being timed for speed will use the system differently, which invalidates the result.
- Keep the table small and separate from the clinical tables. Nothing in the ward features should read it, and it should never join to a Patient. A study record that can be traced to a patient is a data-protection problem with no upside.
- Ethics approval starts in ticket 23. This ticket assumes it landed; if it did not, that is the blocker, not this ticket's code.
- SUS is scored from a questionnaire rather than from the system, so nothing here should try to compute it. The system's job is the time figure; the paper form is the rest.
