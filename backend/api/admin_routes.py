"""
admin_routes.py

A private, read-only admin view of who uses GazeLens and what they do.

    POST /api/admin/login              admin password -> short-lived admin token
    GET  /api/admin/overview           totals, daily activity, every user, recent events
    GET  /api/admin/users/{user_id}    one user's tests

Access model:
  * Off unless GAZELENS_ADMIN_PASSWORD is set. With it unset every route here
    answers 404, so a deployment that never configured an admin exposes
    nothing, not even that the feature exists.
  * The admin password is separate from every user account. Logging in with
    it returns a token carrying role "admin" and no user id; ordinary user
    tokens are rejected here, and admin tokens are rejected by every user
    route (their "sub" names no user).
  * Wrong passwords are throttled per IP (GAZELENS_ADMIN_MAX_FAILURES per
    GAZELENS_ADMIN_WINDOW_SECONDS), stricter than user login.
  * Read-only. Nothing here changes or deletes data, and password hashes,
    gaze streams and files are never returned.
"""

import hmac
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from .db import get_db
from .models import Session as SessionModel, User
from .ratelimit import FailureLimiter
from .security import ALGORITHM, SECRET_KEY

ADMIN_PASSWORD_ENV = "GAZELENS_ADMIN_PASSWORD"
ADMIN_TOKEN_TTL_MINUTES = int(os.environ.get("GAZELENS_ADMIN_TOKEN_TTL_MINUTES", "120"))
ADMIN_SUBJECT = "__admin__"
ADMIN_ROLE = "admin"

admin_limiter = FailureLimiter(
    int(os.environ.get("GAZELENS_ADMIN_MAX_FAILURES", "5")),
    float(os.environ.get("GAZELENS_ADMIN_WINDOW_SECONDS", "900")),
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
_bearer = OAuth2PasswordBearer(tokenUrl="/api/admin/login", auto_error=False)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="admin login required",
    headers={"WWW-Authenticate": "Bearer"},
)


def _admin_password() -> Optional[str]:
    # Read on every call so tests (and a restart-free env change) see it.
    value = os.environ.get(ADMIN_PASSWORD_ENV) or ""
    return value if value.strip() else None


def _require_enabled() -> str:
    password = _admin_password()
    if password is None:
        raise _NOT_FOUND
    return password


def create_admin_token() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": ADMIN_SUBJECT, "role": ADMIN_ROLE, "iat": now,
         "exp": now + timedelta(minutes=ADMIN_TOKEN_TTL_MINUTES)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def require_admin(token: Optional[str] = Depends(_bearer)) -> None:
    _require_enabled()
    if not token:
        raise _UNAUTHORIZED
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise _UNAUTHORIZED from None
    if payload.get("role") != ADMIN_ROLE or payload.get("sub") != ADMIN_SUBJECT:
        raise _UNAUTHORIZED


# ----------------------------------------------------------------------
# login


class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    expected = _require_enabled()
    key = request.client.host if request.client else "unknown"

    wait = admin_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many wrong passwords; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    # constant-time comparison, so response timing says nothing about the password
    if not hmac.compare_digest(payload.password.encode("utf-8"), expected.encode("utf-8")):
        admin_limiter.record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="wrong admin password")

    admin_limiter.reset(key)
    return AdminLoginResponse(access_token=create_admin_token(),
                              expires_in_minutes=ADMIN_TOKEN_TTL_MINUTES)


# ----------------------------------------------------------------------
# data


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    dt = _aware(dt)
    return dt.isoformat() if dt else None


def _report_summary(session: SessionModel) -> Dict:
    report = session.report
    if report is None:
        return {"issues": None, "high_issues": None, "accuracy": None, "gaze_error_px": None}
    pr = report.pipeline_result or {}
    issues = pr.get("issues") or []
    quality = pr.get("quality") or {}
    return {
        "issues": len(issues),
        "high_issues": sum(1 for i in issues if i.get("severity") == "High"),
        "accuracy": quality.get("level"),
        "gaze_error_px": quality.get("gaze_error_px"),
    }


def _session_row(session: SessionModel) -> Dict:
    return {
        "id": session.id,
        "mode": session.mode,
        "ui_page": session.ui_page,
        "target_url": session.target_url,
        "status": session.status,
        "created_at": _iso(session.created_at),
        "completed_at": _iso(session.completed_at),
        "gaze_points": session.gaze_point_count,
        "error": session.error,
        **_report_summary(session),
    }


