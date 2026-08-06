"""
classify.py

Turns a detected DOM element into the two labels the agent chain needs:
`type` and `importance`.

WHY THIS FILE IS THE RISKY PART
-------------------------------
backend/agents branches on these exact strings. Only "CTA" elements get the
TTFF and dwell-visibility rules; only "non-interactive" ones can trigger the
misleading-affordance rule; only "high" importance ones can be reported as
ignored. So a misclassification doesn't produce a slightly-off report -- it
silently exempts an element from the rules that would have flagged it, or
invents a finding about something that was never meant to be clicked.

Hand-authored test_uis/ configs are labelled by a human who knows the design
intent. Nothing here can know that. These are heuristics over tag names, ARIA
roles and geometry, and they are wrong sometimes -- a <div> styled as a button
reads as non-interactive, a decorative <a> reads as a CTA.

Every element therefore carries `confidence` and `classified_by`, and the
capture as a whole reports how much of the page it was unsure about. That is
the difference between "auto-detected, treat with care" and quietly passing
guesses off as design intent.
"""

from typing import Dict, Tuple

# Vocabularies from backend/agents/schemas.py. Not extended here.
TYPE_CTA = "CTA"
TYPE_TEXT = "text"
TYPE_IMAGE = "image"
TYPE_NAV = "nav"
TYPE_NON_INTERACTIVE = "non-interactive"

IMPORTANCE_HIGH = "high"
IMPORTANCE_MEDIUM = "medium"
IMPORTANCE_LOW = "low"

# Tags that are a call to action by their nature.
_CTA_TAGS = {"button"}
_CTA_INPUT_TYPES = {"submit", "button", "image"}
_CTA_ROLES = {"button", "link", "menuitem"}

_NAV_TAGS = {"nav", "header", "footer"}
_NAV_ROLES = {"navigation", "menubar", "banner", "contentinfo"}

_IMAGE_TAGS = {"img", "svg", "video", "canvas", "picture", "figure"}
_IMAGE_ROLES = {"img", "figure"}

_TEXT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "label",
              "li", "blockquote", "figcaption", "legend"}

_FORM_TAGS = {"input", "select", "textarea"}

# Class-name fragments that mark a call to action in most CSS conventions.
# Weak evidence on their own -- used only to lift a link or a div, and always
# recorded in classified_by so a reader can see the guess was made.
_CTA_CLASS_HINTS = ("btn", "button", "cta", "submit", "buy", "checkout",
                    "signup", "sign-up", "add-to-cart", "purchase")


def classify_type(el: Dict) -> Tuple[str, float, str]:
    """DOM element -> (type, confidence, why).

    `el` carries tag, role, type attribute, class list, clickability and
    geometry, as collected by capture.py's in-page script.
    """
    tag = (el.get("tag") or "").lower()
    role = (el.get("role") or "").lower()
    input_type = (el.get("input_type") or "").lower()
    classes = " ".join(el.get("classes") or []).lower()
    has_click = bool(el.get("has_click_handler"))

    # --- unambiguous: the tag or role says exactly what it is ---
    if tag in _CTA_TAGS or role in _CTA_ROLES and role == "button":
        return TYPE_CTA, 0.95, f"tag={tag or role}"
    if tag == "input" and input_type in _CTA_INPUT_TYPES:
        return TYPE_CTA, 0.95, f"input[type={input_type}]"

    if tag in _NAV_TAGS or role in _NAV_ROLES:
        return TYPE_NAV, 0.9, f"tag={tag or role}"

    if tag in _IMAGE_TAGS or role in _IMAGE_ROLES:
        return TYPE_IMAGE, 0.9, f"tag={tag or role}"

    if tag in _FORM_TAGS:
        # A text field is something to read and fill, not a call to action.
        return TYPE_TEXT, 0.85, f"form field <{tag}>"

    # --- links: the genuinely ambiguous case ---
    # An <a> can be the primary CTA ("Buy now") or a footer legal link. Class
    # names are the only signal available without understanding the design.
    if tag == "a" or role == "link":
        if any(h in classes for h in _CTA_CLASS_HINTS):
            return TYPE_CTA, 0.6, f"<a> with CTA-ish class ({classes[:40]})"
        if el.get("in_nav"):
            return TYPE_NAV, 0.7, "<a> inside a nav landmark"
        return TYPE_TEXT, 0.5, "<a> with no CTA signal -- could be either"

    if tag in _TEXT_TAGS:
        return TYPE_TEXT, 0.85, f"tag={tag}"

    # --- containers and divs ---
    if any(h in classes for h in _CTA_CLASS_HINTS):
        return TYPE_CTA, 0.45, f"<{tag}> with CTA-ish class -- weak signal"
    if has_click:
        return TYPE_CTA, 0.4, f"<{tag}> with a click handler -- weak signal"

    # Default is the inert label, matching backend/api/layouts.py: a wrong
    # "CTA" invents poor-visibility findings for every unlabelled box, whereas
    # a wrong "non-interactive" needs 5+ fixations before it says anything.
    return TYPE_NON_INTERACTIVE, 0.3, f"<{tag}> -- no signal, defaulted"


