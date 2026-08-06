"""
deps.py

Shared FastAPI dependencies: the DB session and the authenticated user.

`get_current_user` is the single place ownership is established. Every route
that touches a session depends on it, and every session lookup goes through
`owned_session()` below -- so there is one function to audit for "can user A
read user B's data", rather than a scoping check repeated per route that
someone will eventually forget.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session as DBSession

from .db import get_db
from .models import Session as SessionModel, User
from .security import decode_access_token

# auto_error=False so a missing header produces our own 401 with a useful
# message, rather than FastAPI's bare "Not authenticated".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated -- send 'Authorization: Bearer <token>' from /api/auth/login",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: DBSession = Depends(get_db),
) -> User:
    if not token:
        raise _UNAUTHENTICATED

    user_id = decode_access_token(token)
    if user_id is None:
        raise _UNAUTHENTICATED

    user = db.get(User, user_id)
    if user is None:
        # Valid signature, but the account is gone. Same 401 as a bad token:
        # a distinct error here would confirm to a holder of an old token
        # that the account once existed.
        raise _UNAUTHENTICATED
    return user


def owned_session(session_id: str, user: User, db: DBSession) -> SessionModel:
    """Fetch a session belonging to `user`, or raise 404.

    404 rather than 403 on someone else's session, deliberately: a 403 would
    confirm that the id exists, letting anyone enumerate valid session ids.
    A caller who doesn't own it should be unable to tell it apart from one
    that was never created.
    """
    session = db.get(SessionModel, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no session {session_id!r}",
        )
    return session


__all__ = ["get_current_user", "owned_session", "get_db", "oauth2_scheme"]
