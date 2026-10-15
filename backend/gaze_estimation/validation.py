"""
validation.py

Accuracy measured on NEW points after calibration, not on the calibration
points themselves.

Leave-one-point-out (evaluation.py) already holds out each calibration point
in turn, but every fold still comes from the same 30 seconds of the same
sitting. A short validation pass -- a handful of fresh dots, captured after
the model is trained -- is the number a participant (and the paper) should
see, and the one the live session gates on.

Results are stored on the model itself, in metrics["validation_pass"], next to
the held-out calibration error, so a loaded model always carries both.
"""

from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from .estimator import GazePoint
from .model import GazeModel

# Thresholds as a fraction of the screen diagonal, so they mean the same
# thing on a 13" laptop and a 27" monitor. On a 1694x840 screen these are
# ~150 px (good) and ~280 px (refused).
VALIDATION_GOOD_FRACTION = 0.08
VALIDATION_MAX_FRACTION = 0.15

# A validation point needs at least this many tracked frames to count;
# fewer is a blink-through or a face that left the frame.
MIN_VALID_FRAMES = 3

# Not "validation": metrics["validation"] already names the CV method
# ("leave_one_point_out") in evaluation.py's output.
VALIDATION_KEY = "validation_pass"


def _diagonal(model: GazeModel) -> float:
    return float(np.hypot(model.screen_width, model.screen_height))


def score_point(
    points: Sequence[GazePoint],
    target_x: float,
    target_y: float,
    model: GazeModel,
) -> Dict:
    """One validation dot's frames -> its error.

    error_px uses the MEDIAN predicted position over the dot: the person was
    fixating one target, so per-frame jitter around it is noise to average
    out, and the median is robust to a stray blink frame. per_frame_median
    keeps the jitter visible as a second number.
    """
    w, h = model.screen_width, model.screen_height
    valid = [p for p in points if p.valid]
    out = {
        "target_x": float(target_x),
        "target_y": float(target_y),
        "n_frames": len(points),
        "n_valid": len(valid),
        "head_moved_frames": sum(1 for p in valid if p.note == "head_moved"),
    }
    if len(valid) < MIN_VALID_FRAMES:
        out.update(usable=False, error_px=None, per_frame_median_error_px=None,
                   predicted_x=None, predicted_y=None)
        return out

    xs = np.asarray([p.x for p in valid])
    ys = np.asarray([p.y for p in valid])
    px, py = float(np.median(xs)), float(np.median(ys))
    per_frame = np.hypot((xs - target_x) * w, (ys - target_y) * h)
    out.update(
        usable=True,
        predicted_x=px,
        predicted_y=py,
        error_px=float(np.hypot((px - target_x) * w, (py - target_y) * h)),
        per_frame_median_error_px=float(np.median(per_frame)),
    )
    return out


def record_point(model: GazeModel, point_index: int, result: Dict) -> Dict:
    """Store one point's result on the model; returns the updated summary.

    Re-submitting a point index replaces it, so a participant can redo one
    dot without restarting the pass.
    """
    validation = dict(model.metrics.get(VALIDATION_KEY) or {})
    points = dict(validation.get("points") or {})
    points[str(point_index)] = result
    validation["points"] = points
    validation.update(summarise(points, model))
    model.metrics = {**model.metrics, VALIDATION_KEY: validation}
    return validation


def summarise(points: Dict[str, Dict], model: GazeModel) -> Dict:
    errors = [p["error_px"] for p in points.values() if p.get("usable")]
    diagonal = _diagonal(model)
    if not errors:
        return {"n_points": len(points), "n_usable": 0, "median_error_px": None,
                "median_error_pct_diagonal": None, "verdict": "insufficient"}
    median = float(np.median(errors))
    frac = median / diagonal
    verdict = ("good" if frac <= VALIDATION_GOOD_FRACTION
               else "fair" if frac <= VALIDATION_MAX_FRACTION
               else "poor")
    return {
        "n_points": len(points),
        "n_usable": len(errors),
        "median_error_px": median,
        "max_error_px": float(max(errors)),
        "median_error_pct_diagonal": 100.0 * frac,
        "good_threshold_px": VALIDATION_GOOD_FRACTION * diagonal,
        "max_threshold_px": VALIDATION_MAX_FRACTION * diagonal,
        "verdict": verdict,
    }


def validation_gate(model: GazeModel) -> Tuple[Optional[bool], str]:
    """Should a live session be allowed on this model?

    (None, ...) when no validation was run -- the caller decides; older
    calibrations predate validation and stay usable. (False, reason) when
    validation says the mapping is too inaccurate for element attribution.
    """
    v = model.metrics.get(VALIDATION_KEY)
    if not v or v.get("median_error_px") is None:
        return None, "not validated"
    if v["verdict"] == "poor":
        return False, (
            f"validation error {v['median_error_px']:.0f}px is over the "
            f"{v['max_threshold_px']:.0f}px limit ({VALIDATION_MAX_FRACTION:.0%} of the "
            f"screen diagonal) -- recalibrate"
        )
    return True, f"validated at {v['median_error_px']:.0f}px ({v['verdict']})"


__all__ = [
    "VALIDATION_GOOD_FRACTION",
    "VALIDATION_MAX_FRACTION",
    "MIN_VALID_FRAMES",
    "VALIDATION_KEY",
    "score_point",
    "record_point",
    "summarise",
    "validation_gate",
]
