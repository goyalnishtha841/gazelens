"""
backend/cv -- live pupil detection.

    from cv import get_pipeline
    result = get_pipeline().process_encoded(frame_b64)   # -> FrameResult

Knows nothing about calibration, screens, or sessions. Give it a frame, get
pupil coordinates back. Shared unchanged by calibration today and by live
gaze estimation once that exists.

A note on imports: backend/agents uses flat sibling imports (`from schemas
import ...`) and is run from inside its own directory. That doesn't extend
to here -- backend/cv and backend/calibration BOTH define a schemas.py, and
they have to import each other, so flat imports plus a sys.path insert would
let one package's schemas shadow the other's. These two packages therefore
use ordinary relative imports. Scripts inside them (test_cv.py,
webcam_demo.py) put backend/ on sys.path themselves so they still run
directly, the same way test_agents.py does.
"""

from .schemas import (
    SIDES,
    EyeRegion,
    FrameResult,
    PupilDetection,
    empty_result,
)
from .frame_source import (
    FrameDecodeError,
    decode_base64_frame,
    encode_frame_base64,
    webcam_frames,
)
from .landmarks import EyeLandmarker, LandmarkerUnavailable
from .pupil_detector import (
    DEFAULT_CONF,
    DEFAULT_WEIGHTS,
    DetectorUnavailable,
    PupilDetector,
)
from .pipeline import PupilPipeline, get_pipeline, set_pipeline

__all__ = [
    "SIDES",
    "EyeRegion",
    "PupilDetection",
    "FrameResult",
    "empty_result",
    "EyeLandmarker",
    "LandmarkerUnavailable",
    "PupilDetector",
    "DetectorUnavailable",
    "DEFAULT_WEIGHTS",
    "DEFAULT_CONF",
    "PupilPipeline",
    "get_pipeline",
    "set_pipeline",
    "decode_base64_frame",
    "encode_frame_base64",
    "webcam_frames",
    "FrameDecodeError",
]
