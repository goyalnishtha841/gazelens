"""
capture.py

Screenshot an arbitrary URL and detect its elements, via headless Chromium.

    result = capture_page("https://example.com")
    result.layout          # element_id -> {bbox, importance, type}  <- attribution
    result.screenshot_path

The layout is emitted in exactly the format backend/attribution.build_ui_config
accepts and backend/reports/heatmap_stub.py renders, so a URL session and a
fixed test-UI session are indistinguishable downstream.

COORDINATES
-----------
Top-left origin, y down, normalised against either the viewport or the whole
scrollable document -- see `scope` on CaptureResult and CONTRACT.md.

Document scope is the default because most real pages scroll, and a
viewport-only layout silently omits everything below the fold, which reads
downstream as "nobody looked at it" rather than "it was never measured".
Document scope requires the gaze stream to carry a scroll offset per point;
backend/api/pipeline.to_document_space does that translation.

THREADING
---------
Playwright's sync API refuses to run inside an asyncio event loop, and this is
called from FastAPI request handlers. Same fix as
backend/reports/pdf_backends.py: detect a running loop and hand the work to a
worker thread.
"""

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .classify import classify

DEFAULT_VIEWPORT = (1280, 720)
DEFAULT_TIMEOUT_MS = 30_000

# Elements smaller than this fraction of the viewport are dropped. Gaze
# estimation carries ~40px of error, so a 12x12 icon cannot be attributed
# to with any confidence and would only add noise to the report.
MIN_AREA_FRACTION = 0.0015          # ~0.15% of a 1280x720 viewport

# Elements larger than this are page containers (<body>, a full-width wrapper)
# rather than things a person looks AT. attribution resolves overlap by
# smallest-box-wins, so keeping them would mostly be harmless -- but they'd
# still collect every stray gaze point as "the main content div".
MAX_AREA_FRACTION = 0.60

MAX_ELEMENTS = 40


class RenderUnavailable(RuntimeError):
    """Playwright or its Chromium build isn't installed."""


SCOPE_VIEWPORT = "viewport"
SCOPE_DOCUMENT = "document"


@dataclass
class CaptureResult:
    url: str
    final_url: str
    title: str
    viewport: Tuple[int, int]
    layout: Dict[str, dict] = field(default_factory=dict)
    screenshot_path: Optional[str] = None

    # Which coordinate system `layout` is normalised against.
    #
    #   viewport -- boxes are fractions of the visible window. Correct only if
    #               the participant never scrolls.
    #   document -- boxes are fractions of the WHOLE scrollable page. Gaze must
    #               then be translated into the same space using the scroll
    #               offset recorded with each point (see api/pipeline.py).
    #
    # attribution is agnostic: it hit-tests two [0,1] rectangles and does not
    # care which system they describe -- as long as BOTH describe the same one.
    scope: str = SCOPE_VIEWPORT
    document_size: Tuple[int, int] = (0, 0)

    detected: int = 0
    kept: int = 0
    below_fold_dropped: int = 0
    too_small_dropped: int = 0
    too_large_dropped: int = 0
    # Per-element classification detail, kept out of `layout` so that stays
    # exactly the shape attribution wants.
    classification: Dict[str, dict] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def low_confidence_fraction(self) -> float:
        """Share of kept elements whose type was a guess rather than a tag.

        The number to look at before trusting a URL-mode report: at 0.5, half
        the element labels the agents reasoned over were inferred from class
        names and geometry.
        """
        if not self.classification:
            return 0.0
        weak = sum(1 for c in self.classification.values() if c["confidence"] < 0.6)
        return round(weak / len(self.classification), 3)

    @property
    def page_screens(self) -> float:
        """How many viewports tall the page is. 1.0 = fits without scrolling."""
        _, vh = self.viewport
        return round(self.document_size[1] / vh, 2) if vh else 1.0

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "viewport": list(self.viewport),
            "scope": self.scope,
            "document_size": list(self.document_size),
            "page_screens": self.page_screens,
            "layout": self.layout,
            "screenshot_path": self.screenshot_path,
            "detected": self.detected,
            "kept": self.kept,
            "below_fold_dropped": self.below_fold_dropped,
            "too_small_dropped": self.too_small_dropped,
            "too_large_dropped": self.too_large_dropped,
            "low_confidence_fraction": self.low_confidence_fraction,
            "classification": self.classification,
            "warnings": self.warnings,
        }


