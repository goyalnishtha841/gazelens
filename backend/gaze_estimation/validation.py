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
from .model import CORRECTION_KEY, GazeModel, undo_correction

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
    # Keep the model's own (uncorrected) answer too: the bias correction is
    # re-fitted from these, so they must not already include it.
    raw_x, raw_y = undo_correction(px, py, model.metrics.get(CORRECTION_KEY))
    per_frame = np.hypot((xs - target_x) * w, (ys - target_y) * h)
    out.update(
        usable=True,
        predicted_x=px,
        predicted_y=py,
        raw_x=float(raw_x),
        raw_y=float(raw_y),
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
    summary = summarise(points, model)
    correction, corrected = fit_correction(points, model)
    metrics = dict(model.metrics)
    if correction is not None and corrected is not None and summary.get("median_error_px") is not None \
            and corrected < IMPROVEMENT_REQUIRED * summary["median_error_px"]:
        # Report the HELD-OUT corrected error, so the number shown is honest.
        diagonal = _diagonal(model)
        frac = corrected / diagonal
        summary.update(
            uncorrected_median_error_px=summary["median_error_px"],
            median_error_px=corrected,
            median_error_pct_diagonal=100.0 * frac,
            verdict=("good" if frac <= VALIDATION_GOOD_FRACTION
                     else "fair" if frac <= VALIDATION_MAX_FRACTION else "poor"),
            corrected=True,
        )
        metrics[CORRECTION_KEY] = correction
    else:
        summary["corrected"] = False
        metrics.pop(CORRECTION_KEY, None)
    validation.update(summary)
    metrics[VALIDATION_KEY] = validation
    model.metrics = metrics
    return validation


# The correction is kept only if it beats the raw model by this margin on
# dots it was not fitted to.
IMPROVEMENT_REQUIRED = 0.9
# Pull toward "no correction" (a=1, b=0); five dots is not much data.
CORRECTION_SHRINK = 0.05
MIN_CORRECTION_POINTS = 4


def _fit_axis(raw: np.ndarray, target: np.ndarray) -> Tuple[float, float]:
    """target ~ a*raw + b, ridge-shrunk toward a=1, b=0."""
    A = np.column_stack([raw, np.ones_like(raw)])
    lam = CORRECTION_SHRINK * len(raw)
    # minimise |A w - t|^2 + lam |w - [1, 0]|^2
    w = np.linalg.solve(A.T @ A + lam * np.eye(2), A.T @ target + lam * np.array([1.0, 0.0]))
    a = float(np.clip(w[0], 0.6, 1.6))      # never flip or wildly stretch an axis
    return a, float(w[1])


def fit_correction(points: Dict[str, Dict], model: GazeModel):
    """Learn a per-axis linear fix-up from the validation dots.

    Webcam gaze models tend to carry a systematic bias (for example the top
    of the screen read as lower than it is). The calibration fit can't see
    that, but the accuracy-check dots can. Returns (correction, held-out
    median error in px) -- the error is leave-one-dot-out, so the reported
    accuracy is never measured on the dots the correction was fitted to.
    """
    usable = [p for p in points.values() if p.get("usable") and p.get("raw_x") is not None]
    if len(usable) < MIN_CORRECTION_POINTS:
        return None, None
    rx = np.array([p["raw_x"] for p in usable]); ry = np.array([p["raw_y"] for p in usable])
    tx = np.array([p["target_x"] for p in usable]); ty = np.array([p["target_y"] for p in usable])
    w, h = model.screen_width, model.screen_height
    held_out = []
    for i in range(len(usable)):
        keep = np.arange(len(usable)) != i
        ax, bx = _fit_axis(rx[keep], tx[keep])
        ay, by = _fit_axis(ry[keep], ty[keep])
        held_out.append(float(np.hypot((ax * rx[i] + bx - tx[i]) * w, (ay * ry[i] + by - ty[i]) * h)))
    ax, bx = _fit_axis(rx, tx)
    ay, by = _fit_axis(ry, ty)
    return {"x": [ax, bx], "y": [ay, by], "n_points": len(usable)}, float(np.median(held_out))


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
