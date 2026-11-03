# 05: Symptom Group recognition

**What to build:** The free-text presenting complaint is mapped onto the fixed Symptom Group vocabulary, and the groups the system recognised are visible to the Clinical user on the Encounter's card, so a misreading of the text is obvious before it affects care.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] The Symptom Group vocabulary exists as a concrete, finite list authored clinically first, anchored on ESI red-flag and common presentations.
- [ ] A complaint is recognised onto zero or more Symptom Groups, with no synonym table and no inference beyond matching onto that list.
- [ ] Recognition runs as part of producing a Triage Assessment; the recognised Symptom Groups are stored with the assessment and never change afterwards.
- [ ] The expanded Encounter card shows which Symptom Groups the complaint was mapped onto.
- [ ] A complaint matching no Symptom Group is recognised as matching none, and is distinguishable from a complaint that matched one.
- [ ] Vocabulary terms use the project's glossary vocabulary, and no term is introduced that `CONTEXT.md` does not define.
