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

from typing import Dict, Sequence

from .elements import UIConfig
from .fixations import (
    DISPERSION_THRESHOLD,
    MAX_GAP,
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
) -> AttributionReport:
    """Gaze stream + UI layout -> SessionMetrics (plus diagnostics).

    An empty stream is not an error: a participant who never produced a usable
    gaze point is a real study outcome, and the caller should get a zeroed
    report carrying that warning rather than an exception to catch.
    """
    trace = attribute(
        samples,
        ui_config.boxes,
        priority=ui_config.priority,
        min_fixation_duration=min_fixation_duration,
        dispersion_threshold=dispersion_threshold,
        max_gap=max_gap,
        smoothing_window=smoothing_window,
    )
    report = build_metrics(trace, ui_config, session_id)

    overlaps = overlapping_pairs(ui_config.boxes)
    report.overlapping_elements = [list(p) for p in overlaps]
    if overlaps:
        report.warnings.append(
            f"{len(overlaps)} overlapping element pair(s) in the layout "
            f"(e.g. {overlaps[0][0]} / {overlaps[0][1]}); gaze inside the "
            f"overlap is attributed to the smaller box"
        )
    return report


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


__all__ = ["analyze_session", "gaze_samples_from_dicts"]
