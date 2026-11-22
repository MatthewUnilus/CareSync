# 22: Freeze the triage work in git

**What to build:** The triage system about to be deleted stays findable. Nothing is removed in this ticket; it only makes the removal safe. It exists because around 16,200 lines are deleted by tickets 25 and 26, and a dissertation chapter that discusses how the engine worked needs a commit it can cite and a checkout it can recover.

**Blocked by:** none.

**Status:** ready-for-agent

- [ ] The current working tree is committed or stashed. It is dirty: the audit-log frontend work, `frontend/src/TriageKitGallery.tsx`, `frontend/components/triage/`, `frontend/PRODUCT.md`, `.impeccable/`, `.tmp-ref/`, `.zcode-share/` and `TriageAssist-Chapter6-System-Implementation.docx` are all uncommitted. Decide per item, and treat the scratch directories as local state rather than content to commit.
- [ ] The last triage commit is tagged. `triage-engine-final` is the suggested name.
- [ ] `git status` is clean and the tag points at the commit the triage system was last complete at.
- [ ] `git tag -l` shows the tag, and `git log --oneline <tag>` shows the triage work intact.

## Notes

- A tag is the whole mechanism. It costs nothing, it never conflicts, and `git checkout triage-engine-final` recovers the deleted code during writing up.
- Do not commit `.tmp-ref/` and `.zcode-share/`: both are working scratch with large binaries. Check `.gitignore` covers them before committing anything nearby.
- The classifier artefact `backend/models/urgency-classifier-v1.1.0.json`, the 1,525-line evaluation corpus and the 1,100-line results artefact are all committed, so they are covered by the tag. They do not need separate copies.
- If the dirty tree contains work worth keeping beyond the tag, commit it on its own branch first so the tag recorded what the triage system actually was.
