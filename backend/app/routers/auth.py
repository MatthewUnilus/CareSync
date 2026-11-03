from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import User, UserSession
from app.schemas import LoginRequest, PasswordChangeRequest, UserResponse
from app.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
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
        )
    )
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return user


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
) -> Response:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        user_session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token),
            )
        )
        if user_session is not None:
            db.delete(user_session)
            db.commit()

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
