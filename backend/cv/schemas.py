"""
schemas.py

The CONTRACT between the CV layer and everything that consumes pupil
positions -- calibration today, live gaze estimation tomorrow.

Deliberately plain dataclasses, matching backend/agents/schemas.py.
Pydantic only shows up at the HTTP boundary (backend/calibration/schemas.py);
nothing in here should know that FastAPI exists.

Coordinate conventions -- there are three, and mixing them up is the
easiest way to silently break the regression model later, so they are
named explicitly everywhere:

  * pixel        -- (x, y) in full-frame pixels, origin top-left
  * frame_norm   -- pixel / (frame_w, frame_h), so [0, 1] regardless of
                    the webcam's resolution
  * eye_norm     -- position WITHIN the eye bounding box, [0, 1].
                    This is the feature that actually matters for gaze:
                    it is invariant to where the head sits in the frame,
                    so it survives the user shifting in their chair.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Tuple

# Which eye a detection belongs to. "left"/"right" are from the
# CAMERA's point of view (image-left = the participant's right eye),
# because that is what the pixel coordinates actually describe.
SIDES = ("left", "right")


@dataclass
class EyeRegion:
    """An eye crop box in full-frame pixels, from the face landmarker."""

    side: str                  # "left" | "right"
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PupilDetection:
    """One pupil, localised by the YOLO detector inside an eye crop."""

    side: str

    # centre, in all three conventions (see module docstring)
    x_px: float
    y_px: float
    x_frame: float
    y_frame: float
    x_eye: float
    y_eye: float

    confidence: float
    bbox_px: Tuple[float, float, float, float]   # x1, y1, x2, y2 full-frame
    eye_region: Optional[EyeRegion] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bbox_px"] = list(self.bbox_px)
        return d


@dataclass
class FrameResult:
    """Everything the CV layer knows about a single frame.

    A FrameResult is always returned, even when nothing was found -- the
    caller decides whether a miss is fatal. Silently dropping frames here
    would hide blink/dropout rates that the calibration quality check
    actually wants to see.
    """

    frame_id: str
    timestamp: float                     # seconds, capture time
    frame_width: int
    frame_height: int

    face_found: bool = False
    pupils: Dict[str, PupilDetection] = field(default_factory=dict)
    eye_regions: Dict[str, EyeRegion] = field(default_factory=dict)

    # Coarse head-position proxy, so gaze_estimation can later condition on
    # (or reject) samples where the head moved between calibration and use.
    # Not a real 6-DoF pose -- just cheap, stable quantities from landmarks.
    head_proxy: Optional[Dict[str, float]] = None

    note: str = ""                       # why a frame came back empty

    @property
    def left(self) -> Optional[PupilDetection]:
        return self.pupils.get("left")

    @property
    def right(self) -> Optional[PupilDetection]:
        return self.pupils.get("right")

    @property
    def has_any_pupil(self) -> bool:
        return bool(self.pupils)

    @property
    def has_both_pupils(self) -> bool:
        return "left" in self.pupils and "right" in self.pupils

    @property
    def mean_confidence(self) -> float:
        if not self.pupils:
            return 0.0
        return sum(p.confidence for p in self.pupils.values()) / len(self.pupils)

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "face_found": self.face_found,
            "pupils": {s: p.to_dict() for s, p in self.pupils.items()},
            "eye_regions": {s: r.to_dict() for s, r in self.eye_regions.items()},
            "head_proxy": self.head_proxy,
            "note": self.note,
        }


def empty_result(frame_id: str, timestamp: float, w: int, h: int, note: str) -> FrameResult:
    """A frame where detection failed -- kept explicit rather than None."""
    return FrameResult(
        frame_id=frame_id,
        timestamp=timestamp,
        frame_width=w,
        frame_height=h,
        face_found=False,
        note=note,
    )


__all__ = [
    "SIDES",
    "EyeRegion",
    "PupilDetection",
    "FrameResult",
    "empty_result",
]
