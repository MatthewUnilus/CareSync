# 01: Walking skeleton and authentication

**What to build:** A runnable stack — Postgres, the Python API, and the React client — brought up together by one command locally, with authentication and the two Roles enforced at the API. A Clinical user and an Administrator can each log in, and neither can reach the other's actions. Passwords are stored hashed, sessions expire, and a user can change their own password.

**Blocked by:** None (can start immediately).

**Status:** done

- [ ] The full stack starts from a clean checkout with a single documented command and serves the client against the API backed by Postgres.
- [ ] A Clinical user starts a session with a valid password and is refused one with an invalid password.
- [ ] A stored password is never recoverable from the database in plain text.
- [ ] A session stops working once its expiry has passed.
- [ ] An authenticated user can change their own password, and the old password stops working afterwards.
- [ ] An Administrator is refused every clinical action and a Clinical user is refused every Administrator-only action, at the API boundary rather than only in the client.
- [ ] There are exactly two Roles; no third role exists in the system.

## Comments

Resolved on `integration` (merge `6c858bc`). Full suite green: 381 passed, 10 skipped (dataset-dependent, skipped when the published data is not cached).
