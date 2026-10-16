"""
ratelimit.py

Failed-login throttling for POST /api/auth/login.

In-memory and per process, deliberately. A password-guessing client gets
GAZELENS_LOGIN_MAX_FAILURES wrong guesses per GAZELENS_LOGIN_WINDOW_SECONDS
from one IP, then a 429 with Retry-After until the oldest failure ages out.
A successful login clears that IP's count, so a participant who mistypes a
couple of times isn't punished afterwards.

Why not Redis / slowapi: the API runs as one uvicorn process against SQLite,
so there is exactly one place to count. If it ever runs as several workers,
each keeps its own count -- the effective limit becomes workers x max, still
a limit -- and that is the point to move this into a shared store.

Client IP comes from request.client, which is the real client only when
uvicorn runs with --proxy-headers behind a trusted proxy (the Dockerfile
does). Without that, every request behind a load balancer shares one IP and
one bad actor locks everyone out -- which is why the default is generous.
"""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

MAX_FAILURES = int(os.environ.get("GAZELENS_LOGIN_MAX_FAILURES", "10"))
WINDOW_SECONDS = float(os.environ.get("GAZELENS_LOGIN_WINDOW_SECONDS", "900"))


class FailureLimiter:
    """Sliding-window count of failures per key."""

    def __init__(self, max_failures: int, window_seconds: float, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        q = self._failures[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until this key may try again; 0 if it may now."""
        if self.max_failures <= 0:
            return 0
        with self._lock:
            now = self._clock()
            q = self._prune(key, now)
            if len(q) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - q[0]) + 0.999))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = FailureLimiter(MAX_FAILURES, WINDOW_SECONDS)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def login_rate_limit(request: Request):
    """Router dependency: refuse throttled IPs, count 401s, clear on success.

    A yield dependency rather than code in the route body, so the route's
    signature is unchanged and the tests that call login() directly still can.
    """
    key = _client_key(request)
    wait = login_limiter.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed login attempts; try again later",
            headers={"Retry-After": str(wait)},
        )
    try:
        yield
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_limiter.record_failure(key)
        raise
    else:
        login_limiter.reset(key)


__all__ = ["FailureLimiter", "login_limiter", "login_rate_limit"]
