"""
estimator.py

Live inference: pupil coordinates in, screen coordinates out, per frame.

    est = get_estimator("cal_a1b2c3d4e5f6")     # loads once, cached
    point = est.estimate(left=(0.51, 0.48), right=(0.49, 0.49), timestamp=t)
    # -> GazePoint(x=0.63, y=0.41, ...)

The cost per call is a feature build, one small matrix multiply, and a
clamp. Nothing retrains, nothing touches disk, nothing scales with how long
the session has been running -- a model is loaded from disk at most once per
session and then held in memory. That is the whole point of persisting the
trained model: calibration happens once, not per gaze estimate.

This module never imports backend/cv. `estimate_frame_result` reads the
attributes a cv.FrameResult exposes (`.left`, `.right`, `.timestamp`) by
duck typing, so the two modules stay decoupled and this one remains testable
with plain tuples.

The output stream is what backend/attribution will consume -- see
CONTRACT.md. Deliberately raw: no fixation detection, no dwell aggregation,
no element mapping. Those are attribution's job, and doing any of them here
would mean attribution could never change its mind about them.
"""

import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .model import GazeModel
from .training import load_model

Pupil = Optional[Tuple[float, float]]


@dataclass
class GazePoint:
    """One gaze estimate. The atom of the stream attribution reads."""

    timestamp: float
    x: float                  # normalised [0,1] screen coords
    y: float
    x_px: float               # same point in pixels, for heatmaps/overlays
    y_px: float
    valid: bool               # False when no pupil was available this frame
    in_bounds: bool           # False when the raw prediction fell off-screen
    confidence: float         # carried through from the detector
    note: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def invalid_point(timestamp: float, note: str, confidence: float = 0.0) -> GazePoint:
    """A frame that produced no gaze.

    Emitted rather than skipped: attribution needs to know the difference
    between "looked away" and "the detector blinked", and a silently missing
    frame reads as neither. Gaps in a gaze stream also inflate dwell time on
    whatever element was being looked at either side of them.
    """
    return GazePoint(
        timestamp=timestamp, x=0.0, y=0.0, x_px=0.0, y_px=0.0,
        valid=False, in_bounds=False, confidence=confidence, note=note,
    )


# How far the head may move from its calibration pose before gaze points
# carry note="head_moved". Past this the iris-to-screen mapping was learned
# for a different geometry; the client prompts a recalibration.
HEAD_DRIFT_DEG = 8.0          # yaw or pitch
HEAD_DRIFT_DEPTH_FRAC = 0.15  # relative change in distance from camera


def head_moved(head_proxy: Optional[Dict[str, float]], pose_ref: Dict[str, float]) -> bool:
    if not head_proxy or not pose_ref:
        return False
    for col in ("head_yaw", "head_pitch"):
        if (col in pose_ref and head_proxy.get(col) is not None
                and abs(head_proxy[col] - pose_ref[col]) > HEAD_DRIFT_DEG):
            return True
    ref_z, z = pose_ref.get("head_tz"), head_proxy.get("head_tz")
    return bool(ref_z and z is not None
                and abs(z - ref_z) / abs(ref_z) > HEAD_DRIFT_DEPTH_FRAC)


# Pre-test position check: a short burst of frames taken just before a new
# test starts, compared with the calibration pose. Same thresholds as the
# per-frame "head_moved" note above, but on the MEDIAN of the burst, so one
# odd frame can't block a test and a real move can't hide behind one good
# frame. Fewer usable frames than this and nothing can be said.
MIN_POSITION_FRAMES = 3


