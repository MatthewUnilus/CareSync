# 38: Shared-device session safety

**What to build:** A session on a shared tablet locks when nobody has touched it, and a nurse can lock and hand the tablet over deliberately. This is a patient-privacy fix, not a convenience: the session lasts eight hours and a ward tablet is picked up by whoever is nearest, so today the next person to open it sees the last nurse's patients. It is blocked by nothing because the fix does not depend on any ward feature, and it is sequenced late only because it is not on the critical path.

**Blocked by:** none.

**Status:** ready-for-agent

- [ ] An inactivity timeout locks the session, on a period shorter than the session's own lifetime, configurable and defaulting to something suitable for a shared device.
- [ ] Locking hides patient data without logging the user out: the session survives, and unlocking is a credential check rather than a fresh sign-in.
- [ ] An explicit lock action is available, so a nurse can hand the tablet over without waiting for the timer.
- [ ] A switch-user action signs the current user out and returns to sign-in, for a deliberate handover to a different person.
- [ ] The lock is enforced on the server as well as presented in the client. A locked session is refused by the API, so a hidden screen is not the only thing standing between the next person and the record.
- [ ] Unlocking is rate-limited, so a locked tablet cannot be used as an unattended guessing surface.
- [ ] `session_cookie_secure` is set for the deployment, documented in the README's security section with the reason it requires HTTPS, and not left as a trap that silently breaks sign-in over plain HTTP.
- [ ] The session TTL default is reconsidered against a shared-device ward rather than an eight-hour working day, and the choice is recorded with its reasoning.
- [ ] Tests: a locked session is refused by the API; an expired-by-inactivity session is refused; unlocking with the right credential resumes the same session; unlocking with the wrong credential is refused and rate-limited; a valid session is unaffected.

## Notes

- Server-side enforcement is the part that matters. A client-side lock that hides a screen while the API still answers is a privacy fix in appearance only, and it would not survive the first reviewer who tried it with a tool.
- Rate limiting has no existing pattern in this codebase, so keep it simple and in the application layer, consistent with ADR 0001's no-database-triggers rule. A counter on the session row is enough at this scale.
- `session_ttl_seconds` defaults to 8 hours in `backend/app/config.py` and `session_cookie_secure` defaults to false. Both defaults are reasonable for a personal device and wrong for a shared one. The README's "Security behaviour" section documents the current stance and is where the change is explained.
- HTTPS and a reverse proxy are a go-live prerequisite rather than a code change, and they are what makes the secure cookie meaningful. The README should say that plainly so the hospital's IT does not enable the flag against a plain-HTTP deployment and lock everyone out.
- Consider whether the lock state belongs in the session cookie, the session row, or both. A session row is where the expiry already lives, and putting the lock beside it keeps one source of truth for "may this session act".
- This is the one ticket in the set that a hospital IT reviewer would ask about first, and its absence would be a finding against deploying at all.
