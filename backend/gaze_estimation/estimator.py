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
    ) -> GazePoint:
        """Pupil positions (eye-normalised) -> a GazePoint."""
        timestamp = time.time() if timestamp is None else timestamp

        if left is None and right is None:
            return invalid_point(timestamp, "no_pupil", confidence)

        predicted = self.model.predict_one(left, right, clip=True)
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
            note="" if in_bounds else "off_screen",
        )

    def estimate_frame_result(self, result) -> GazePoint:
        """Convenience for the live loop: a cv.FrameResult -> a GazePoint.

        Duck-typed on purpose (see module docstring) -- reads `.left`,
        `.right`, `.timestamp`, `.mean_confidence` without importing cv.
        """
        left = getattr(result, "left", None)
        right = getattr(result, "right", None)
        return self.estimate(
            left=(left.x_eye, left.y_eye) if left else None,
            right=(right.x_eye, right.y_eye) if right else None,
            timestamp=getattr(result, "timestamp", None),
            confidence=getattr(result, "mean_confidence", 0.0),
        )

    def estimate_batch(self, frames: Sequence[Dict]) -> List[GazePoint]:
        """A burst of frames -> a gaze stream slice.

        Each frame is {"left": (x,y)|None, "right": (x,y)|None,
        "timestamp": float, "confidence": float}.
        """
        return [
            self.estimate(
                left=f.get("left"),
                right=f.get("right"),
                timestamp=f.get("timestamp"),
                confidence=f.get("confidence", 1.0),
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
]
