"""Shared-device session safety: the inactivity lock and unlock rate limiting.

A session on a shared ward tablet locks when nobody has touched it, and a nurse
can lock the tablet deliberately. Locking hides patient data without ending the
session: the row survives, and unlocking is a credential check on it rather
than a fresh sign-in. The lock state lives on the session row, beside the
expiry it is measured against, so there is one source of truth for "may this
session act".

Everything here is evaluated on a request and in the application layer. There
is no timer and no background task (ADR 0010's rule that the system never acts
on a timer, and ADR 0001's rule against database triggers): a locked session is
refused when it asks to act, and unlock attempts are counted on the row.
"""

from datetime import datetime, timedelta

from app.models import UserSession
from app.timeutils import as_utc


def is_expired(user_session: UserSession, now: datetime) -> bool:
    """True once the session's own lifetime has passed."""
    return as_utc(user_session.expires_at) <= now


def is_locked(
    user_session: UserSession, idle_seconds: int, now: datetime
) -> bool:
    """True when the session may not act.

    Either it was locked deliberately, or the idle window has lapsed since it
    was last seen. The idle case is derived from ``last_seen_at`` so a session
    that was never touched writes no lock row simply because time passed.
    """
    if user_session.locked_at is not None:
        return True
    idle_deadline = as_utc(user_session.last_seen_at) + timedelta(
        seconds=idle_seconds
    )
    return idle_deadline <= now


def lock(user_session: UserSession, now: datetime) -> None:
    """Lock the session deliberately and start a fresh unlock window."""
    user_session.locked_at = now
    user_session.unlock_attempts = 0
    user_session.unlock_blocked_until = None


def touch(
    user_session: UserSession,
    heartbeat_seconds: int,
    now: datetime,
) -> bool:
    """Refresh the last-seen instant, throttled to the heartbeat.

    Returns True when the row changed. The throttle keeps a session that is
    being read every few seconds (the ward board polls) from writing a row on
    every request, while keeping the idle window accurate to the heartbeat.
    """
    if as_utc(user_session.last_seen_at) + timedelta(
        seconds=heartbeat_seconds
    ) <= now:
        user_session.last_seen_at = now
        return True
    return False


def unlock_is_blocked(user_session: UserSession, now: datetime) -> bool:
    """True while a run of wrong passwords is still being cooled down."""
    blocked_until = user_session.unlock_blocked_until
    return blocked_until is not None and as_utc(blocked_until) > now


def record_failed_unlock(
    user_session: UserSession,
    max_attempts: int,
    lockout_seconds: int,
    now: datetime,
) -> None:
    """Count one wrong password and start a lockout at the threshold."""
    user_session.unlock_attempts += 1
    if user_session.unlock_attempts >= max_attempts:
        user_session.unlock_blocked_until = now + timedelta(
            seconds=lockout_seconds
        )


def unlock(user_session: UserSession, now: datetime) -> None:
    """Resume the session: clear the lock and the failed-attempt window."""
    user_session.locked_at = None
    user_session.unlock_attempts = 0
    user_session.unlock_blocked_until = None
    user_session.last_seen_at = now
