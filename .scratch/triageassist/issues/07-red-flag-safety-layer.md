# 07: Red-flag safety layer

**What to build:** A documented safety layer between the classifier and the Machine Recommendation, carrying on the order of fifteen to twenty red-flag vital thresholds and red-flag symptoms drawn from ESI, each with a clinical citation. It can raise a recommendation to High and can never lower one, so obvious critical presentations are not missed even when the classifier would have missed them.

**Blocked by:** 06.

**Status:** ready-for-agent

- [ ] Each rule in the layer carries a clinical citation, and the citation is visible in the project's documentation of the layer.
- [ ] A presentation the classifier alone would place at Medium or Low is returned as High when a red-flag rule fires.
- [ ] No rule can lower a recommendation, and a presentation with no firing rule returns the classifier's own result unchanged.
- [ ] The layer applies within the same three-second budget as the rest of the recommendation.
- [ ] The resulting Machine Recommendation is what is stored on the Triage Assessment and what the board orders by.
- [ ] The layer is deliberately bounded to a moderate documented set, and does not grow into a full ESI rule engine.
