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
Boxes are normalised to the VIEWPORT, top-left origin, y down -- the same
convention as gaze, which is also viewport-relative. Elements scrolled out of
view are dropped rather than given negative coordinates: gaze can only land on
what is on screen, and a box at y=-300 would silently never be hit while still
appearing in the report as an element that got no attention.

That is a real limitation for long pages, and it is recorded on the result
rather than hidden -- see `below_fold_dropped`.

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


@dataclass
class CaptureResult:
    url: str
    final_url: str
    title: str
    viewport: Tuple[int, int]
    layout: Dict[str, dict] = field(default_factory=dict)
    screenshot_path: Optional[str] = None

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

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "viewport": list(self.viewport),
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
      box: { x: r.x, y: r.y, width: r.width, height: r.height }
    });
  }
  return out;
}
"""


def _capture_sync(
    url: str,
    viewport: Tuple[int, int],
    screenshot_path: Optional[Path],
    timeout_ms: int,
    full_page_screenshot: bool,
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
            raw = page.evaluate(_COLLECT_JS)

            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path),
                                full_page=full_page_screenshot)
        finally:
            browser.close()

    return _build_layout(url, final_url, title, viewport, raw,
                         screenshot_path, warnings)


def _build_layout(
    url: str,
    final_url: str,
    title: str,
    viewport: Tuple[int, int],
    raw: List[dict],
    screenshot_path: Optional[Path],
    warnings: List[str],
) -> CaptureResult:
    vw, vh = viewport
    result = CaptureResult(
        url=url, final_url=final_url, title=title, viewport=viewport,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        detected=len(raw), warnings=list(warnings),
    )

    candidates = []
    for el in raw:
        box = el["box"]
        area_fraction = (box["width"] * box["height"]) / float(vw * vh)
        el["area_fraction"] = area_fraction

        # Off-screen: gaze is viewport-relative and can never land here.
        if box["y"] + box["height"] <= 0 or box["y"] >= vh \
                or box["x"] + box["width"] <= 0 or box["x"] >= vw:
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

        box = el["box"]
        # Clip to the viewport before normalising: a half-off-screen element
        # would otherwise get a box extending past 1.0, and every gaze point
        # in that phantom region would be attributed to it.
        x1 = max(0.0, box["x"])
        y1 = max(0.0, box["y"])
        x2 = min(float(vw), box["x"] + box["width"])
        y2 = min(float(vh), box["y"] + box["height"])

        result.layout[info["element_id"]] = {
            "bbox": (round(x1 / vw, 5), round(y1 / vh, 5),
                     round((x2 - x1) / vw, 5), round((y2 - y1) / vh, 5)),
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
) -> CaptureResult:
    """Screenshot + element detection for a URL. Safe to call from async code."""
    if not url.startswith(("http://", "https://", "file://")):
        raise ValueError(f"unsupported URL scheme: {url!r}")

    args = (url, viewport,
            Path(screenshot_path) if screenshot_path else None,
            timeout_ms, full_page_screenshot)

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
    "CaptureResult",
    "RenderUnavailable",
    "render_available",
    "DEFAULT_VIEWPORT",
    "MIN_AREA_FRACTION",
    "MAX_AREA_FRACTION",
    "MAX_ELEMENTS",
]
