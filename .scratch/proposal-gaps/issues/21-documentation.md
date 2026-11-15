# 21: Documentation and the audit-log ADR

**What to build:** The written record catches up with the three features: the API surface, the red-flag rule set, the feature-vector version, and a new ADR for the audit log.

**Blocked by:** 17, 18, 19, 20.

**Status:** open

- [ ] The README API table lists the two new clinical routes and the audit-log route, with their query parameters and role requirements.
- [ ] The README's description of the classifier artefact records the new version and its feature count.
- [ ] ADR 0005's feature count (currently "51 of 57 features are constant") is corrected for the larger vector, and its honest statement of the cross-validated accuracy is preserved — not revised upward.
- [ ] A new ADR records the audit log: its shape, the fixed action set, and the decision to enforce append-only in the application layer rather than with database triggers, following ADR 0001.
- [ ] `docs/red-flag-safety-layer.md` names the tachypnoea rules and their citations, and the rule count stated there is updated.
- [ ] Any prose describing the intake's vital signs lists respiratory rate.
- [ ] The README's layout listing includes any new module.

## Notes

- The ADR bar in this repo is: hard to reverse, surprising without context, and a real trade-off. The audit log's append-only-in-application-layer choice qualifies — it is the same trade-off ADR 0001 already documents for the Triage Assessment guard, and a reader who did not know that would reasonably expect triggers or constraints.
- Do not restate the features at length; point at the spec and the tickets.
- Check the existing ADRs' format before writing the new one and match it.

## Comments
