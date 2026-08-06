"""
pipeline.py

The single entry point the rest of the backend uses:

    from cv import get_pipeline
    result = get_pipeline().process_encoded(frame_b64)

PupilPipeline is the seam between "some source of frames" and "pupil
coordinates". Calibration talks to this, and live gaze estimation will talk
to the same object later -- neither needs to know about MediaPipe, YOLO,
base64, or OpenCV.

The process-wide singleton exists because loading the YOLO weights takes a
second or two and holding a FaceMesh open keeps tracking state warm. Doing
that per request would make the calibration loop unusable.
"""

import time
import uuid
from typing import Optional

from .schemas import FrameResult, empty_result
from .frame_source import FrameDecodeError, decode_base64_frame
from .pupil_detector import PupilDetector


class PupilPipeline:
    """Frames (array or base64) -> FrameResult."""

    def __init__(self, detector: Optional[PupilDetector] = None):
        self.detector = detector if detector is not None else PupilDetector()

    @property
    def available(self) -> bool:
        return self.detector.available

    def process_frame(
        self,
        frame_bgr,
        frame_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> FrameResult:
        return self.detector.detect(frame_bgr, frame_id=frame_id, timestamp=timestamp)

    def process_encoded(
        self,
        payload: str,
        frame_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> FrameResult:
        """Decode a base64 frame from the browser, then detect.

        A frame that won't decode comes back as an empty FrameResult with a
        note rather than an exception: during calibration the client is
        posting a burst of frames per point, and one corrupt frame should
        cost one sample, not the whole point.
        """
        frame_id = frame_id or uuid.uuid4().hex[:12]
        timestamp = time.time() if timestamp is None else timestamp
        try:
            frame = decode_base64_frame(payload)
        except FrameDecodeError as exc:
            return empty_result(frame_id, timestamp, 0, 0, f"decode_error: {exc}")
        return self.process_frame(frame, frame_id=frame_id, timestamp=timestamp)

    def close(self) -> None:
        self.detector.close()


# ----------------------------------------------------------------------
# process-wide singleton

_pipeline: Optional[PupilPipeline] = None


def get_pipeline() -> PupilPipeline:
    """The shared pipeline. Constructed lazily, weights loaded lazily again
    inside the detector, so importing this never touches the filesystem."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PupilPipeline()
    return _pipeline


def set_pipeline(pipeline: Optional[PupilPipeline]) -> None:
    """Swap the shared pipeline.

    This is how test_calibration.py drives the endpoint end to end with
    synthetic frames and no webcam, no weights, and no mediapipe -- it
    installs a StubPipeline here before calling the routes. Pass None to
    reset.
    """
    global _pipeline
    _pipeline = pipeline


__all__ = ["PupilPipeline", "get_pipeline", "set_pipeline"]
