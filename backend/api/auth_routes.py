"""
auth_routes.py

    POST /api/auth/signup    create an account, returns a token
    POST /api/auth/login     exchange credentials for a token
    GET  /api/auth/me        the current user

Real bcrypt hashes and real JWTs. The README described this as already built,
but it had never been pushed -- see CONTRACT.md.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from .db import get_db
from .deps import get_current_user
from .models import User
from .schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from .security import (
    PasswordError,
    create_access_token,
    hash_password,
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
        password_hash = hash_password(payload.password)
    except PasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
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


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


__all__ = ["router"]
