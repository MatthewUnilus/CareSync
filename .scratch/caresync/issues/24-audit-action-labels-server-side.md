# 24: Audit action labels come from the server

**What to build:** Every Audit Entry arrives with its human label beside its machine key. Today `frontend/src/AdministratorDashboard.tsx` hard-codes all six action values in an `ACTION_LABELS` map with a comment pointing at `backend/app/audit_actions.py` as the source. The action set is about to grow to roughly seventeen for the ward work, so the copy has to stop before it drifts. This is a prefactor: it changes no behaviour except where the label is computed, and it lands before the demolition so the client never learns values that are about to be deleted.

**Blocked by:** none.

**Status:** ready-for-agent

- [ ] The action's human label lives beside the enum in `backend/app/audit_actions.py`, in the same file so the two cannot drift.
- [ ] Every audit entry returned by `GET /api/administrator/audit-log` carries its label.
- [ ] The client renders the server's label and holds no action-value map of its own.
- [ ] The fallback for a value the server did not label is defined and deliberate, rather than showing a raw snake_case key to an administrator.
- [ ] The existing audit-log tests pass unchanged, and a test asserts the label is present and correct for each action in the set.
- [ ] A test asserts that every member of the action enum has a label, so adding an action without a label fails the suite rather than reaching the UI.

## Notes

- The map is at `AdministratorDashboard.tsx:31-41` with `actionLabel()` at 43-45. The comment there already says the values mirror `backend/app/audit_actions.py`, which is the drift this ticket removes.
- `AuditAction` is a `str, Enum` whose docstring explains why values are snake_case: "an action is a machine-readable key used for filtering and counting, unlike an Override Reason which is a reportable clinical dimension rendered to a human". The label is that reportable dimension, so it belongs in the same module as a second table rather than replacing the keys.
- Keep the keys. They are what tests and filters match on, and changing them would rewrite the audit log's stored values.
- The reason this goes first: a client-side map that grows to seventeen entries alongside a server enum that grows to seventeen will disagree within one ticket. Doing it now means the ward work adds actions in one place.
