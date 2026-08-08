"""
layouts.py

Element bounding boxes + metadata per test page.

Loaded from test_uis/<ui_page>/elements.json -- a config sitting next to each
page's real HTML (test_uis/<ui_page>/index.html), so the boxes and the markup
can't drift apart. Previously this held the boxes as a hardcoded dict here
(TEST_UI_LAYOUTS) with no real page behind them; test_uis/ now exists, so
`_load_test_uis()` is the only thing that changed to read from it instead.

Geometry for ecommerce_product_page/form_page/dashboard_page matches
backend/reports/heatmap_stub.py's DEMO_LAYOUTS and the element ids/
importance/type labels match backend/agents/mock_sessions.py, so a real
session on those three still produces metrics directly comparable to the
mock data the agent chain was built and tested against. login_page and
article_page never had mock data or a layout defined anywhere -- their
element sets in test_uis/ are new.

Format is what backend/attribution.build_ui_config accepts:
element_id -> {"bbox": [x, y, w, h] normalised, "importance": ..., "type": ...}
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

TEST_UIS_DIR = Path(__file__).resolve().parent.parent.parent / "test_uis"


def _load_test_uis() -> Dict[str, dict]:
    """test_uis/<page>/elements.json -> {ui_page: {element_id: {bbox, importance, type}}}.

    `label` is dropped here -- it's read straight off elements.json by the
    static-served index.html for display and isn't part of the attribution
    contract (build_ui_config doesn't accept it), so keeping it in the dict
    handed downstream would be dead weight, not a mismatch worth adapting.
    Read once at import time: these are checked-in files, not something that
    changes while the process is running.
    """
    layouts: Dict[str, dict] = {}
    if not TEST_UIS_DIR.is_dir():
        return layouts
    for page_dir in sorted(TEST_UIS_DIR.iterdir()):
        config_path = page_dir / "elements.json"
        if not page_dir.is_dir() or not config_path.exists():
            continue
        raw = json.loads(config_path.read_text())
        layouts[page_dir.name] = {
            element_id: {
                "bbox": tuple(info["bbox"]),
                "importance": info["importance"],
                "type": info["type"],
            }
            for element_id, info in raw.items()
        }
    return layouts


TEST_UI_LAYOUTS: Dict[str, dict] = _load_test_uis()
AVAILABLE_TEST_UIS = tuple(TEST_UI_LAYOUTS)


# TODO(render): backend/render screenshots an arbitrary URL and auto-detects
# elements -- it IS in this repo now (see api/pipeline.capture_page), so this
# placeholder is only reached when a capture fails (page down, consent wall,
# timeout), not the general case it used to be.
#
# Every session using it is marked layout_is_placeholder=True and its report
# carries a warning. That flag is the thing to grep for.
PLACEHOLDER_URL_LAYOUT: dict = {
    "page_header": {"bbox": (0.00, 0.00, 1.00, 0.12), "importance": "low", "type": "nav"},
    "main_content": {"bbox": (0.05, 0.14, 0.60, 0.60), "importance": "medium", "type": "text"},
    "sidebar": {"bbox": (0.68, 0.14, 0.28, 0.60), "importance": "low", "type": "non-interactive"},
    "primary_cta": {"bbox": (0.05, 0.78, 0.24, 0.09), "importance": "high", "type": "CTA"},
    "page_footer": {"bbox": (0.00, 0.90, 1.00, 0.10), "importance": "low", "type": "text"},
}


class UnknownTestUI(KeyError):
    """No layout for that ui_page."""


def layout_for(
    mode: str,
    ui_page: Optional[str],
    target_url: Optional[str] = None,
) -> Tuple[str, dict, bool]:
    """Resolve a session's element layout.

    Returns (ui_page, layout, is_placeholder). `is_placeholder` is True when
    the boxes were not derived from the page actually shown -- the caller is
    expected to record it on the session and surface it on the report.
    """
    if mode == "url":
        return ("url_placeholder", dict(PLACEHOLDER_URL_LAYOUT), True)

    if not ui_page or ui_page not in TEST_UI_LAYOUTS:
        raise UnknownTestUI(
            f"unknown ui_page {ui_page!r}; available: {list(AVAILABLE_TEST_UIS)}"
        )
    return (ui_page, dict(TEST_UI_LAYOUTS[ui_page]), False)


__all__ = [
    "TEST_UIS_DIR",
    "TEST_UI_LAYOUTS",
    "AVAILABLE_TEST_UIS",
    "PLACEHOLDER_URL_LAYOUT",
    "UnknownTestUI",
    "layout_for",
]
