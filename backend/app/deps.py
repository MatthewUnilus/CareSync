from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User, UserSession
from app.security import hash_session_token
from app.session_lock import is_expired, is_locked, lock, touch
from app.timeutils import utc_now


def get_db(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def _unauthorised() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def _locked() -> HTTPException:
    """A locked session is refused, but not signed out.

    423 rather than 401: the client must be able to tell "locked, unlock me"
    from "signed out, sign in again". The session row survives, so unlocking
    is a credential check rather than a fresh sign-in.
    """
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail="Session locked",
    )


def load_session(request: Request, db: Session) -> UserSession | None:
    """The session row named by the request's cookie, or None.

    Reads only; the caller decides what an absent or expired row means.
    """
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token),
        )
    )


def get_current_session(request: Request, db: DbSession) -> UserSession:
    """The acting session, refusing an expired or locked one.

    This is where the shared-device lock is enforced: a locked session (locked
    deliberately, or idle past the configured window) cannot act on any route
    that depends on it. The lock is evaluated on the request, never on a timer.
    """
    settings = request.app.state.settings
    user_session = load_session(request, db)
    now = utc_now()

    if user_session is None or is_expired(user_session, now):
        raise _unauthorised()

    if is_locked(user_session, settings.session_idle_seconds, now):
        # Persist the derived lock so the row records when it took effect and
        # a later read sees the same state, then refuse this request.
        if user_session.locked_at is None:
            lock(user_session, now)
            db.commit()
        raise _locked()

    if touch(user_session, settings.session_heartbeat_seconds, now):
        db.commit()

    return user_session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


def get_current_user(session: CurrentSession) -> User:
    return session.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed_roles: Role):
    def dependency(user: CurrentUser) -> User:
        try:
            role = Role(user.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not permitted",
            ) from None
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role not permitted",
            )
        return user

    return dependency
