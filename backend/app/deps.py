from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User, UserSession
from app.security import hash_session_token
from app.timeutils import as_utc, utc_now


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


def get_current_user(request: Request, db: DbSession) -> User:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorised()

    user_session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token),
        )
    )
    if user_session is None or as_utc(user_session.expires_at) <= utc_now():
        raise _unauthorised()

    return user_session.user


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