def classify_importance(el: Dict, element_type: str,
                        viewport: Tuple[int, int]) -> Tuple[str, str]:
    """(importance, why). Geometry-aware, because position carries intent."""
    _, vh = viewport
    box = el.get("box") or {}
    top = float(box.get("y", 0))
    area_frac = float(el.get("area_fraction", 0.0))
    above_fold = top < vh

    if element_type == TYPE_CTA:
        # The design's primary action is what the study is usually about, and
        # a CTA nobody looked at is the finding the agents exist to produce.
        if above_fold:
            return IMPORTANCE_HIGH, "CTA above the fold"
        return IMPORTANCE_MEDIUM, "CTA below the fold"

    if element_type == TYPE_NAV:
        return IMPORTANCE_LOW, "navigation chrome"

    if element_type == TYPE_IMAGE:
        if area_frac > 0.10 and above_fold:
            return IMPORTANCE_MEDIUM, "large above-the-fold image"
        return IMPORTANCE_LOW, "secondary image"

    if element_type == TYPE_TEXT:
        if (el.get("tag") or "").lower() in {"h1", "h2"} and above_fold:
            return IMPORTANCE_MEDIUM, "leading heading"
        return IMPORTANCE_LOW, "body text"

    return IMPORTANCE_LOW, "no importance signal"


def element_id_for(el: Dict, taken: set) -> str:
    """A stable, readable id.

    Prefers the author's own id/name/aria-label -- those describe the element
    the way the team already talks about it, which is what a UX report should
    say. Falls back to tag + text, then to a counter.
    """
    import re

    # Element ids are printed verbatim in the UX report and on the heatmap.
    # A 60-character id built from a footer's entire link list is technically
    # unique and completely unreadable, so text-derived ids are cut to the
    # first few words rather than the first N characters -- truncating
    # mid-word reads like corruption.
    MAX_WORDS = 4
    MAX_LEN = 32

    def _slug(value: str, max_words: int = 99) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
        if not s:
            return ""
        s = "_".join(s.split("_")[:max_words])
        return s[:MAX_LEN].rstrip("_")

    tag = (el.get("tag") or "el").lower()
    for source in (el.get("dom_id"), el.get("aria_label"), el.get("name")):
        slug = _slug(source or "")
        if slug and slug not in taken:
            return slug

    text_slug = _slug(el.get("text") or "", max_words=MAX_WORDS)
    base = f"{tag}_{text_slug}" if text_slug else tag

    candidate = base
    n = 2
    while candidate in taken or not candidate:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def classify(el: Dict, viewport: Tuple[int, int], taken: set) -> Dict:
    """Full classification for one element."""
    element_type, confidence, type_why = classify_type(el)
    importance, imp_why = classify_importance(el, element_type, viewport)
    element_id = element_id_for(el, taken)

    return {
        "element_id": element_id,
        "type": element_type,
        "importance": importance,
        "confidence": round(confidence, 2),
        "classified_by": f"type: {type_why}; importance: {imp_why}",
    }


__all__ = [
    "classify",
    "classify_type",
    "classify_importance",
    "element_id_for",
    "TYPE_CTA",
    "TYPE_TEXT",
    "TYPE_IMAGE",
    "TYPE_NAV",
    "TYPE_NON_INTERACTIVE",
]
