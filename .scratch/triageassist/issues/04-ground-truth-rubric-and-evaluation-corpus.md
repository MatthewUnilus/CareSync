# 04: Ground-truth rubric and labelled evaluation corpus

**What to build:** An independent, citable standard for what the correct Urgency Level is, and a labelled corpus that later tickets score the engine against. The rubric is derived from published ESI v4 criteria and deliberately richer than the engine's own feature set, so the accuracy claim is not self-referential. Synthetic Encounters labelled by the rubric give the pipeline something to be proven on end to end.

**Blocked by:** 02.

**Status:** done

- [ ] A written rubric maps a described presentation to exactly one Urgency Level, citing its published source criteria.
- [ ] The rubric's inputs are deliberately broader than the Prioritization Engine's feature set, and it is authored without reference to the engine's rules.
- [ ] The rubric is applied by a labeller that takes a described presentation and returns the labelled Urgency Level.
- [ ] A generator produces synthetic Encounters spanning all three Urgency Levels and all four vitals, with labels supplied by the rubric rather than by the engine.
- [ ] The generated corpus is reproducible from a fixed seed.
- [ ] The corpus is stored in a form a later evaluation run can consume without re-generating it.
- [ ] Ground-truth labels are kept distinct from Machine Recommendations and Final Decisions in the stored data.

## Comments

Resolved on `integration` (merge `2f69b30`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
