"""
deps.py

Shared FastAPI dependencies: the DB session and the authenticated user.

`get_current_user` is the single place ownership is established. Every route
that touches a session depends on it, and every session lookup goes through
`owned_session()` below -- so there is one function to audit for "can user A
read user B's data", rather than a scoping check repeated per route that
someone will eventually forget.

Calibration sessions (backend/calibration's JSON store) and the gaze models
trained from them (keyed by the same id) get the same treatment through
`owned_calibration()` / `owned_calibration_ids()`.
"""

from typing import Optional, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
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


# ----------------------------------------------------------------------
# Calibration ownership
#
# A calibration session records its creator's user id (owner_id) from the
# moment POST /api/calibration/sessions makes it. Files written before that
# field existed have owner_id None. Those LEGACY calibrations are not public:
# one is reachable only by a user who already linked it to one of their own
# /api/sessions sessions -- the only record of whose data it is. A legacy
# calibration nobody linked is unreachable over the API (it stays on disk;
# set "owner_id" in its JSON by hand to hand it to someone).
#
# Gaze models are keyed by their calibration session id, so a model belongs
# to whoever owns its calibration. A model whose calibration was deleted has
# no provable owner and is treated as not found.


def _linked_calibration_ids(user: User, db: Optional[DBSession]) -> Set[str]:
    if db is None:
        return set()
    rows = db.scalars(
        select(SessionModel.calibration_session_id).where(
            SessionModel.user_id == user.id,
            SessionModel.calibration_session_id.is_not(None),
        )
    )
    return set(rows)


def owned_calibration(calibration_session_id: str, user: User, db: Optional[DBSession]):
    """Fetch a calibration session belonging to `user`, or raise 404.

    404 for someone else's, for the same reason as owned_session().
    `db` is only consulted for legacy (ownerless) calibrations.
    """
    # Imported here, not at module level: backend/calibration's router
    # imports this module, so a top-level import would be circular.
    from calibration.storage import SessionNotFound, get_store

    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"calibration session {calibration_session_id!r} not found",
    )
    try:
        calibration = get_store().get(calibration_session_id)
    except SessionNotFound:
        raise not_found from None

    if calibration.owner_id == user.id:
        return calibration
    if (calibration.owner_id is None
            and calibration_session_id in _linked_calibration_ids(user, db)):
        return calibration
    raise not_found


def owned_calibration_ids(user: User, db: Optional[DBSession]) -> Set[str]:
    """Every calibration session id `user` may see -- for the list endpoints."""
    from calibration.storage import get_store

    linked = _linked_calibration_ids(user, db)
    return {
        s["session_id"] for s in get_store().list_sessions()
        if s.get("owner_id") == user.id
        or (s.get("owner_id") is None and s["session_id"] in linked)
    }


__all__ = [
    "get_current_user",
    "owned_session",
    "owned_calibration",
    "owned_calibration_ids",
    "get_db",
    "oauth2_scheme",
]
