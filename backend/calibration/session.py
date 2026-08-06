"""
session.py

The calibration session itself: which points, which samples came back for
each, and whether the result is good enough to train a gaze model on.

This is the module that defines the CONTRACT with backend/gaze_estimation
(not built yet). That contract is `CalibrationSample.to_training_row()`:
one flat dict per captured sample, features and target side by side, ready
to go straight into a regression fit without any further joining.

Same discipline as backend/agents/schemas.py -- the shape is written down
here, in one place, so the module downstream can be built against it before
either side is finished.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .points import DEFAULT_PATTERN, CalibrationPoint, PATTERNS, generate_points

# How many usable frames we want per target. ~15 at 20-30fps is well under a
# second of fixation, and averaging over them cancels most of the per-frame
# jitter in the detector.
DEFAULT_SAMPLES_PER_POINT = 15

# Below this, a point is treated as not calibrated. Fitting a mapping from
# 2 noisy samples is worse than admitting the point failed.
MIN_SAMPLES_PER_POINT = 5

# Sessions must cover this fraction of their points to be usable.
MIN_POINT_COVERAGE = 0.75

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_ABANDONED = "abandoned"


@dataclass
class CalibrationSample:
    """One frame's worth of pupil data, paired with the target being shown.

    Both eyes are stored separately rather than averaged. Averaging is a
    decision for the gaze model, and doing it here would destroy the
    information needed to detect (or exploit) the asymmetry between eyes.
    """

    sample_id: str
    point_index: int
    target_x: float
    target_y: float

    # from cv.FrameResult -- None when that eye wasn't found this frame
    left_x_eye: Optional[float]
    left_y_eye: Optional[float]
    right_x_eye: Optional[float]
    right_y_eye: Optional[float]
    left_x_frame: Optional[float]
    left_y_frame: Optional[float]
    right_x_frame: Optional[float]
    right_y_frame: Optional[float]

    confidence: float
    head_proxy: Optional[Dict[str, float]]

    frame_width: int
    frame_height: int
    timestamp: float
    eyes_detected: int          # 0, 1 or 2

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "point_index": self.point_index,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "left_x_eye": self.left_x_eye,
            "left_y_eye": self.left_y_eye,
            "right_x_eye": self.right_x_eye,
            "right_y_eye": self.right_y_eye,
            "left_x_frame": self.left_x_frame,
            "left_y_frame": self.left_y_frame,
            "right_x_frame": self.right_x_frame,
            "right_y_frame": self.right_y_frame,
            "confidence": self.confidence,
            "head_proxy": self.head_proxy,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "timestamp": self.timestamp,
            "eyes_detected": self.eyes_detected,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationSample":
        return cls(**d)

    def to_training_row(self, session: "CalibrationSession") -> dict:
        """THE contract with backend/gaze_estimation.

        Flat, fully self-describing, no nesting: everything a regression fit
        needs for this sample, including the session-level context it would
        otherwise have to look up. Screen size travels with every row so a
        model trained across several participants' sessions can normalise or
        filter on it.
        """
        head = self.head_proxy or {}
        return {
            # --- features ---
            "left_x_eye": self.left_x_eye,
            "left_y_eye": self.left_y_eye,
            "right_x_eye": self.right_x_eye,
            "right_y_eye": self.right_y_eye,
            "left_x_frame": self.left_x_frame,
            "left_y_frame": self.left_y_frame,
            "right_x_frame": self.right_x_frame,
            "right_y_frame": self.right_y_frame,
            "interocular_norm": head.get("interocular_norm"),
            "eye_mid_x": head.get("eye_mid_x"),
            "eye_mid_y": head.get("eye_mid_y"),
            "roll_norm": head.get("roll_norm"),
            # --- target (what we're regressing onto) ---
            "target_x": self.target_x,
            "target_y": self.target_y,
            # --- context / filtering ---
            "session_id": session.session_id,
            "participant_id": session.participant_id,
            "point_index": self.point_index,
            "confidence": self.confidence,
            "eyes_detected": self.eyes_detected,
            "screen_width": session.screen_width,
            "screen_height": session.screen_height,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "timestamp": self.timestamp,
        }


# Column order for the CSV export, so the file is stable across runs.
TRAINING_ROW_COLUMNS = [
    "left_x_eye", "left_y_eye", "right_x_eye", "right_y_eye",
    "left_x_frame", "left_y_frame", "right_x_frame", "right_y_frame",
    "interocular_norm", "eye_mid_x", "eye_mid_y", "roll_norm",
    "target_x", "target_y",
    "session_id", "participant_id", "point_index", "confidence",
    "eyes_detected", "screen_width", "screen_height",
    "frame_width", "frame_height", "timestamp",
]


@dataclass
class CalibrationSession:
    """One participant's calibration run."""

    session_id: str
    participant_id: str
    pattern: int
    screen_width: int
    screen_height: int
    samples_per_point: int = DEFAULT_SAMPLES_PER_POINT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = STATUS_IN_PROGRESS
    samples: List[CalibrationSample] = field(default_factory=list)
    # Frames that arrived but produced no usable pupil. Counted, not stored:
    # the count is what tells you a calibration was poor, the frames aren't
    # worth the disk.
    rejected_frames: int = 0

    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        participant_id: str,
        pattern: int = DEFAULT_PATTERN,
        screen_width: int = 1920,
        screen_height: int = 1080,
        samples_per_point: int = DEFAULT_SAMPLES_PER_POINT,
    ) -> "CalibrationSession":
        if pattern not in PATTERNS:
            raise ValueError(
                f"unsupported calibration pattern {pattern!r}; "
                f"expected one of {sorted(PATTERNS)}"
            )
        return cls(
            session_id=f"cal_{uuid.uuid4().hex[:12]}",
            participant_id=participant_id,
            pattern=pattern,
            screen_width=screen_width,
            screen_height=screen_height,
            samples_per_point=samples_per_point,
        )

    @property
    def points(self) -> List[CalibrationPoint]:
        return generate_points(self.pattern)

    # ------------------------------------------------------------------

    def add_sample(self, sample: CalibrationSample) -> None:
        self.samples.append(sample)
        self.updated_at = time.time()

    def record_rejection(self) -> None:
        self.rejected_frames += 1
        self.updated_at = time.time()

    def samples_for_point(self, point_index: int) -> List[CalibrationSample]:
        return [s for s in self.samples if s.point_index == point_index]

    def sample_counts(self) -> Dict[int, int]:
        """{point_index: usable sample count} for every point, including zeros.

        Zeros are included on purpose -- "point 11 has no data" is the thing
        the frontend needs to know to re-present it, and a dict that silently
        omits missing keys hides exactly that.
        """
        counts = {p.index: 0 for p in self.points}
        for s in self.samples:
            if s.point_index in counts:
                counts[s.point_index] += 1
        return counts

    def points_remaining(self) -> List[int]:
        """Points still short of samples_per_point."""
        return [i for i, n in sorted(self.sample_counts().items())
                if n < self.samples_per_point]

    def covered_points(self) -> List[int]:
        """Points with enough samples to be worth training on."""
        return [i for i, n in sorted(self.sample_counts().items())
                if n >= MIN_SAMPLES_PER_POINT]

    # ------------------------------------------------------------------

    def quality(self) -> dict:
        """Whether this calibration is good enough to build a model from.

        Reported rather than enforced: a marginal calibration is still worth
        keeping (the participant's time is expensive and the pilot study may
        want it), but gaze_estimation must be able to see that it's marginal.
        """
        counts = self.sample_counts()
        total_points = len(counts)
        covered = self.covered_points()
        coverage = len(covered) / total_points if total_points else 0.0
        total_frames = len(self.samples) + self.rejected_frames
        detection_rate = len(self.samples) / total_frames if total_frames else 0.0
        both_eyes = sum(1 for s in self.samples if s.eyes_detected == 2)

        reasons: List[str] = []
        if coverage < MIN_POINT_COVERAGE:
            missing = sorted(set(counts) - set(covered))
            reasons.append(
                f"only {len(covered)}/{total_points} points have "
                f">={MIN_SAMPLES_PER_POINT} samples (missing: {missing})"
            )
        if detection_rate < 0.5 and total_frames:
            reasons.append(
                f"pupils found in only {detection_rate:.0%} of submitted frames"
            )

        return {
            "usable": not reasons,
            "reasons": reasons,
            "point_coverage": round(coverage, 3),
            "points_covered": len(covered),
            "points_total": total_points,
            "total_samples": len(self.samples),
            "rejected_frames": self.rejected_frames,
            "detection_rate": round(detection_rate, 3),
            "both_eyes_rate": round(both_eyes / len(self.samples), 3) if self.samples else 0.0,
            "mean_confidence": (
                round(sum(s.confidence for s in self.samples) / len(self.samples), 3)
                if self.samples else 0.0
            ),
        }

    def is_complete(self) -> bool:
        """Every point has its full sample quota."""
        return not self.points_remaining()

    def training_rows(self) -> List[dict]:
        """All samples as flat rows -- what gaze_estimation consumes."""
        return [s.to_training_row(self) for s in self.samples]

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "pattern": self.pattern,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "samples_per_point": self.samples_per_point,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "rejected_frames": self.rejected_frames,
            "points": [p.to_dict() for p in self.points],
            "quality": self.quality(),
            "samples": [s.to_dict() for s in self.samples],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationSession":
        session = cls(
            session_id=d["session_id"],
            participant_id=d["participant_id"],
            pattern=d["pattern"],
            screen_width=d["screen_width"],
            screen_height=d["screen_height"],
            samples_per_point=d.get("samples_per_point", DEFAULT_SAMPLES_PER_POINT),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            status=d.get("status", STATUS_IN_PROGRESS),
            rejected_frames=d.get("rejected_frames", 0),
        )
        # "points" and "quality" are derived on read, not restored -- keeping
        # them in the file makes it readable by hand, but the objects stay
        # the single source of truth.
        session.samples = [CalibrationSample.from_dict(s) for s in d.get("samples", [])]
        return session