# The in-page collector. Runs in the browser, so it can read computed styles
# and the accessibility tree -- neither is available from the Python side
# without a round trip per element.
_COLLECT_JS = """
() => {
  const SELECTOR = [
    'button', 'a', 'input', 'select', 'textarea',
    'nav', 'header', 'footer', 'main', 'form',
    'img', 'svg', 'video', 'canvas', 'figure',
    'h1', 'h2', 'h3', 'h4', 'label',
    '[role]', '[onclick]'
  ].join(',');

  // Both coordinate systems are returned so Python can choose without a
  // second round trip: `box` is viewport-relative (what getBoundingClientRect
  // gives), `doc_box` adds the scroll offset to put it in document space.
  const sx = window.scrollX || 0;
  const sy = window.scrollY || 0;

  const out = [];
  for (const node of document.querySelectorAll(SELECTOR)) {
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden'
        || parseFloat(style.opacity) === 0) continue;

    const r = node.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;

    out.push({
      tag: node.tagName.toLowerCase(),
      role: node.getAttribute('role') || '',
      input_type: node.getAttribute('type') || '',
      dom_id: node.id || '',
      name: node.getAttribute('name') || '',
      aria_label: node.getAttribute('aria-label') || '',
      classes: Array.from(node.classList || []),
      text: (node.innerText || node.textContent || '').trim().slice(0, 80),
      has_click_handler: !!node.onclick || node.hasAttribute('onclick'),
      in_nav: !!node.closest('nav,[role="navigation"]'),
      box: { x: r.x, y: r.y, width: r.width, height: r.height },
      doc_box: { x: r.x + sx, y: r.y + sy, width: r.width, height: r.height }
    });
  }
  return {
    elements: out,
    document_size: {
      width: Math.max(document.documentElement.scrollWidth,
                      document.body ? document.body.scrollWidth : 0),
      height: Math.max(document.documentElement.scrollHeight,
                       document.body ? document.body.scrollHeight : 0)
    }
  };
}
"""


