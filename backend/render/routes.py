"""
routes.py

    POST /api/render/capture    screenshot + detect elements for a URL

Thin, same as the other routers. The session API calls `capture_page()`
in-process rather than over HTTP; this endpoint exists so a URL's detected
layout can be previewed before a participant is sat in front of it -- which
matters, because auto-detection is heuristic and worth eyeballing first.

SSRF NOTE: this endpoint fetches a URL the caller supplies, from the server.
Loopback and private ranges are refused (see _reject_private) so it can't be
used to reach services on the study machine's network. That check is a
guardrail, not a security boundary -- DNS can still resolve a public name to a
private address. Keep this endpoint behind auth and off the public internet.
"""

import ipaddress
import socket
from typing import Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .capture import DEFAULT_VIEWPORT, RenderUnavailable, capture_page

router = APIRouter(prefix="/api/render", tags=["render"])


class CaptureRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    viewport_width: int = Field(DEFAULT_VIEWPORT[0], ge=320, le=3840)
    viewport_height: int = Field(DEFAULT_VIEWPORT[1], ge=240, le=2160)
    timeout_ms: int = Field(30_000, ge=1_000, le=120_000)


class CaptureResponse(BaseModel):
    url: str
    final_url: str
    title: str
    viewport: List[int]
    layout: Dict[str, dict]
    detected: int
    kept: int
    below_fold_dropped: int
    too_small_dropped: int
    too_large_dropped: int
    low_confidence_fraction: float
    classification: Dict[str, dict]
    warnings: List[str]


def _reject_private(url: str) -> None:
    """Refuse loopback/private/link-local targets."""
    host = (urlparse(url).hostname or "").strip("[]")
    if not host:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"could not resolve {host!r}: {exc}",
        ) from exc

    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"refusing to fetch a private/loopback address ({addr}). "
                       f"Point this at a public URL.",
            )


@router.post("/capture", response_model=CaptureResponse)
async def capture(payload: CaptureRequest) -> CaptureResponse:
    """Screenshot a URL and detect its elements."""
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="url must start with http:// or https://",
        )
    _reject_private(payload.url)

    try:
        result = capture_page(
            payload.url,
            viewport=(payload.viewport_width, payload.viewport_height),
            timeout_ms=payload.timeout_ms,
        )
    except RenderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:            # noqa: BLE001
        # A page that won't load is the caller's problem, not a server fault.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"could not capture {payload.url}: {type(exc).__name__}: {exc}",
        ) from exc

    data = result.to_dict()
    data.pop("screenshot_path", None)
    return CaptureResponse(**data)


__all__ = ["router"]
