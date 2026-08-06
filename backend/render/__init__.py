"""
backend/render -- arbitrary-URL screenshot + automatic element detection.

    from render import capture_page
    result = capture_page("https://example.com")
    result.layout   # element_id -> {bbox, importance, type}

The layout comes out in exactly the format backend/attribution.build_ui_config
accepts and backend/reports/heatmap_stub.py renders, so a URL session is
indistinguishable from a fixed test-UI session everywhere downstream.

Auto-detected labels are heuristics, not design intent -- see classify.py.
Every capture reports `low_confidence_fraction`, and backend/api surfaces it
on the report rather than presenting guesses as facts.

Relative imports and the sys.path line for the same reason as the other
backend packages: several of them define a schemas.py.
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from .capture import (                       # noqa: E402
    DEFAULT_VIEWPORT,
    MAX_ELEMENTS,
    CaptureResult,
    RenderUnavailable,
    capture_page,
    render_available,
)
from .classify import classify, classify_importance, classify_type   # noqa: E402
from .routes import router                   # noqa: E402

__all__ = [
    "router",
    "capture_page",
    "CaptureResult",
    "RenderUnavailable",
    "render_available",
    "classify",
    "classify_type",
    "classify_importance",
    "DEFAULT_VIEWPORT",
    "MAX_ELEMENTS",
]
