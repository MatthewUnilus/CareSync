from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, load_session
from app.models import User, UserSession
from app.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    UnlockRequest,
    UserResponse,
)
from app.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from app.session_lock import (
    is_expired,
    lock,
    record_failed_unlock,
    unlock,
    unlock_is_blocked,
)
from app.timeutils import utc_now

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> User:
    settings = request.app.state.settings
    email = payload.email.strip().lower()

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    token = new_session_token()
    now = utc_now()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            last_seen_at=now,
        )
    )
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
        path="/",
    )
    return user


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    return user


@router.post("/lock", status_code=status.HTTP_204_NO_CONTENT)
def lock_session(request: Request, db: DbSession) -> Response:
    """Lock this session deliberately, without ending it.

    The session row survives and the cookie stays, so the tablet shows the
    lock rather than the sign-in screen and unlocking is a credential check on
    the same session. The lock is enforced server-side by
    ``deps.get_current_session`` from the next request onward.
    """
    user_session = load_session(request, db)
    if user_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if user_session.locked_at is None:
        lock(user_session, utc_now())
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/unlock", response_model=UserResponse)
def unlock_session(
    payload: UnlockRequest,
    request: Request,
    db: DbSession,
) -> User:
    """Resume a locked session after re-entering the credential.

    This is a credential check on the existing session, not a fresh sign-in:
    the token is unchanged, so the session that was there before the lock is
    the one that continues. Repeated wrong passwords are rate-limited on the
    session row, so a locked tablet cannot be used as a guessing surface.
    """
    settings = request.app.state.settings
    user_session = load_session(request, db)
    now = utc_now()

    if user_session is None or is_expired(user_session, now):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if unlock_is_blocked(user_session, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many unlock attempts. Try again shortly.",
        )

    user = user_session.user
    if not verify_password(user.password_hash, payload.password):
        record_failed_unlock(
            user_session,
            settings.session_unlock_max_attempts,
            settings.session_unlock_lockout_seconds,
            now,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    unlock(user_session, now)
    db.commit()
    return user


@router.post("/switch-user", status_code=status.HTTP_204_NO_CONTENT)
def switch_user(
    request: Request,
    response: Response,
    db: DbSession,
) -> Response:
    """Hand the tablet to a different person: sign out and return to sign-in.

    Deliberately the same effect as logout. It exists as its own action
    because the intent differs: a nurse switching user wants the session
    gone and the sign-in screen back, not a locked session.
    """
    _end_session(request, db)
    response.delete_cookie(key=request.app.state.settings.session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _end_session(request: Request, db: DbSession) -> None:
    user_session = load_session(request, db)
    if user_session is not None:
        db.delete(user_session)
        db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
) -> Response:
    settings = request.app.state.settings
    _end_session(request, db)

    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