def position_check(head_proxies: Sequence[Optional[Dict[str, float]]],
                   pose_ref: Dict[str, float]) -> Dict:
    """Has the participant moved since calibrating? -> a dict for the API.

    status: "ok" | "moved" | "no_face" (too few frames with a face) |
    "unknown" (the model predates pose references, so there is nothing to
    compare against -- the test is allowed, as it was before this check).
    """
    frames = len(head_proxies)
    usable = [h for h in head_proxies if h]
    result: Dict = {
        "status": "unknown", "moved": False, "frames": frames,
        "frames_with_face": len(usable), "reasons": [],
        "yaw_change_deg": None, "pitch_change_deg": None, "distance_change_pct": None,
        "thresholds": {"angle_deg": HEAD_DRIFT_DEG,
                       "distance_pct": round(100 * HEAD_DRIFT_DEPTH_FRAC, 1)},
    }
    if not pose_ref:
        return result
    if len(usable) < MIN_POSITION_FRAMES:
        result["status"] = "no_face"
        return result

    def median(col: str) -> Optional[float]:
        vals = sorted(h[col] for h in usable if h.get(col) is not None)
        if not vals:
            return None
        m = len(vals) // 2
        return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2

    reasons: List[str] = []
    for col, key, turn in (("head_yaw", "yaw_change_deg", "turned left or right"),
                           ("head_pitch", "pitch_change_deg", "tilted up or down")):
        now = median(col)
        if col in pose_ref and now is not None:
            delta = now - pose_ref[col]
            result[key] = round(delta, 1)
            if abs(delta) > HEAD_DRIFT_DEG:
                reasons.append(f"your head is {turn} by {abs(delta):.0f}° "
                               f"(more than {HEAD_DRIFT_DEG:.0f}°)")

    ref_z, z = pose_ref.get("head_tz"), median("head_tz")
    if ref_z and z is not None:
        change = (abs(z) - abs(ref_z)) / abs(ref_z)
        result["distance_change_pct"] = round(100 * change, 1)
        if abs(change) > HEAD_DRIFT_DEPTH_FRAC:
            side = "farther from" if change > 0 else "closer to"
            reasons.append(f"you are {abs(change) * 100:.0f}% {side} the screen "
                           f"(more than {HEAD_DRIFT_DEPTH_FRAC * 100:.0f}%)")

    result["reasons"] = reasons
    result["moved"] = bool(reasons)
    result["status"] = "moved" if reasons else "ok"
    return result


class LiveGazeEstimator:
    """A loaded per-session model, ready to call per frame."""

    def __init__(self, model: GazeModel, smoothing: float = 0.0):
        self.model = model
        # Optional exponential smoothing, OFF by default. The stream handed to
        # attribution should be the raw measurement; smoothing shortens
        # saccades and stretches fixations, which is exactly the signal
        # attribution measures. Available for live on-screen cursors, where a
        # jittery dot looks broken.
        self.smoothing = float(smoothing)
        self._last: Optional[Tuple[float, float]] = None

    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self.model.session_id

    @property
    def screen(self) -> Tuple[int, int]:
        return self.model.screen_width, self.model.screen_height

    @property
    def median_error_px(self) -> Optional[float]:
        """The model's held-out accuracy, carried alongside every estimate.

        Anything consuming this stream should be able to state its own error
        bar without going back to the training run to find it.
        """
        return self.model.metrics.get("median_error_px")

    def reset(self) -> None:
        """Drop smoothing state -- call between distinct viewing tasks."""
        self._last = None

    # ------------------------------------------------------------------

    def estimate(
        self,
        left: Pupil = None,
        right: Pupil = None,
        timestamp: Optional[float] = None,
        confidence: float = 1.0,
        head_proxy: Optional[Dict[str, float]] = None,
    ) -> GazePoint:
        """Pupil positions (eye-normalised) -> a GazePoint.

        head_proxy: only read if this session's model was trained on
        "both_eyes_head" (see gaze_estimation/features.py) -- every other
        feature_set ignores it, so passing it here is always safe, never
        required.
        """
        timestamp = time.time() if timestamp is None else timestamp

        if left is None and right is None:
            return invalid_point(timestamp, "no_pupil", confidence)

        predicted = self.model.predict_one(left, right, clip=True, head_proxy=head_proxy)
        if predicted is None:
            # The model's feature set needed both eyes and only one arrived.
            return invalid_point(timestamp, "insufficient_pupils_for_feature_set",
                                 confidence)

        x, y, in_bounds = predicted

        if self.smoothing > 0.0 and self._last is not None:
            a = self.smoothing
            x = a * self._last[0] + (1 - a) * x
            y = a * self._last[1] + (1 - a) * y
        self._last = (x, y)

        w, h = self.screen
        return GazePoint(
            timestamp=timestamp,
            x=x, y=y,
            x_px=x * w, y_px=y * h,
            valid=True,
            in_bounds=in_bounds,
            confidence=confidence,
            note=("off_screen" if not in_bounds
                  else "head_moved" if head_moved(head_proxy, self.model.pose_ref)
                  else ""),
        )

    def estimate_frame_result(self, result) -> GazePoint:
        """Convenience for the live loop: a cv.FrameResult -> a GazePoint.

        Duck-typed on purpose (see module docstring) -- reads `.left`,
        `.right`, `.timestamp`, `.mean_confidence`, `.head_proxy` without
        importing cv.
        """
        left = getattr(result, "left", None)
        right = getattr(result, "right", None)
        return self.estimate(
            left=(left.x_eye, left.y_eye) if left else None,
            right=(right.x_eye, right.y_eye) if right else None,
            timestamp=getattr(result, "timestamp", None),
            confidence=getattr(result, "mean_confidence", 0.0),
            head_proxy=getattr(result, "head_proxy", None),
        )

    def estimate_batch(self, frames: Sequence[Dict]) -> List[GazePoint]:
        """A burst of frames -> a gaze stream slice.

        Each frame is {"left": (x,y)|None, "right": (x,y)|None,
        "timestamp": float, "confidence": float, "head_proxy": dict|None}.
        """
        return [
            self.estimate(
                left=f.get("left"),
                right=f.get("right"),
                timestamp=f.get("timestamp"),
                confidence=f.get("confidence", 1.0),
                head_proxy=f.get("head_proxy"),
            )
            for f in frames
        ]


