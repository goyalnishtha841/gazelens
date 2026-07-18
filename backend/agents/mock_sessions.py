"""
mock_sessions.py

Hand-authored session data matching the SessionMetrics contract.
Use these to build and test the entire agent chain WITHOUT waiting on
the CV/gaze pipeline. When the real metrics module is ready, swap these
for real SessionMetrics objects -- the agents don't know the difference.

Three scenarios on purpose:
  1. clean_session      -- CTA works fine, nothing to flag
  2. ignored_cta_session -- the checkout button is basically invisible
  3. scattered_session   -- attention bounces around, layout confusion
"""

from schemas import SessionMetrics


clean_session = SessionMetrics(
    session_id="mock_clean_01",
    ui_page="ecommerce_product_page",
    dwell_time={
        "checkout_button": 4.2,
        "product_image": 6.1,
        "product_title": 2.8,
        "nav_bar": 1.1,
    },
    ttff={
        "checkout_button": 2.1,
        "product_image": 0.4,
        "product_title": 0.9,
        "nav_bar": 3.0,
    },
    fixation_count={"checkout_button": 5, "product_image": 8, "product_title": 4, "nav_bar": 2},
    revisit_count={"checkout_button": 1, "product_image": 2, "product_title": 0, "nav_bar": 0},
    total_gaze_time=20.0,
    scanpath=["product_image", "product_title", "checkout_button", "product_image", "checkout_button"],
    element_importance={"checkout_button": "high", "product_image": "medium", "product_title": "medium", "nav_bar": "low"},
    element_type={"checkout_button": "CTA", "product_image": "image", "product_title": "text", "nav_bar": "nav"},
)


ignored_cta_session = SessionMetrics(
    session_id="mock_ignored_cta_02",
    ui_page="ecommerce_product_page",
    dwell_time={
        "checkout_button": 0.4,     # very low
        "product_image": 9.5,
        "product_title": 3.0,
        "nav_bar": 2.1,
    },
    ttff={
        "checkout_button": 8.4,     # discovered late
        "product_image": 0.3,
        "product_title": 0.8,
        "nav_bar": 1.5,
    },
    fixation_count={"checkout_button": 1, "product_image": 12, "product_title": 5, "nav_bar": 3},
    revisit_count={"checkout_button": 0, "product_image": 4, "product_title": 1, "nav_bar": 1},
    total_gaze_time=20.0,
    scanpath=["product_image", "product_image", "product_title", "product_image", "nav_bar", "checkout_button"],
    element_importance={"checkout_button": "high", "product_image": "medium", "product_title": "medium", "nav_bar": "low"},
    element_type={"checkout_button": "CTA", "product_image": "image", "product_title": "text", "nav_bar": "nav"},
)


scattered_session = SessionMetrics(
    session_id="mock_scattered_03",
    ui_page="form_page",
    dwell_time={
        "submit_button": 1.0,
        "name_field": 1.2,
        "email_field": 1.1,
        "promo_banner": 3.4,       # non-interactive element getting attention
        "helper_text": 0.5,
    },
    ttff={
        "submit_button": 6.2,
        "name_field": 0.5,
        "email_field": 1.8,
        "promo_banner": 0.2,
        "helper_text": 4.0,
    },
    fixation_count={"submit_button": 2, "name_field": 3, "email_field": 3, "promo_banner": 9, "helper_text": 1},
    revisit_count={"submit_button": 0, "name_field": 1, "email_field": 1, "promo_banner": 5, "helper_text": 0},
    total_gaze_time=15.0,
    scanpath=[
        "promo_banner", "name_field", "promo_banner", "email_field",
        "promo_banner", "helper_text", "promo_banner", "name_field",
        "promo_banner", "submit_button",
    ],
    element_importance={"submit_button": "high", "name_field": "medium", "email_field": "medium", "promo_banner": "low", "helper_text": "low"},
    element_type={"submit_button": "CTA", "name_field": "text", "email_field": "text", "promo_banner": "non-interactive", "helper_text": "text"},
)


busy_dashboard_session = SessionMetrics(
    session_id="mock_busy_dashboard_04",
    ui_page="dashboard_page",
    dwell_time={
        "cta_primary": 0.8,
        "cta_secondary": 1.0,
        "sidebar_ad": 4.5,
        "promo_widget": 5.0,
        "nav_menu": 2.0,
        "chart_widget": 12.0,
        "footer_link": 1.5,
        "help_icon": 3.2,
    },
    ttff={
        "cta_primary": 9.5,
        "cta_secondary": 7.2,
        "sidebar_ad": 1.0,
        "promo_widget": 1.5,
        "nav_menu": 0.3,
        "chart_widget": 0.5,
        "footer_link": 8.0,
        "help_icon": 4.0,
    },
    fixation_count={
        "cta_primary": 2, "cta_secondary": 2, "sidebar_ad": 7, "promo_widget": 9,
        "nav_menu": 4, "chart_widget": 15, "footer_link": 3, "help_icon": 6,
    },
    revisit_count={
        "cta_primary": 0, "cta_secondary": 0, "sidebar_ad": 3, "promo_widget": 4,
        "nav_menu": 2, "chart_widget": 8, "footer_link": 1, "help_icon": 3,
    },
    total_gaze_time=30.0,
    scanpath=[
        "chart_widget", "nav_menu", "chart_widget", "sidebar_ad",
        "chart_widget", "promo_widget", "chart_widget", "help_icon",
        "chart_widget", "footer_link", "chart_widget", "cta_secondary",
        "chart_widget", "cta_primary",
    ],
    element_importance={
        "cta_primary": "high", "cta_secondary": "high", "sidebar_ad": "low",
        "promo_widget": "medium", "nav_menu": "low", "chart_widget": "medium",
        "footer_link": "low", "help_icon": "low",
    },
    element_type={
        "cta_primary": "CTA", "cta_secondary": "CTA", "sidebar_ad": "non-interactive",
        "promo_widget": "non-interactive", "nav_menu": "nav", "chart_widget": "image",
        "footer_link": "text", "help_icon": "non-interactive",
    },
)


ALL_MOCK_SESSIONS = [clean_session, ignored_cta_session, scattered_session, busy_dashboard_session]