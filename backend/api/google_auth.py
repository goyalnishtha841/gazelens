"""
google_auth.py

"Sign in with Google": verifying the ID token Google hands the browser.

The browser shows Google's own button (Google Identity Services). When the
user picks an account, Google gives the page a signed JWT -- the ID token --
and the page posts it to POST /api/auth/google. Nothing from the browser is
trusted as-is: google-auth (Google's official library) checks the token's
RS256 signature against Google's published keys, that it was issued by
accounts.google.com, that its audience is OUR client id (so a token minted
for some other site can't be replayed here), and that it hasn't expired.
Only then are its claims read, and the email is used only if Google says it
has verified it.

No client secret is involved: the ID-token flow needs only the public
client id. Google sign-in is OFF unless GOOGLE_CLIENT_ID is set -- the
endpoint then answers 404 and the web app hides the button.
"""

import os
from dataclasses import dataclass
from typing import Callable, Optional

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


def client_id() -> Optional[str]:
    """The OAuth client id from Google Cloud, or None when the feature is off."""
    return (os.environ.get("GOOGLE_CLIENT_ID") or "").strip() or None


class GoogleTokenError(ValueError):
    """The credential isn't a valid Google ID token for this app."""


@dataclass
class GoogleIdentity:
    sub: str                 # Google's stable account id -- never changes
    email: str
    name: Optional[str]


def _verify_with_google(token: str, audience: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    # Checks signature (keys fetched from Google and cached), audience,
    # expiry and issued-at. Raises ValueError on any failure.
    return id_token.verify_oauth2_token(token, google_requests.Request(), audience)


# Swappable so tests can verify against their own key instead of Google's.
_verifier: Callable[[str, str], dict] = _verify_with_google


def set_verifier(fn: Optional[Callable[[str, str], dict]]) -> None:
    global _verifier
    _verifier = fn or _verify_with_google


def verify_credential(token: str) -> GoogleIdentity:
    audience = client_id()
    if not audience:
        raise GoogleTokenError("Google sign-in is not configured")
    try:
        claims = _verifier(token, audience)
    except GoogleTokenError:
        raise
    except Exception as exc:        # noqa: BLE001 -- any library failure = bad token
        raise GoogleTokenError("Google couldn't confirm this sign-in") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("token was not issued by Google")
    if claims.get("aud") != audience:
        raise GoogleTokenError("token was issued for a different app")
    email = (claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") not in (True, "true"):
        raise GoogleTokenError("Google hasn't verified this account's email")
    if not claims.get("sub"):
        raise GoogleTokenError("token has no account id")

    name = " ".join((claims.get("name") or "").split())[:80] or None
    return GoogleIdentity(sub=str(claims["sub"]), email=email, name=name)


__all__ = ["GoogleIdentity", "GoogleTokenError", "client_id", "set_verifier",
           "verify_credential"]