def sample_from_frame_result(
    result,
    point_index: int,
    target_x: float,
    target_y: float,
) -> Optional[CalibrationSample]:
    """cv.FrameResult -> CalibrationSample, or None if the frame was a miss.

    This is the only place the two modules touch. If cv's FrameResult shape
    changes, this function is what needs updating -- nothing else in
    calibration reads it.
    """
    if not result.has_any_pupil:
        return None

    left = result.left
    right = result.right
    return CalibrationSample(
        sample_id=uuid.uuid4().hex[:12],
        point_index=point_index,
        target_x=target_x,
        target_y=target_y,
        left_x_eye=left.x_eye if left else None,
        left_y_eye=left.y_eye if left else None,
        right_x_eye=right.x_eye if right else None,
        right_y_eye=right.y_eye if right else None,
        left_x_frame=left.x_frame if left else None,
        left_y_frame=left.y_frame if left else None,
        right_x_frame=right.x_frame if right else None,
        right_y_frame=right.y_frame if right else None,
        confidence=result.mean_confidence,
        head_proxy=result.head_proxy,
        frame_width=result.frame_width,
        frame_height=result.frame_height,
        timestamp=result.timestamp,
        eyes_detected=len(result.pupils),
    )


__all__ = [
    "CalibrationSample",
    "CalibrationSession",
    "sample_from_frame_result",
    "TRAINING_ROW_COLUMNS",
    "DEFAULT_SAMPLES_PER_POINT",
    "MIN_SAMPLES_PER_POINT",
    "MIN_POINT_COVERAGE",
    "STATUS_IN_PROGRESS",
    "STATUS_COMPLETE",
    "STATUS_ABANDONED",
]
