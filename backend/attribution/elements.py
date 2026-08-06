"""
elements.py

The UI-side input: which elements exist, where they are, and what they mean.

SessionMetrics needs two things gaze data can never supply --
`element_importance` and `element_type`. They come from the UI config, and
backend/agents keys real behaviour off them: only elements typed "CTA" get
the TTFF and dwell-visibility rules, only "non-interactive" ones get the
misleading-affordance rule, and only "high" importance ones can be reported
as ignored. An element with the wrong type is silently exempt from the rules
that matter, so the vocabularies are validated here rather than trusted.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .geometry import BBox, parse_bbox

# Vocabularies taken from backend/agents/schemas.py. Not extended here --
# agents/rules.py branches on these exact strings.
IMPORTANCE_VALUES = ("high", "medium", "low")
ELEMENT_TYPES = ("CTA", "text", "image", "nav", "non-interactive")

DEFAULT_IMPORTANCE = "medium"
DEFAULT_TYPE = "non-interactive"


class ElementConfigError(ValueError):
    """Malformed element configuration."""


@dataclass(frozen=True)
class Element:
    element_id: str
    bbox: BBox
    importance: str = DEFAULT_IMPORTANCE
    element_type: str = DEFAULT_TYPE

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "bbox": self.bbox.to_dict(),
            "importance": self.importance,
            "element_type": self.element_type,
        }


@dataclass
class UIConfig:
    """One page's elements. The non-gaze half of a session."""

    ui_page: str
    elements: List[Element] = field(default_factory=list)
    # Explicit z-order for overlap ties; earlier wins. Optional -- the default
    # smallest-box-wins rule handles nesting without it.
    priority: Optional[List[str]] = None

    @property
    def boxes(self) -> Dict[str, BBox]:
        return {e.element_id: e.bbox for e in self.elements}

    @property
    def element_ids(self) -> List[str]:
        return [e.element_id for e in self.elements]

    def importance_map(self) -> Dict[str, str]:
        return {e.element_id: e.importance for e in self.elements}

    def type_map(self) -> Dict[str, str]:
        return {e.element_id: e.element_type for e in self.elements}

    def layout_for_heatmap(self) -> Dict[str, Tuple[float, float, float, float]]:
        """The exact shape backend/reports/heatmap_stub.py wants.

        Provided so the report layer can render a real page layout without
        anyone writing a conversion step -- see CONTRACT.md.
        """
        return {e.element_id: e.bbox.as_tuple() for e in self.elements}


def _validate(element_id: str, importance: str, element_type: str) -> None:
    if importance not in IMPORTANCE_VALUES:
        raise ElementConfigError(
            f"element {element_id!r}: importance {importance!r} is not one of "
            f"{list(IMPORTANCE_VALUES)} -- backend/agents branches on these exact strings"
        )
    if element_type not in ELEMENT_TYPES:
        raise ElementConfigError(
            f"element {element_id!r}: type {element_type!r} is not one of "
            f"{list(ELEMENT_TYPES)} -- backend/agents branches on these exact strings"
        )


def build_ui_config(
    ui_page: str,
    elements: dict,
    viewport: Optional[Tuple[float, float]] = None,
    priority: Optional[Sequence[str]] = None,
) -> UIConfig:
    """Build a UIConfig from any of the accepted element-map forms.

    `elements` maps element_id -> one of:

      (x, y, w, h)                          bare bbox, metadata defaulted
      {"bbox": ..., "importance":, "type":} bbox plus metadata
      {"x":, "y":, "width":, "height":,     Playwright-style, metadata optional
       "importance":, "type":}

    Bare boxes default to importance="medium", type="non-interactive".
    That default is deliberately inert: "non-interactive" is the only type
    that can trigger agents' misleading-affordance rule, and it needs 5+
    fixations to do so, whereas defaulting to "CTA" would invent
    poor-visibility findings for every unlabelled element on the page.
    """
    parsed: List[Element] = []

    for element_id, spec in elements.items():
        importance = DEFAULT_IMPORTANCE
        element_type = DEFAULT_TYPE

        if isinstance(spec, dict) and "bbox" in spec:
            raw_box = spec["bbox"]
            importance = spec.get("importance", importance)
            element_type = spec.get("type", spec.get("element_type", element_type))
        elif isinstance(spec, dict):
            raw_box = spec
            importance = spec.get("importance", importance)
            element_type = spec.get("type", spec.get("element_type", element_type))
        else:
            raw_box = spec

        _validate(element_id, importance, element_type)
        try:
            bbox = parse_bbox(raw_box, viewport=viewport)
        except Exception as exc:
            raise ElementConfigError(f"element {element_id!r}: {exc}") from exc

        if bbox.area <= 0:
            raise ElementConfigError(
                f"element {element_id!r} has zero area ({bbox.to_dict()}); "
                f"it can never receive a gaze point"
            )

        parsed.append(Element(element_id, bbox, importance, element_type))

    if not parsed:
        raise ElementConfigError(
            f"UI config for {ui_page!r} has no elements -- nothing to attribute gaze to"
        )

    return UIConfig(ui_page=ui_page, elements=parsed,
                    priority=list(priority) if priority else None)


__all__ = [
    "Element",
    "UIConfig",
    "ElementConfigError",
    "IMPORTANCE_VALUES",
    "ELEMENT_TYPES",
    "build_ui_config",
]
