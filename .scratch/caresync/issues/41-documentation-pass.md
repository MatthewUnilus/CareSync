# 41: Documentation pass

**What to build:** The repository describes CareSync as it now is. This mirrors what the `proposal-gaps` ticket 21 did for the triage work: the README's surface table, the product contract, and the docs that tell a reader what the system is for.

**Blocked by:** 38, 39, 40 (the last features, so nothing documented is still moving).

**Status:** ready-for-agent

- [ ] `README.md` describes a nursing workflow system. Its positioning, stack, setup, demo users, patient matching, mobile client, security behaviour, environment variables and layout sections are accurate, and the sections on Symptom Groups, the Prioritization Engine, the Queue, the red-flag safety layer, the cached fallback, Override, Departure and Re-assessment are gone or archived.
- [ ] The README's API surface table lists the surviving routes and the new ward routes, and no removed ones.
- [ ] The README's environment-variable table matches the renamed prefix and the settings that actually exist.
- [ ] `frontend/PRODUCT.md` describes CareSync: the ward nurse as the primary user, the administrator as read-only oversight, what the system does not do, and the accessibility floor. Its triage positioning, its "both records survive" claim and its urgency principles are replaced rather than trimmed.
- [ ] `frontend/PRODUCT.md`'s stale statements are corrected: the mobile shell shipped, and the hospital and the ward are real.
- [ ] The surviving ADRs read as current, and the superseded ones point forward rather than being silently wrong.
- [ ] The removed subsystem documents are either deleted or sitting in a clearly named archive directory with a header saying they describe a system that no longer ships. This is the ticket that makes that call once.
- [ ] The frontend `AGENTS.md` and the BoardUI rules still read correctly against the pruned component tree.
- [ ] A reader who has never seen the project can go from the README to a running system without hitting a removed concept.
- [ ] `npm test` and `npm run build:web` pass, and a fresh checkout with a deleted database starts and serves a login page.

## Notes

- The README is 715 lines and its "Layout" section inventories both source trees. That section is the one most likely to be left half-correct after a deletion this size, so check it against the tree rather than editing it from memory.
- Read `frontend/PRODUCT.md`'s header before editing it: it is schema-tagged and its sections carry specific meanings, so a name swap is not enough. Its "Evidence on Hand" section in particular points at a spec and a glossary that both changed.
- The process docs under `docs/agents/` describe how the issue tracker and the domain docs work. They are tooling rather than product, so they should need no change beyond anything the pivot broke.
- This is the last ticket, and it is the one that decides whether the repository reads as a coherent project or as a triage system with a ward bolted on. Budget the time for it rather than treating it as cleanup.
