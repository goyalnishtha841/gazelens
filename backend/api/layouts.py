"""
layouts.py

Element bounding boxes + metadata per test page.

TODO(test_uis): this is INTERIM. The real layouts belong with the 5 test UI
pages in test_uis/ (a separate task) as a config sitting next to each page's
HTML, so the boxes and the markup can never drift apart. Everything here is
keyed by ui_page, so moving to that source is a change to `layout_for()` and
nothing else.

Geometry matches backend/reports/heatmap_stub.py's DEMO_LAYOUTS and the
element ids/importance/type labels match backend/agents/mock_sessions.py, so
a real session produces metrics directly comparable to the mock data the
agent chain was built and tested against.

Format is what backend/attribution.build_ui_config accepts:
element_id -> {"bbox": (x, y, w, h) normalised, "importance": ..., "type": ...}
"""

from typing import Dict, Optional, Tuple

TEST_UI_LAYOUTS: Dict[str, dict] = {
    "ecommerce_product_page": {
        "nav_bar": {"bbox": (0.05, 0.03, 0.90, 0.08), "importance": "low", "type": "nav"},
        "product_image": {"bbox": (0.05, 0.16, 0.40, 0.55), "importance": "medium", "type": "image"},
        "product_title": {"bbox": (0.50, 0.16, 0.45, 0.14), "importance": "medium", "type": "text"},
        "checkout_button": {"bbox": (0.50, 0.38, 0.28, 0.10), "importance": "high", "type": "CTA"},
    },
    "form_page": {
        "promo_banner": {"bbox": (0.10, 0.04, 0.80, 0.09), "importance": "low", "type": "non-interactive"},
        "name_field": {"bbox": (0.20, 0.20, 0.60, 0.09), "importance": "medium", "type": "text"},
        "email_field": {"bbox": (0.20, 0.34, 0.60, 0.09), "importance": "medium", "type": "text"},
        "helper_text": {"bbox": (0.20, 0.46, 0.60, 0.05), "importance": "low", "type": "text"},
        "submit_button": {"bbox": (0.35, 0.60, 0.30, 0.10), "importance": "high", "type": "CTA"},
    },
    "dashboard_page": {
        "nav_menu": {"bbox": (0.05, 0.03, 0.90, 0.06), "importance": "low", "type": "nav"},
        "chart_widget": {"bbox": (0.05, 0.13, 0.55, 0.48), "importance": "medium", "type": "image"},
        "sidebar_ad": {"bbox": (0.65, 0.13, 0.30, 0.14), "importance": "low", "type": "non-interactive"},
        "promo_widget": {"bbox": (0.65, 0.31, 0.30, 0.14), "importance": "medium", "type": "non-interactive"},
        "help_icon": {"bbox": (0.87, 0.03, 0.08, 0.05), "importance": "low", "type": "non-interactive"},
        "cta_primary": {"bbox": (0.05, 0.66, 0.25, 0.09), "importance": "high", "type": "CTA"},
        "cta_secondary": {"bbox": (0.33, 0.66, 0.25, 0.09), "importance": "high", "type": "CTA"},
        "footer_link": {"bbox": (0.05, 0.90, 0.20, 0.04), "importance": "low", "type": "text"},
    },
}

AVAILABLE_TEST_UIS = tuple(TEST_UI_LAYOUTS)


# TODO(render): backend/render is supposed to screenshot an arbitrary URL and
# auto-detect its elements. It has never been pushed to this repo, so a
# mode="url" session gets this instead: a generic page skeleton, so the
# pipeline runs end to end and the endpoint shape is final, but the numbers
# describe boxes nobody detected.
#
# Every session using it is marked layout_is_placeholder=True and its report
# carries a warning. That flag is the thing to grep for when render/ lands.
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
    "TEST_UI_LAYOUTS",
    "AVAILABLE_TEST_UIS",
    "PLACEHOLDER_URL_LAYOUT",
    "UnknownTestUI",
    "layout_for",
]