def _calibrations_by_owner(sessions: List[SessionModel]) -> Dict[str, int]:
    """Camera setups per user.

    The calibration store records an owner only for setups made since
    ownership was added, so older ones are also credited to whoever linked
    them to a test. Never fatal: the page still works if the store can't be
    read.
    """
    ids: Dict[str, set] = defaultdict(set)
    for s in sessions:
        if s.calibration_session_id:
            ids[s.user_id].add(s.calibration_session_id)
    try:
        from calibration import get_store

        for row in get_store().list_sessions():
            if row.get("owner_id") and row.get("session_id"):
                ids[row["owner_id"]].add(row["session_id"])
    except Exception:       # noqa: BLE001
        pass
    return {user_id: len(cals) for user_id, cals in ids.items()}


@router.get("/overview", dependencies=[Depends(require_admin)])
def admin_overview(db: DBSession = Depends(get_db)) -> Dict:
    users: List[User] = db.query(User).order_by(User.created_at.asc()).all()
    sessions: List[SessionModel] = db.query(SessionModel).all()
    calibrations = _calibrations_by_owner(sessions)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    by_user: Dict[str, List[SessionModel]] = defaultdict(list)
    for s in sessions:
        by_user[s.user_id].append(s)

    user_rows = []
    for u in users:
        mine = sorted(by_user.get(u.id, []), key=lambda s: _aware(s.created_at) or now)
        reported = [s for s in mine if s.report is not None]
        last = mine[-1] if mine else None
        user_rows.append({
            "id": u.id,
            "email": u.email,
            "joined_at": _iso(u.created_at),
            "last_active_at": _iso(last.created_at if last else u.created_at),
            "tests": len(mine),
            "reports": len(reported),
            "failed": sum(1 for s in mine if s.status == "failed"),
            "problems_found": sum(_report_summary(s)["issues"] or 0 for s in reported),
            "calibrations": calibrations.get(u.id, 0),
            "website_tests": sum(1 for s in mine if s.target_url),
            "last_test": _session_row(last) if last else None,
        })
    user_rows.sort(key=lambda r: r["last_active_at"] or "", reverse=True)

    # tests started per day, last 14 days (oldest first)
    days = [(now - timedelta(days=i)).date() for i in range(13, -1, -1)]
    per_day = Counter((_aware(s.created_at) or now).date() for s in sessions)
    daily = [{"date": d.isoformat(), "tests": per_day.get(d, 0)} for d in days]

    # recent events: sign-ups, tests started, reports finished or failed
    events = []
    emails = {u.id: u.email for u in users}
    for u in users:
        events.append({"at": _iso(u.created_at), "kind": "signup", "email": u.email})
    for s in sessions:
        base = {"email": emails.get(s.user_id, "?"), "session_id": s.id,
                "ui_page": s.ui_page, "target_url": s.target_url}
        events.append({"at": _iso(s.created_at), "kind": "test_started", **base})
        if s.completed_at and s.status in ("complete", "failed"):
            events.append({"at": _iso(s.completed_at),
                           "kind": "report_ready" if s.status == "complete" else "test_failed",
                           **base, **({"issues": _report_summary(s)["issues"]} if s.report else {})})
    events.sort(key=lambda e: e["at"] or "", reverse=True)

    status_mix = Counter(s.status for s in sessions)
    return {
        "generated_at": now.isoformat(),
        "totals": {
            "users": len(users),
            "new_users_7d": sum(1 for u in users if (_aware(u.created_at) or now) >= week_ago),
            "active_users_7d": len({s.user_id for s in sessions if (_aware(s.created_at) or now) >= week_ago}),
            "tests": len(sessions),
            "tests_7d": sum(1 for s in sessions if (_aware(s.created_at) or now) >= week_ago),
            "reports": sum(1 for s in sessions if s.report is not None),
            "failed": status_mix.get("failed", 0),
            "website_tests": sum(1 for s in sessions if s.target_url),
            "calibrations": sum(calibrations.values()),
            "problems_found": sum(r["problems_found"] for r in user_rows),
        },
        "status_mix": dict(status_mix),
        "daily": daily,
        "users": user_rows,
        "events": events[:40],
    }


@router.get("/users/{user_id}", dependencies=[Depends(require_admin)])
def admin_user(user_id: str, db: DBSession = Depends(get_db)) -> Dict:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no user {user_id!r}")
    sessions = (db.query(SessionModel).filter(SessionModel.user_id == user_id)
                .order_by(SessionModel.created_at.desc()).all())
    setups = _calibrations_by_owner(sessions).get(user.id, 0)
    return {
        "id": user.id,
        "email": user.email,
        "joined_at": _iso(user.created_at),
        "calibrations": setups,
        "tests": [_session_row(s) for s in sessions],
    }


__all__ = ["router", "require_admin", "create_admin_token", "ADMIN_PASSWORD_ENV", "admin_limiter"]
