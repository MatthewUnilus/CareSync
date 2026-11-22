# 24: Audit action labels come from the server

**What to build:** Every Audit Entry arrives with its human label beside its machine key. Today `frontend/src/AdministratorDashboard.tsx` hard-codes all six action values in an `ACTION_LABELS` map with a comment pointing at `backend/app/audit_actions.py` as the source. The action set is about to grow to roughly seventeen for the ward work, so the copy has to stop before it drifts. This is a prefactor: it changes no behaviour except where the label is computed, and it lands before the demolition so the client never learns values that are about to be deleted.

**Blocked by:** none.

**Status:** done

- [x] The action's human label lives beside the enum in `backend/app/audit_actions.py`, in the same file so the two cannot drift.
- [x] Every audit entry returned by `GET /api/administrator/audit-log` carries its label.
- [x] The client renders the server's label and holds no action-value map of its own.
- [x] The fallback for a value the server did not label is defined and deliberate, rather than showing a raw snake_case key to an administrator.
- [x] The existing audit-log tests pass unchanged, and a test asserts the label is present and correct for each action in the set.
- [x] A test asserts that every member of the action enum has a label, so adding an action without a label fails the suite rather than reaching the UI.

## Notes

- The map is at `AdministratorDashboard.tsx:31-41` with `actionLabel()` at 43-45. The comment there already says the values mirror `backend/app/audit_actions.py`, which is the drift this ticket removes.
- `AuditAction` is a `str, Enum` whose docstring explains why values are snake_case: "an action is a machine-readable key used for filtering and counting, unlike an Override Reason which is a reportable clinical dimension rendered to a human". The label is that reportable dimension, so it belongs in the same module as a second table rather than replacing the keys.
- Keep the keys. They are what tests and filters match on, and changing them would rewrite the audit log's stored values.
- The reason this goes first: a client-side map that grows to seventeen entries alongside a server enum that grows to seventeen will disagree within one ticket. Doing it now means the ward work adds actions in one place.

## Comments

Landed on `ticket/24-audit-action-labels`. Backend suite: 430 passed, 10 skipped (was 425 passed, 10 skipped before; the change adds 5 tests and no regressions). The 10 skips are the evaluation-harness dataset tests, which need a dataset cache the worktree does not carry; they are unrelated to this ticket.

Labels live in `AUDIT_ACTION_LABELS` beside the enum, keyed by `AuditAction`, with `label_for()` as the one reader. `label_for` accepts the enum or its raw string and returns `UNKNOWN_ACTION_LABEL` ("Unknown action") for a value not in the set, so the fallback is server-side and shared rather than reinvented per caller. `AuditEntryResponse` gained `action_label: str`, filled in the route from `label_for(entry.action)`; the key is unchanged, so tests and filters still match on it.

The client's `ACTION_LABELS` map is deleted. `actionLabel(entry)` renders `entry.action_label`, with a local `"Unlabelled action"` fallback for an older server or a missing field; the server's own fallback already covers an unknown value, so raw snake_case never reaches the screen. `AuditEntry` in `api.ts` gained `action_label: string`.

Tests added to `backend/tests/test_audit_log.py`: `test_every_action_has_a_label` (table covers the enum exactly, no stale rows), `test_a_label_is_never_the_raw_key`, `test_the_audit_log_serves_each_actions_label` (all six actions end to end), `test_a_correction_entry_carries_its_label` (the sixth action, reachable only for an Assessment-less Encounter), and `test_label_for_falls_back_deliberately`. The existing 13 tests are unchanged and pass.

Unsure about: (1) the labels are byte-identical to the old client map. I found no vocabulary change ticket 23 made that touches these six reads, so I improved nothing rather than change copy without a reason. (2) `npm run build:web` type-checks (`tsc --noEmit` passes) but `vite build` fails on this machine with `esbuild` "Access is denied" deleting its own temp file. The identical failure reproduces on the untouched `caresync` checkout, so it is pre-existing and environmental, not from this change.
