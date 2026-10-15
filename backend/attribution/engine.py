"""
engine.py

The one function everything else calls.

    report = analyze_session(gaze_samples, ui_config, session_id)
    orchestrator.run_pipeline(report.metrics)      # straight into the agents

Live sessions call this in-process rather than over HTTP -- the gaze stream
already exists in memory, and posting thousands of points back to the server
to have them counted would be absurd. The route in routes.py wraps this same
function for the frontend and for offline re-analysis of a stored session.
"""

from typing import Dict, Optional, Sequence, Tuple

from .elements import UIConfig
from .fixations import (
    DISPERSION_THRESHOLD,
    MAX_GAP,
    EDGE_TOLERANCE,
    MAX_EDGE_TOLERANCE,
    MIN_FIXATION_DURATION,
    SMOOTHING_WINDOW,
    GazeSample,
    attribute,
)
from .geometry import overlapping_pairs
from .metrics import AttributionReport, build_metrics


def analyze_session(
    samples: Sequence[GazeSample],
    ui_config: UIConfig,
    session_id: str,
    min_fixation_duration: float = MIN_FIXATION_DURATION,
    dispersion_threshold: float = DISPERSION_THRESHOLD,
    max_gap: float = MAX_GAP,
    smoothing_window: int = SMOOTHING_WINDOW,
    gaze_error_px: Optional[float] = None,
    viewport_px: Optional[Tuple[float, float]] = None,
) -> AttributionReport:
    """Gaze stream + UI layout -> SessionMetrics (plus diagnostics).

    An empty stream is not an error: a participant who never produced a usable
    gaze point is a real study outcome, and the caller should get a zeroed
    report carrying that warning rather than an exception to catch.

    gaze_error_px + viewport_px (the page's size in pixels as shown) make
    attribution error-aware: a fixation landing on background within one
    median gaze error of a box is attributed to it (instead of the fixed
    EDGE_TOLERANCE), and every element gets a reliability score -- its
    smaller side over the gaze error. Without them behaviour is unchanged.
    """
    edge_tolerance, reliability = EDGE_TOLERANCE, {}
    if gaze_error_px and viewport_px:
        edge_tolerance, reliability = error_model(ui_config, gaze_error_px, viewport_px)

    trace = attribute(
        samples,
        ui_config.boxes,
        priority=ui_config.priority,
        min_fixation_duration=min_fixation_duration,
        dispersion_threshold=dispersion_threshold,
        max_gap=max_gap,
        smoothing_window=smoothing_window,
        edge_tolerance=edge_tolerance,
    )
    report = build_metrics(trace, ui_config, session_id)
    report.edge_tolerance = edge_tolerance
    if reliability:
        report.gaze_error_px = float(gaze_error_px)
        report.element_reliability = reliability
        report.low_confidence_elements = sorted(
            e for e, r in reliability.items() if r < RELIABLE_SIZE_RATIO
        )
        if report.low_confidence_elements:
            report.warnings.append(
                f"{len(report.low_confidence_elements)} element(s) are smaller than "
                f"the measured gaze error ({gaze_error_px:.0f}px): "
                f"{report.low_confidence_elements} -- attention on them can't be "
                f"told apart from tracking noise"
            )

    overlaps = overlapping_pairs(ui_config.boxes)
    report.overlapping_elements = [list(p) for p in overlaps]
    if overlaps:
        report.warnings.append(
            f"{len(overlaps)} overlapping element pair(s) in the layout "
            f"(e.g. {overlaps[0][0]} / {overlaps[0][1]}); gaze inside the "
            f"overlap is attributed to the smaller box"
        )
    return report


# An element is measurable when its smaller side is at least one median gaze
# error: then most gaze aimed at its centre still lands inside it.
RELIABLE_SIZE_RATIO = 1.0


def error_model(
    ui_config: UIConfig,
    gaze_error_px: float,
    viewport_px: Tuple[float, float],
) -> Tuple[float, Dict[str, float]]:
    """(edge tolerance in page units, {element_id: size/error ratio}).

    The tolerance is the error converted to page units (averaging the two
    axes, since nearest_element measures in normalised space), clamped
    between the fixed default and MAX_EDGE_TOLERANCE. It only ever applies
    to a fixation that hit NO box, so a larger tolerance can't steal
    attention from an element that was actually hit.
    """
    vw, vh = float(viewport_px[0]), float(viewport_px[1])
    err_norm = float(gaze_error_px) / ((vw + vh) / 2.0)
    tolerance = min(max(err_norm, EDGE_TOLERANCE), MAX_EDGE_TOLERANCE)
    reliability = {
        e.element_id: round(min(e.bbox.w * vw, e.bbox.h * vh) / float(gaze_error_px), 3)
        for e in ui_config.elements
    }
    return tolerance, reliability


def gaze_samples_from_dicts(raw: Sequence[Dict]) -> list:
    """Convenience for JSON input: dicts -> GazeSample.

    Accepts the GazePoint shape backend/gaze_estimation emits, without
    importing it: {"timestamp", "x", "y", "valid", "confidence"}. Anything a
    consumer might reasonably send instead ("t", "time") is accepted too,
    because the alternative is a stack trace on a key name.
    """
    out = []
    for i, d in enumerate(raw):
        ts = d.get("timestamp", d.get("t", d.get("time")))
        if ts is None:
            raise ValueError(f"gaze sample {i} has no timestamp")
        if d.get("x") is None or d.get("y") is None:
            raise ValueError(f"gaze sample {i} has no x/y")
        out.append(GazeSample(
            timestamp=float(ts),
            x=float(d["x"]),
            y=float(d["y"]),
            valid=bool(d.get("valid", True)),
            confidence=float(d.get("confidence", 1.0)),
        ))
    return out


__all__ = ["RELIABLE_SIZE_RATIO", "analyze_session", "error_model", "gaze_samples_from_dicts"]