def _capture_sync(
    url: str,
    viewport: Tuple[int, int],
    screenshot_path: Optional[Path],
    timeout_ms: int,
    full_page_screenshot: bool,
    scope: str,
) -> CaptureResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:      # pragma: no cover - environment dependent
        raise RenderUnavailable(
            "playwright is not installed -- pip install -r requirements.txt "
            "&& playwright install chromium"
        ) from exc

    vw, vh = viewport
    warnings: List[str] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:    # noqa: BLE001
            raise RenderUnavailable(
                f"could not launch Chromium ({exc}). Run: playwright install chromium"
            ) from exc

        try:
            page = browser.new_page(viewport={"width": vw, "height": vh})
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:       # noqa: BLE001
                # networkidle never settles on pages with polling or ads. Fall
                # back to domcontentloaded rather than failing the capture --
                # a late-loading widget is worth less than the whole session.
                warnings.append(
                    "page never reached network idle; captured after DOM load, "
                    "so late-loading elements may be missing"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            title = page.title()
            final_url = page.url
            collected = page.evaluate(_COLLECT_JS)
            raw = collected["elements"]
            doc = collected["document_size"]
            document_size = (int(doc["width"]), int(doc["height"]))

            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                # A document-scope capture wants the whole page, so the
                # screenshot and the layout describe the same thing.
                page.screenshot(
                    path=str(screenshot_path),
                    full_page=full_page_screenshot or scope == SCOPE_DOCUMENT,
                )
        finally:
            browser.close()

    return _build_layout(url, final_url, title, viewport, raw,
                         screenshot_path, warnings,
                         scope=scope, document_size=document_size)


def _build_layout(
    url: str,
    final_url: str,
    title: str,
    viewport: Tuple[int, int],
    raw: List[dict],
    screenshot_path: Optional[Path],
    warnings: List[str],
    scope: str = SCOPE_VIEWPORT,
    document_size: Tuple[int, int] = (0, 0),
) -> CaptureResult:
    vw, vh = viewport
    doc_w, doc_h = document_size or (vw, vh)

    # The reference frame everything is normalised against.
    document = scope == SCOPE_DOCUMENT
    ref_w, ref_h = (doc_w, doc_h) if document else (vw, vh)

    result = CaptureResult(
        url=url, final_url=final_url, title=title, viewport=viewport,
        scope=scope, document_size=(doc_w, doc_h),
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        detected=len(raw), warnings=list(warnings),
    )

    candidates = []
    for el in raw:
        box = el["doc_box"] if document else el["box"]
        el["_box"] = box

        # Area is judged against the VIEWPORT in both scopes. A banner that
        # fills the screen is equally hard to attribute whether or not the
        # page happens to scroll for another ten screens beneath it -- scaling
        # the thresholds by document height would let a huge hero image slip
        # under MAX_AREA_FRACTION on a long page and not on a short one.
        area_fraction = (box["width"] * box["height"]) / float(vw * vh)
        el["area_fraction"] = area_fraction

        if document:
            # Nothing is "off-screen" in document scope -- the participant can
            # scroll to any of it. Only genuinely out-of-document boxes go.
            if box["y"] >= doc_h or box["x"] >= doc_w \
                    or box["y"] + box["height"] <= 0 or box["x"] + box["width"] <= 0:
                result.below_fold_dropped += 1
                continue
        elif box["y"] + box["height"] <= 0 or box["y"] >= vh \
                or box["x"] + box["width"] <= 0 or box["x"] >= vw:
            # Viewport scope: gaze can never land outside the visible window.
            result.below_fold_dropped += 1
            continue

        if area_fraction < MIN_AREA_FRACTION:
            result.too_small_dropped += 1
            continue
        if area_fraction > MAX_AREA_FRACTION:
            result.too_large_dropped += 1
            continue
        candidates.append(el)

    # Biggest first, so if MAX_ELEMENTS truncates it keeps the elements a
    # participant is most likely to actually look at.
    candidates.sort(key=lambda e: e["area_fraction"], reverse=True)
    if len(candidates) > MAX_ELEMENTS:
        warnings.append(
            f"page has {len(candidates)} attributable elements; kept the "
            f"{MAX_ELEMENTS} largest. Per-element metrics cover only those."
        )
        candidates = candidates[:MAX_ELEMENTS]

    taken: set = set()
    for el in candidates:
        info = classify(el, viewport, taken)
        taken.add(info["element_id"])

        box = el["_box"]
        # Clip to the reference frame before normalising: a partially
        # out-of-frame element would otherwise get a box extending past 1.0,
        # and every gaze point in that phantom region would be attributed to it.
        x1 = max(0.0, box["x"])
        y1 = max(0.0, box["y"])
        x2 = min(float(ref_w), box["x"] + box["width"])
        y2 = min(float(ref_h), box["y"] + box["height"])

        result.layout[info["element_id"]] = {
            "bbox": (round(x1 / ref_w, 5), round(y1 / ref_h, 5),
                     round((x2 - x1) / ref_w, 5), round((y2 - y1) / ref_h, 5)),
            "importance": info["importance"],
            "type": info["type"],
        }
        result.classification[info["element_id"]] = {
            "tag": el.get("tag"),
            "text": (el.get("text") or "")[:60],
            "confidence": info["confidence"],
            "classified_by": info["classified_by"],
        }

    result.kept = len(result.layout)
    result.warnings = warnings

    if not result.layout:
        warnings.append(
            "no attributable elements found -- the page may be canvas-based, "
            "behind a consent wall, or rendered entirely below the fold"
        )
    elif not document and result.page_screens > 1.2:
        # The trap this scope exists to avoid: capture the first screen of a
        # five-screen page, and every element further down is simply absent
        # from the report. Nobody reading it can tell that from "nobody looked
        # at them".
        warnings.append(
            f"page is {result.page_screens:.1f} viewports tall but was captured "
            f"in viewport scope, so {result.below_fold_dropped} element(s) below "
            f"the fold are not in this layout at all. Use scope='document' and "
            f"send scroll offsets with the gaze stream to cover the whole page."
        )
    elif result.low_confidence_fraction > 0.4:
        warnings.append(
            f"{result.low_confidence_fraction:.0%} of element types were "
            f"inferred from class names or geometry rather than tags; treat "
            f"per-element findings as provisional"
        )

    return result


def capture_page(
    url: str,
    viewport: Tuple[int, int] = DEFAULT_VIEWPORT,
    screenshot_path: Optional[Path] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    full_page_screenshot: bool = False,
    scope: str = SCOPE_DOCUMENT,
) -> CaptureResult:
    """Screenshot + element detection for a URL. Safe to call from async code.

    scope="document" (the default) normalises boxes against the whole
    scrollable page, so elements below the fold are included. The gaze stream
    must then carry a scroll offset per point -- backend/api does that
    translation; see its pipeline.to_document_space.

    scope="viewport" restricts the layout to the first screen. Correct only
    when the page doesn't scroll, and it warns when the page clearly does.
    """
    if not url.startswith(("http://", "https://", "file://")):
        raise ValueError(f"unsupported URL scheme: {url!r}")
    if scope not in (SCOPE_VIEWPORT, SCOPE_DOCUMENT):
        raise ValueError(f"scope must be 'viewport' or 'document', got {scope!r}")

    args = (url, viewport,
            Path(screenshot_path) if screenshot_path else None,
            timeout_ms, full_page_screenshot, scope)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _capture_sync(*args)

    # Inside an event loop (a FastAPI request): Playwright's sync API refuses
    # to run there, so hand it to a thread that has no loop of its own.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_capture_sync, *args).result()


def render_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


__all__ = [
    "capture_page",
    "SCOPE_VIEWPORT",
    "SCOPE_DOCUMENT",
    "CaptureResult",
    "RenderUnavailable",
    "render_available",
    "DEFAULT_VIEWPORT",
    "MIN_AREA_FRACTION",
    "MAX_AREA_FRACTION",
    "MAX_ELEMENTS",
]
