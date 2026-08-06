"""
schemas.py

Pydantic request/response models -- the HTTP boundary only.

Same rule as backend/calibration and backend/gaze_estimation: Pydantic where
untrusted JSON arrives, plain dataclasses everywhere inward. The response
mirrors backend/agents' SessionMetrics field for field, so what comes out of
the endpoint can be fed back into the agent chain unchanged.
"""

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .elements import ELEMENT_TYPES, IMPORTANCE_VALUES
from .fixations import DISPERSION_THRESHOLD, MAX_GAP, MIN_FIXATION_DURATION, SMOOTHING_WINDOW


class GazePointInput(BaseModel):
    """One raw gaze point.

    Matches the GazePoint shape backend/gaze_estimation emits, but is declared
    independently -- attribution must not depend on that module.
    """

    timestamp: float
    x: float
    y: float
    valid: bool = True
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class ElementInput(BaseModel):
    """One UI element: where it is, and what it means.

    Accepts either a normalised (x, y, w, h) tuple -- the form
    backend/reports/heatmap_stub.py already uses -- or explicit x/y/width/
    height, which is what Playwright's boundingBox() returns and therefore
    what backend/render most likely produces. Pixel values need `viewport`
    on the request to normalise against.
    """

    bbox: Optional[Tuple[float, float, float, float]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None

    importance: str = "medium"
    type: str = "non-interactive"

    @model_validator(mode="after")
    def _check(self) -> "ElementInput":
        has_tuple = self.bbox is not None
        has_fields = None not in (self.x, self.y, self.width, self.height)
        if has_tuple == has_fields:
            raise ValueError(
                "supply either bbox=(x,y,w,h) or all of x/y/width/height, not both"
            )
        if self.importance not in IMPORTANCE_VALUES:
            raise ValueError(f"importance must be one of {list(IMPORTANCE_VALUES)}")
        if self.type not in ELEMENT_TYPES:
            raise ValueError(f"type must be one of {list(ELEMENT_TYPES)}")
        return self

    def as_spec(self) -> dict:
        box = self.bbox if self.bbox is not None else {
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
        }
        return {"bbox": box, "importance": self.importance, "type": self.type}


class AnalyzeRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    ui_page: str = Field(..., min_length=1, max_length=128)
    elements: Dict[str, ElementInput] = Field(..., min_length=1)
    gaze: List[GazePointInput] = Field(..., min_length=0, max_length=500_000)

    # Required when element boxes are in CSS pixels; omit for normalised ones.
    viewport: Optional[Tuple[float, float]] = None
    # Explicit overlap z-order; earlier wins. Without it, the smaller box wins.
    priority: Optional[List[str]] = None

    # Thresholds are exposed because they are research parameters, not fixed
    # constants -- the pilot study may well retune them. Defaults are the
    # documented ones.
    min_fixation_duration: float = Field(MIN_FIXATION_DURATION, gt=0, le=2.0)
    dispersion_threshold: float = Field(DISPERSION_THRESHOLD, gt=0, le=1.0)
    max_gap: float = Field(MAX_GAP, ge=0, le=2.0)
    smoothing_window: int = Field(SMOOTHING_WINDOW, ge=1, le=51)


class SessionMetricsModel(BaseModel):
    """Mirrors backend/agents/schemas.py SessionMetrics exactly.

    `ttff` deliberately omits elements that were never fixated -- see
    metrics.py. It is not a bug that its key set can be smaller than
    dwell_time's.
    """

    session_id: str
    ui_page: str
    dwell_time: Dict[str, float]
    ttff: Dict[str, float]
    fixation_count: Dict[str, int]
    revisit_count: Dict[str, int]
    total_gaze_time: float
    scanpath: List[str]
    element_importance: Dict[str, str]
    element_type: Dict[str, str]


class DiagnosticsModel(BaseModel):
    """Things worth knowing that SessionMetrics has no field for.

    SessionMetrics is a fixed contract owned by backend/agents; it must not
    grow, so these live alongside it rather than inside it.
    """

    background_time: float
    background_pct: float
    tracked_pct: float
    dropped_invalid: int
    bridged_samples: int
    total_fixations: int
    background_fixations: int
    unfixated_elements: List[str]
    overlapping_elements: List[List[str]]
    warnings: List[str]


class AnalyzeResponse(BaseModel):
    metrics: SessionMetricsModel
    diagnostics: DiagnosticsModel
    # The layout in the exact form backend/reports/heatmap_stub.py consumes,
    # so the report layer needs no conversion step.
    heatmap_layout: Dict[str, Tuple[float, float, float, float]]


class DefaultsResponse(BaseModel):
    """The thresholds in force, so a client isn't guessing what produced a number."""

    min_fixation_duration: float
    dispersion_threshold: float
    max_gap: float
    smoothing_window: int
    importance_values: List[str]
    element_types: List[str]
    notes: Dict[str, str]


__all__ = [
    "GazePointInput",
    "ElementInput",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "SessionMetricsModel",
    "DiagnosticsModel",
    "DefaultsResponse",
]
