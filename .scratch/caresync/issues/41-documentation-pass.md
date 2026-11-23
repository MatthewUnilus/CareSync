# 41: Documentation pass

**What to build:** The repository describes CareSync as it now is. This mirrors what the `proposal-gaps` ticket 21 did for the triage work: the README's surface table, the product contract, and the docs that tell a reader what the system is for.

**Blocked by:** 38, 39, 40 (the last features, so nothing documented is still moving).

**Status:** done

- [x] `README.md` describes a nursing workflow system. Its positioning, stack, setup, demo users, patient matching, mobile client, security behaviour, environment variables and layout sections are accurate, and the sections on Symptom Groups, the Prioritization Engine, the Queue, the red-flag safety layer, the cached fallback, Override, Departure and Re-assessment are gone or archived.
- [x] The README's API surface table lists the surviving routes and the new ward routes, and no removed ones.
- [x] The README's environment-variable table matches the renamed prefix and the settings that actually exist.
- [x] `frontend/PRODUCT.md` describes CareSync: the ward nurse as the primary user, the administrator as read-only oversight, what the system does not do, and the accessibility floor. Its triage positioning, its "both records survive" claim and its urgency principles are replaced rather than trimmed.
- [x] `frontend/PRODUCT.md`'s stale statements are corrected: the mobile shell shipped, and the hospital and the ward are real.
- [x] The surviving ADRs read as current, and the superseded ones point forward rather than being silently wrong.
- [x] The removed subsystem documents are either deleted or sitting in a clearly named archive directory with a header saying they describe a system that no longer ships. This is the ticket that makes that call once.
- [x] The frontend `AGENTS.md` and the BoardUI rules still read correctly against the pruned component tree.
- [x] A reader who has never seen the project can go from the README to a running system without hitting a removed concept.
- [x] `npm test` and `npm run build:web` pass, and a fresh checkout with a deleted database starts and serves a login page.

## Notes

- The README is 715 lines and its "Layout" section inventories both source trees. That section is the one most likely to be left half-correct after a deletion this size, so check it against the tree rather than editing it from memory.
- Read `frontend/PRODUCT.md`'s header before editing it: it is schema-tagged and its sections carry specific meanings, so a name swap is not enough. Its "Evidence on Hand" section in particular points at a spec and a glossary that both changed.
- The process docs under `docs/agents/` describe how the issue tracker and the domain docs work. They are tooling rather than product, so they should need no change beyond anything the pivot broke.
- This is the last ticket, and it is the one that decides whether the repository reads as a coherent project or as a triage system with a ward bolted on. Budget the time for it rather than treating it as cleanup.

## Comments

Built on `ticket/41-documentation-pass`, merged to
`integration/caresync-ward-features`. `npm run build:web` green and the full API
suite green. (`npm test:web` fails in this environment because the installed
Node 22.22 build has no TypeScript support at all — `ERR_NO_TYPESCRIPT` — which
is pre-existing and unrelated; `main` fails identically.)

**README rewritten as a nursing workflow system.** The triage-era sections —
Intake, Symptom Groups, Prioritization Engine and the Queue, Override,
Departure, Re-assessment, the old Administrator dashboard, the old Reports, and
the stale API-surface and Layout inventories — are gone, not marked obsolete. A
new "Ward features" section describes admissions and the board, the Observation
chart, Nursing Notes, medications, Investigations, Tasks, printable sheets, the
Administrator dashboard and the study instrumentation, each pointing at its ADR.

**The API surface table is rebuilt against the running routes** (auth, clinical,
ward, administrator) and lists no removed route. The environment table gains
`CARESYNC_STUDY_INSTRUMENTATION_ENABLED`. The schema/migration operator notes
collapse into one section that names the grown audit action set.

**The Layout inventory is rebuilt against the tree**, naming the ward modules
(`admissions`, `departures`, `observations`, `notes`, `medications`,
`administrations`, `tasks`, `investigations`), the ward router, the new frontend
components and `print.css`, and the `docs/archive/` triage documents.

**PRODUCT.md's stale claim is corrected.** It said the ward capabilities were
unshipped and landing incrementally; they are now landed, so the sentence is
replaced rather than trimmed. Its positioning, users and "what it does not do"
sections already read as CareSync and were left as they were.

**The ADRs already read as current.** 0002–0006 are marked Superseded and point
forward to 0014; 0001 and 0007 carry amendments; 0008–0014 describe the ward
work. The removed subsystem documents already sit in `docs/archive/` behind a
header saying they describe a system that no longer ships. `frontend/AGENTS.md`
and `docs/agents/` needed no change beyond the pivot they already reflect.

**A fresh reader can run it.** The README goes from setup to a running login
page using only concepts that still exist.
