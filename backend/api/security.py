"""
security.py

Password hashing and JWT issue/verify.

bcrypt and PyJWT directly, rather than passlib + python-jose. Both of those
are the older FastAPI-tutorial default and both are effectively unmaintained
now; the two libraries here are small enough that the wrapper is this file.

bcrypt only hashes the first 72 BYTES of input and silently ignores the rest
in some versions -- meaning two different long passwords can collide. Newer
bcrypt raises instead. Either way it is a real edge, so passwords are length
checked before hashing rather than left to the library's mood.
"""

import os
from pathlib import Path
import secrets
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.environ.get("GAZELENS_TOKEN_TTL_MINUTES", "720"))

# bcrypt's hard limit. Enforced here so an over-long password is a clean 422
# rather than a truncation nobody notices.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


# Where a generated key is persisted when the environment doesn't supply one.
# Gitignored, like the database.
SECRET_FILE = Path(
    os.environ.get("GAZELENS_SECRET_FILE", Path(__file__).resolve().parent / ".secret_key")
)

# HS256 keys shorter than this make PyJWT warn (RFC 7518 §3.2).
MIN_SECRET_BYTES = 32


def _load_secret() -> str:
    """Signing key: environment first, then a persisted local file.

    There is deliberately no hardcoded default -- it would end up in the pilot
    deployment, where it would let anyone mint a token for any participant.

    The environment variable is still the right answer for anything deployed.
    But an unset variable used to mean a fresh random key per process, which
    logged every participant out on each restart and made the API annoying
    enough to work around badly. So a key is generated ONCE and written to a
    gitignored file with owner-only permissions; restarts then keep sessions
    alive without anyone having to remember an export.

    If the file can't be written (read-only checkout, locked-down CI) it falls
    back to the old per-process key and says so.
    """
    key = os.environ.get("GAZELENS_SECRET_KEY")
    if key:
        if len(key.encode()) < MIN_SECRET_BYTES:
            warnings.warn(
                f"GAZELENS_SECRET_KEY is only {len(key.encode())} bytes; "
                f"HS256 wants at least {MIN_SECRET_BYTES}.",
                RuntimeWarning, stacklevel=2,
            )
        return key

    try:
        if SECRET_FILE.exists():
            stored = SECRET_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored

        generated = secrets.token_urlsafe(48)
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(generated, encoding="utf-8")
        try:
            SECRET_FILE.chmod(0o600)     # best effort; a no-op on Windows
        except OSError:
            pass
        warnings.warn(
            f"GAZELENS_SECRET_KEY was not set, so a key was generated and "
            f"saved to {SECRET_FILE} (gitignored). Tokens will survive "
            f"restarts. For a deployment, set the environment variable "
            f"instead and delete that file.",
            RuntimeWarning, stacklevel=2,
        )
        return generated
    except OSError as exc:
        warnings.warn(
            f"GAZELENS_SECRET_KEY is not set and {SECRET_FILE} could not be "
            f"written ({exc}) -- falling back to a random per-process key. "
            f"Tokens will be invalidated on every restart.",
            RuntimeWarning, stacklevel=2,
        )
        return secrets.token_urlsafe(48)


SECRET_KEY = _load_secret()


class PasswordError(ValueError):
    """Password fails the basic policy."""


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordError(
            f"password must be at most {MAX_PASSWORD_BYTES} bytes "
            f"(bcrypt ignores anything beyond that, so a longer one would be "
            f"silently truncated)"
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed stored hash. False, never an exception -- a corrupted row
        # must read as "wrong password", not as a 500 that distinguishes this
        # account from every other failed login.
        return False


def create_access_token(user_id: str, ttl_minutes: Optional[int] = None) -> str:
    ttl = ACCESS_TOKEN_TTL_MINUTES if ttl_minutes is None else ttl_minutes
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(minutes=ttl),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> Optional[str]:
    """Token -> user id, or None if it isn't valid.

    Returns None rather than raising so callers can't accidentally distinguish
    expired from forged from malformed and leak that distinction to a client.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


__all__ = [
    "hash_password",
    "verify_password",
    "validate_password",
    "create_access_token",
    "decode_access_token",
    "PasswordError",
    "MIN_PASSWORD_LENGTH",
    "MAX_PASSWORD_BYTES",
    "ACCESS_TOKEN_TTL_MINUTES",
]
