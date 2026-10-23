"""
auth_routes.py

    POST /api/auth/signup    create an account, returns a token
    POST /api/auth/login     exchange credentials for a token
    POST /api/auth/google    sign in or sign up with a Google ID token
    GET  /api/auth/config    which sign-in options this server offers
    GET  /api/auth/me        the current user

Real bcrypt hashes and real JWTs. The README described this as already built,
but it had never been pushed -- see CONTRACT.md.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from .db import get_db
from .deps import get_current_user
from .models import User
from .google_auth import GoogleTokenError, client_id as google_client_id, verify_credential
from .ratelimit import login_rate_limit
from .schemas import (
    AuthConfigResponse,
    GoogleLoginRequest,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from .security import (
    PasswordError,
    create_access_token,
    hash_password,
    validate_new_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _normalise_email(email: str) -> str:
    # Stored lowercase so Alice@x.com and alice@x.com can't become two
    # accounts that each think they own the other's sessions.
    return email.strip().lower()


@router.post("/signup", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: DBSession = Depends(get_db)) -> TokenResponse:
    email = _normalise_email(payload.email)

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with that email already exists",
        )

    try:
        validate_new_password(payload.password, email)
        password_hash = hash_password(payload.password)
    except PasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user = User(email=email, full_name=payload.full_name, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse,
             dependencies=[Depends(login_rate_limit)])
async def login(payload: LoginRequest, db: DBSession = Depends(get_db)) -> TokenResponse:
    email = _normalise_email(payload.email)
    user = db.query(User).filter(User.email == email).first()

    # One message and one code for both "no such account" and "wrong
    # password". Distinguishing them turns this endpoint into a way to
    # enumerate which emails have accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    # The client id is public by design (it is in every page that shows the
    # button); serving it here means the web app needs no rebuild to enable it.
    return AuthConfigResponse(google_client_id=google_client_id())


@router.post("/google", response_model=TokenResponse,
             dependencies=[Depends(login_rate_limit)])
def google_login(payload: GoogleLoginRequest, db: DBSession = Depends(get_db)) -> TokenResponse:
    """Sign in, or create an account, with a Google ID token.

    One button for both: an unknown Google account becomes a new GazeLens
    account (named from the Google profile); a known one signs in. An
    existing password account with the same email is linked rather than
    duplicated -- Google has verified the person owns that address, which is
    the same proof a password reset email would give.

    A plain `def`: verification may fetch Google's signing keys over the
    network, so it runs in the threadpool, off the event loop.
    """
    if not google_client_id():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Google sign-in is not enabled on this server")
    try:
        identity = verify_credential(payload.credential)
    except GoogleTokenError as exc:
        # 401 so a stream of forged tokens counts against the login limiter.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc),
                            headers={"WWW-Authenticate": "Bearer"}) from exc

    user = db.query(User).filter(User.google_sub == identity.sub).first()
    if user is None:
        user = db.query(User).filter(User.email == identity.email).first()
        if user is not None and user.google_sub and user.google_sub != identity.sub:
            # That email already belongs to a different Google account.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="this email is linked to another Google account")
    if user is None:
        user = User(email=identity.email, full_name=identity.name or identity.email.split("@")[0],
                    google_sub=identity.sub, password_hash="")
        db.add(user)
    else:
        user.google_sub = identity.sub
        if not user.full_name and identity.name:
            user.full_name = identity.name
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


__all__ = ["router"]
