"""
geometry.py

Bounding boxes and hit-testing.

COORDINATE CONVENTION
---------------------
Normalised [0,1] page-space, (x, y) = TOP-LEFT corner, y grows DOWNWARD.

That is not an arbitrary choice: backend/reports/heatmap_stub.py already
renders against exactly this convention (it calls `ax_map.invert_yaxis()`
for precisely this reason), and backend/reports is done. Attribution output
and the heatmap therefore describe the same geometry without a conversion
step between them.

TWO ACCEPTED INPUT FORMS
------------------------
1. `(x, y, w, h)` tuple, already normalised -- the heatmap_stub /
   hand-authored test_uis form.
2. `{"x":, "y":, "width":, "height":}` in CSS pixels, plus a viewport size --
   which is what Playwright's `boundingBox()` returns, and therefore almost
   certainly what backend/render produces. (backend/render has never been
   pushed to this repo, so this is inference from the Playwright API rather
   than from its code -- see CONTRACT.md.)

Both normalise to the same BBox on ingest, so neither producer has to change
when the other one lands.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

BBoxInput = Union[
    Sequence[float],        # (x, y, w, h)
    Dict[str, float],       # {"x":, "y":, "width":, "height":} or {"x","y","w","h"}
    "BBox",
]


class BBoxFormatError(ValueError):
    """The bounding box couldn't be understood."""


@dataclass(frozen=True)
class BBox:
    """A normalised [0,1] rectangle, top-left origin, y down."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def contains(self, px: float, py: float) -> bool:
        """Half-open on the far edges, so touching boxes never both match.

        Adjacent elements in a real layout share an edge constantly (a nav bar
        sitting directly on a hero image). Closed intervals would make every
        gaze point on that seam ambiguous.
        """
        return self.x <= px < self.x2 and self.y <= py < self.y2

    def expanded(self, margin: float) -> "BBox":
        """Grow by `margin` on every side, clamped to the page."""
        return BBox(
            x=max(0.0, self.x - margin),
            y=max(0.0, self.y - margin),
            w=min(1.0, self.x2 + margin) - max(0.0, self.x - margin),
            h=min(1.0, self.y2 + margin) - max(0.0, self.y - margin),
        )

    def as_tuple(self) -> Tuple[float, float, float, float]:
        """The form backend/reports/heatmap_stub.py consumes."""
        return (self.x, self.y, self.w, self.h)

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


def parse_bbox(
    raw: BBoxInput,
    viewport: Optional[Tuple[float, float]] = None,
) -> BBox:
    """Any accepted bbox form -> a normalised BBox.

    `viewport` is (width_px, height_px). Supply it when the box is in pixels;
    omit it when the box is already normalised.
    """
    if isinstance(raw, BBox):
        return raw

    if isinstance(raw, dict):
        try:
            x = float(raw["x"])
            y = float(raw["y"])
            w = float(raw["width"] if "width" in raw else raw["w"])
            h = float(raw["height"] if "height" in raw else raw["h"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BBoxFormatError(
                f"dict bbox needs x/y plus width/height (or w/h); got {sorted(raw)}"
            ) from exc
    else:
        try:
            x, y, w, h = (float(v) for v in raw)
        except (TypeError, ValueError) as exc:
            raise BBoxFormatError(
                f"sequence bbox must be exactly (x, y, w, h); got {raw!r}"
            ) from exc

    if viewport:
        vw, vh = viewport
        if vw <= 0 or vh <= 0:
            raise BBoxFormatError(f"viewport must be positive, got {viewport!r}")
        x, y, w, h = x / vw, y / vh, w / vw, h / vh

    if w < 0 or h < 0:
        raise BBoxFormatError(f"bbox has negative size: w={w}, h={h}")

    # A box in pixels with no viewport supplied is the one silent failure mode
    # here -- it would normalise to a rectangle far outside the page and simply
    # never be hit, producing a plausible-looking all-zeros report.
    if viewport is None and (x > 1.5 or y > 1.5 or w > 1.5 or h > 1.5):
        raise BBoxFormatError(
            f"bbox ({x}, {y}, {w}, {h}) looks like pixels, but no viewport was "
            f"given to normalise it with. Pass viewport=(width_px, height_px)."
        )
    return BBox(x=x, y=y, w=w, h=h)


# ----------------------------------------------------------------------


def hit_test(
    boxes: Dict[str, BBox],
    px: float,
    py: float,
    priority: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Which element does this point land in? None for background.

    OVERLAP RESOLUTION: the SMALLEST box wins.

    Automatic element detection nests boxes constantly -- a button inside a
    card inside a section -- and a point inside the button is inside all
    three. Smallest-wins picks the most specific element, which is the one a
    UX finding should name ("the checkout button was ignored", not "the page
    body was ignored").

    `priority` overrides that for genuine same-size ties or hand-authored
    configs that want an explicit z-order: earlier in the list wins.
    """
    hits = [eid for eid, box in boxes.items() if box.contains(px, py)]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]

    if priority:
        ranked = {eid: i for i, eid in enumerate(priority)}
        hits.sort(key=lambda e: (ranked.get(e, len(ranked)), boxes[e].area, e))
        return hits[0]

    # Ties broken by element_id so the result is deterministic across runs --
    # a report that changes wording between identical runs is unusable.
    hits.sort(key=lambda e: (boxes[e].area, e))
    return hits[0]


def nearest_element(
    boxes: Dict[str, BBox],
    px: float,
    py: float,
    max_distance: float,
) -> Optional[str]:
    """Closest element within `max_distance`, or None.

    Used only for noise tolerance: a gaze point that lands just outside a box
    it was previously inside is far more likely to be estimation error than a
    genuine glance at whitespace. See fixations.py -- this is never used to
    attribute a point that was never near an element to begin with.
    """
    best: Optional[str] = None
    best_d = max_distance
    for eid, box in boxes.items():
        dx = max(box.x - px, 0.0, px - box.x2)
        dy = max(box.y - py, 0.0, py - box.y2)
        d = (dx * dx + dy * dy) ** 0.5
        if d < best_d or (d == best_d and best is not None and eid < best):
            best, best_d = eid, d
    return best


def overlapping_pairs(boxes: Dict[str, BBox]) -> List[Tuple[str, str]]:
    """Element pairs whose boxes intersect -- reported as a diagnostic.

    Overlap is handled, not rejected, but it's worth surfacing: heavy overlap
    in an auto-detected layout usually means the detector emitted container
    elements alongside their children, and the resulting metrics will be
    harder to interpret.
    """
    ids = sorted(boxes)
    out: List[Tuple[str, str]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ba, bb = boxes[a], boxes[b]
            if ba.x < bb.x2 and bb.x < ba.x2 and ba.y < bb.y2 and bb.y < ba.y2:
                out.append((a, b))
    return out


def dispersion(points: Iterable[Tuple[float, float]]) -> float:
    """I-DT dispersion: (max_x - min_x) + (max_y - min_y).

    The standard Salvucci & Goldberg formulation. Cheaper than a true spatial
    variance and, at the sample counts a fixation contains, behaves the same.
    """
    xs, ys = [], []
    for px, py in points:
        xs.append(px)
        ys.append(py)
    if not xs:
        return 0.0
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


__all__ = [
    "BBox",
    "BBoxFormatError",
    "parse_bbox",
    "hit_test",
    "nearest_element",
    "overlapping_pairs",
    "dispersion",
]
