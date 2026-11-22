# 22: Freeze the triage work in git

**What to build:** The triage system about to be deleted stays findable. Nothing is removed in this ticket; it only makes the removal safe. It exists because around 16,200 lines are deleted by tickets 25 and 26, and a dissertation chapter that discusses how the engine worked needs a commit it can cite and a checkout it can recover.

**Blocked by:** none.

**Status:** done

- [x] The working tree is free of uncommitted triage content, and scratch directories (`.tmp-ref/`, `.zcode-share/`) are treated as local state rather than committed.
- [x] The last triage commit is tagged. `triage-engine-final` is the suggested name.
- [x] `git status` is clean and the tag points at the commit the triage system was last complete at.
- [x] `git tag -l` shows the tag, and `git log --oneline <tag>` shows the triage work intact.

## Notes

- A tag is the whole mechanism. It costs nothing, it never conflicts, and `git checkout triage-engine-final` recovers the deleted code during writing up.
- Do not commit `.tmp-ref/` and `.zcode-share/`: both are working scratch with large binaries. Check `.gitignore` covers them before committing anything nearby.
- The classifier artefact `backend/models/urgency-classifier-v1.1.0.json`, the 1,525-line evaluation corpus and the 1,100-line results artefact are all committed, so they are covered by the tag. They do not need separate copies.
- If the dirty tree contains work worth keeping beyond the tag, commit it on its own branch first so the tag recorded what the triage system actually was.

## Comments

The tag already existed and no longer needed creating: `triage-engine-final` resolves to `3d532af` ("feat(web): audit log UI, triage kit and the pivot tickets"), an ancestor of the current `caresync` HEAD (after ticket 25). It was left untouched — not moved or recreated — and `git log --oneline triage-engine-final` shows the triage system intact at it: the backend engine (`backend/app/classifier.py`, `backend/app/features.py`, `backend/app/prioritisation.py`, `backend/app/red_flags.py`) with the classifier artefact `backend/models/urgency-classifier-v1.1.0.json`, and the frontend surfaces (`frontend/components/triage/`, `frontend/src/TriageKitGallery.tsx`).

Before this ticket the working tree held fifteen tracked modifications and one untracked file, all authored by the prior agent turn (a red-flag/respiratory-rate bug fix: the `respiratory_rate_bpm` sentinel, the WHO IITT low-rate guards, the Android debug-manifest cleartext split, and the matching docs and tests). The user explicitly declined keeping that work in a separate commit, so it was **discarded** rather than committed: the fifteen tracked files were reverted to HEAD and the untracked `android/app/src/debug/AndroidManifest.xml` was deleted, along with its now-empty `debug` directory. No independent user work was found in the dirty set, `git stash list` was empty, and nothing was staged, so nothing else was reverted. After this issues-only change is committed on `caresync`, `git status` is clean. No branches were created and the tag was not modified.