# ----------------------------------------------------------------------
# process-wide cache, mirroring cv.get_pipeline() and calibration.get_store()


_estimators: Dict[str, LiveGazeEstimator] = {}
_model_dir_override: Optional[Path] = None


def set_model_dir(path: Optional[Path]) -> None:
    """Point the cache at a different model directory (used by the tests)."""
    global _model_dir_override
    _model_dir_override = Path(path) if path else None
    clear_cache()


def get_estimator(session_id: str, smoothing: float = 0.0) -> LiveGazeEstimator:
    """The estimator for a session, loading its model from disk at most once.

    Cached because a live session calls this on every frame: re-reading and
    re-parsing the model JSON 30 times a second would dominate the per-frame
    cost, which is otherwise a single small matrix multiply.
    """
    cached = _estimators.get(session_id)
    if cached is not None:
        cached.smoothing = smoothing
        return cached

    estimator = LiveGazeEstimator(
        load_model(session_id, _model_dir_override), smoothing=smoothing
    )
    _estimators[session_id] = estimator
    return estimator


def register_estimator(estimator: LiveGazeEstimator) -> None:
    """Put an already-built estimator in the cache (skips the disk read)."""
    _estimators[estimator.session_id] = estimator


def clear_estimator(session_id: str) -> bool:
    return _estimators.pop(session_id, None) is not None


def clear_cache() -> None:
    _estimators.clear()


def gaze_stream(
    estimator: LiveGazeEstimator,
    frames: Iterable[Dict],
) -> Iterable[GazePoint]:
    """Lazily map a stream of frames to a stream of GazePoints.

    A generator so a long live session never materialises the whole stream in
    memory -- attribution can consume it as it arrives.
    """
    for frame in frames:
        yield estimator.estimate(
            left=frame.get("left"),
            right=frame.get("right"),
            timestamp=frame.get("timestamp"),
            confidence=frame.get("confidence", 1.0),
            head_proxy=frame.get("head_proxy"),
        )


__all__ = [
    "GazePoint",
    "LiveGazeEstimator",
    "invalid_point",
    "get_estimator",
    "register_estimator",
    "clear_estimator",
    "clear_cache",
    "set_model_dir",
    "gaze_stream",
    "position_check",
]
