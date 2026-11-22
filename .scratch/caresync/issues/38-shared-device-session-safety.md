# 38: Shared-device session safety

**What to build:** A session on a shared tablet locks when nobody has touched it, and a nurse can lock and hand the tablet over deliberately. This is a patient-privacy fix, not a convenience: the session lasts eight hours and a ward tablet is picked up by whoever is nearest, so today the next person to open it sees the last nurse's patients. It is blocked by nothing because the fix does not depend on any ward feature, and it is sequenced late only because it is not on the critical path.

**Blocked by:** none.

**Status:** done

- [x] An inactivity timeout locks the session, on a period shorter than the session's own lifetime, configurable and defaulting to something suitable for a shared device.
- [x] Locking hides patient data without logging the user out: the session survives, and unlocking is a credential check rather than a fresh sign-in.
- [x] An explicit lock action is available, so a nurse can hand the tablet over without waiting for the timer.
- [x] A switch-user action signs the current user out and returns to sign-in, for a deliberate handover to a different person.
- [x] The lock is enforced on the server as well as presented in the client. A locked session is refused by the API, so a hidden screen is not the only thing standing between the next person and the record.
- [x] Unlocking is rate-limited, so a locked tablet cannot be used as an unattended guessing surface.
- [x] `session_cookie_secure` is set for the deployment, documented in the README's security section with the reason it requires HTTPS, and not left as a trap that silently breaks sign-in over plain HTTP.
- [x] The session TTL default is reconsidered against a shared-device ward rather than an eight-hour working day, and the choice is recorded with its reasoning.
- [x] Tests: a locked session is refused by the API; an expired-by-inactivity session is refused; unlocking with the right credential resumes the same session; unlocking with the wrong credential is refused and rate-limited; a valid session is unaffected.

## Notes

- Server-side enforcement is the part that matters. A client-side lock that hides a screen while the API still answers is a privacy fix in appearance only, and it would not survive the first reviewer who tried it with a tool.
- Rate limiting has no existing pattern in this codebase, so keep it simple and in the application layer, consistent with ADR 0001's no-database-triggers rule. A counter on the session row is enough at this scale.
- `session_ttl_seconds` defaults to 8 hours in `backend/app/config.py` and `session_cookie_secure` defaults to false. Both defaults are reasonable for a personal device and wrong for a shared one. The README's "Security behaviour" section documents the current stance and is where the change is explained.
- HTTPS and a reverse proxy are a go-live prerequisite rather than a code change, and they are what makes the secure cookie meaningful. The README should say that plainly so the hospital's IT does not enable the flag against a plain-HTTP deployment and lock everyone out.
- Consider whether the lock state belongs in the session cookie, the session row, or both. A session row is where the expiry already lives, and putting the lock beside it keeps one source of truth for "may this session act".
- This is the one ticket in the set that a hospital IT reviewer would ask about first, and its absence would be a finding against deploying at all.

## Comments

Built on `ticket/38-session-safety`. Suite green: 443 passed (10 skipped when the
published datasets are not cached), 8 of them the new lock tests.

**Lock state lives on the session row, not the cookie.** The row already holds
`expires_at`, so the lock sits beside it and there is one source of truth for
"may this session act". Three columns were added to `UserSession`:
`last_seen_at` (drives the idle window), `locked_at` (null means unlocked), and
the `unlock_attempts` / `unlock_blocked_until` pair for rate limiting. A cookie
copy of the lock would be a second place for it to disagree with itself, and a
reviewer with a tool can edit a cookie anyway.

**Server-side enforcement is the lock, not a decoration on it.**
`deps.get_current_session` is now the dependency every authenticated route
resolves, and it refuses a locked session with **423 Locked**, distinct from
401, so the client can tell "locked, unlock me" from "signed out, sign in
again". The idle case is derived from `last_seen_at` at request time and
persisted on first detection, so the lock is never on a timer. The frontend
listens for a `SESSION_LOCKED_EVENT` the request module fires on any 423, which
matters because the background poll can hit the lock while nobody is clicking.

**The idle window is shorter than the session's own lifetime, deliberately.**
`session_idle_seconds` defaults to 5 minutes and `session_ttl_seconds` was cut
from 8 hours to 4. The ticket asks that the TTL be reconsidered for a shared
device: the lock is the control that answers the next person picking up the
tablet, and the TTL is the backstop for a token that escapes the lock (a
restored tab, a copied cookie). Four hours covers half a shift, so an escaped
token dies within one shift rather than lasting a full working day. A heartbeat
(`session_heartbeat_seconds`, 60) throttles the last-seen write so the ward
board's five-second poll does not write a row per request.

**Rate limiting is a counter on the session row**, checked and incremented in
`app/session_lock.py` and enforced in the unlock route, per ADR 0001's no
triggers rule. Five wrong passwords (configurable) block further attempts for
60 seconds, and a blocked attempt is refused with 429 even when the password is
correct.

**`session_cookie_secure` stays `false` by default and is documented, not
flipped.** Turning it on against a plain-HTTP deployment is the trap the ticket
names: the browser withholds a `Secure` cookie over HTTP, so sign-in writes a
session row and every following request looks unauthenticated. The README's
"Security behaviour" now says HTTPS and a reverse proxy are a go-live
prerequisite and the flag is set after them, not before.

**One uncertainty.** `session_ttl_seconds` 4 hours is judgement, not evidence:
the ticket gives no number and no ward shift length. It is configurable and the
reasoning is in the config comment and the README, so a real shift length from
the hospital would change it without touching code.

