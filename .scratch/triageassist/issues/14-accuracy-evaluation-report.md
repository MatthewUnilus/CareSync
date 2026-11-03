# 14: Accuracy Evaluation Report

**What to build:** The flagship reporting view — the screen that evidences the project's contribution. It compares Machine Recommendations against ground-truth Urgency Levels and presents the engine's correctness alongside where staff disagreed with it. This is the most carefully designed Report in the system.

**Blocked by:** 04, 08, 13.

**Status:** ready-for-agent

- [ ] The Report shows a confusion matrix of Machine Recommendation against ground-truth Urgency Level across all three levels.
- [ ] The Report shows precision and recall for each Urgency Level separately, not only an aggregate score.
- [ ] The Report shows False High-Priority and False Low-Priority rates as separate figures, so missed urgent cases are visible as their own risk.
- [ ] The Report shows the Override rate and the distribution of Override Reasons.
- [ ] Every figure is computed from stored, immutable Triage Assessments, so a later Override cannot alter a Machine Recommendation's contribution to the matrix.
- [ ] An evaluation run with the fallback disabled and a run with it enabled are distinguishable in the reported results, with fallback coverage shown as its own statistic rather than folded into the main score.
- [ ] An Administrator can view the Report on the web dashboard, and it is visually the most prominent reporting view.
