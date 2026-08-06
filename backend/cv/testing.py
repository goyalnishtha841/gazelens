"""
testing.py

Synthetic stand-ins for the real CV stack, so calibration can be tested end
to end on a machine with no webcam, no models/*.pt (it's gitignored), and no
mediapipe wheel for its Python version.

This is the same trick backend/agents used with mock_sessions.py: build the
module against a written-down contract and a fake data source, so it can be
finished and verified before the thing upstream of it exists.

StubPipeline is a drop-in for PupilPipeline -- same two methods, same
FrameResult out -- installed via cv.set_pipeline().
"""

import time
import uuid
from typing import Dict, List, Tuple

from .schemas import EyeRegion, FrameResult, PupilDetection, empty_result

DEFAULT_FRAME_W = 640
DEFAULT_FRAME_H = 480


def synthetic_frame(width: int = DEFAULT_FRAME_W, height: int = DEFAULT_FRAME_H):
    """A grey frame with two dark blobs where eyes would be.

    Not realistic enough to fool the real detector -- it exists so the HTTP
    path has actual image bytes to carry, and so decode/shape handling is
    exercised. Detection itself is stubbed. Requires numpy only.
    """
    import numpy as np

    frame = np.full((height, width, 3), 128, dtype=np.uint8)
    for cx in (int(width * 0.35), int(width * 0.65)):
        cy = int(height * 0.45)
        frame[cy - 12:cy + 12, cx - 20:cx + 20] = 60   # eye socket
        frame[cy - 5:cy + 5, cx - 5:cx + 5] = 10       # pupil
    return frame


def synthetic_eye_frame(
    regions=None,
    width: int = DEFAULT_FRAME_W,
    height: int = DEFAULT_FRAME_H,
):
    """A frame with drawn eyes inside the given boxes.

    Unlike synthetic_frame's flat grey blobs, these are shaped like the eye
    crops the detector actually receives -- pale sclera, mid-grey iris, dark
    pupil, specular highlight -- so a real YOLO model can be run over them.

    `regions` is an iterable of (x1, y1, x2, y2) in pixels; it defaults to the
    boxes the test suite's stub landmarker reports, so the two line up without
    the caller restating them. numpy only, no OpenCV.
    """
    import numpy as np

    if regions is None:
        regions = [(100, 200, 160, 230), (300, 200, 380, 240)]

    frame = np.full((height, width, 3), 150, dtype=np.uint8)

    for x1, y1, x2, y2 in regions:
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = w / 2.0, h / 2.0

        sclera = ((xx - cx) / (w * 0.46)) ** 2 + ((yy - cy) / (h * 0.42)) ** 2 <= 1.0
        iris_r = min(w, h) * 0.30
        iris = (xx - cx) ** 2 + (yy - cy) ** 2 <= iris_r ** 2
        pupil = (xx - cx) ** 2 + (yy - cy) ** 2 <= (iris_r * 0.55) ** 2

        patch = frame[y1:y2, x1:x2]
        patch[sclera] = 225
        patch[iris] = 90
        patch[pupil] = 20
        # highlight -- real pupils have one, and its absence makes a pupil
        # trivially findable in a way real ones aren't
        hl = (xx - (cx + iris_r * 0.25)) ** 2 + (yy - (cy - iris_r * 0.25)) ** 2
        patch[hl <= max(1.0, iris_r * 0.16) ** 2] = 245

    return frame


def synthetic_frame_b64(width: int = DEFAULT_FRAME_W, height: int = DEFAULT_FRAME_H) -> str:
    """The same frame, base64 JPEG, as the browser would post it.

    Needs OpenCV. Tests that must run without it should use
    StubPipeline(require_decode=False) and send any placeholder string.
    """
    from .frame_source import encode_frame_base64

    return encode_frame_base64(synthetic_frame(width, height))


class StubPipeline:
    """Deterministic fake pupils that MOVE with the calibration target.

    The point of moving them: a stub that returns a constant would let a
    broken pairing (target N stored against point M's pupils) pass the
    tests. Driving eye_norm from the target means the stored rows are only
    self-consistent if the wiring is actually right, which is the one thing
    these tests exist to prove.

    Set the current target with `aim_at(x, y)` before submitting frames.
    """

    def __init__(
        self,
        frame_size: Tuple[int, int] = (DEFAULT_FRAME_W, DEFAULT_FRAME_H),
        confidence: float = 0.91,
        fail_next: int = 0,
        require_decode: bool = False,
    ):
        self.frame_width, self.frame_height = frame_size
        self.confidence = confidence
        # Number of upcoming frames to report as misses, for testing how the
        # endpoint handles blinks / dropped detections.
        self.fail_next = fail_next
        self.require_decode = require_decode
        self.calls: List[str] = []
        self._target: Tuple[float, float] = (0.5, 0.5)

    # ------------------------------------------------------------------

    def aim_at(self, x: float, y: float) -> None:
        """Pretend the participant is looking at this normalised screen point."""
        self._target = (x, y)

    @property
    def available(self) -> bool:
        return True

    def process_frame(self, frame_bgr, frame_id=None, timestamp=None) -> FrameResult:
        frame_id = frame_id or uuid.uuid4().hex[:12]
        timestamp = time.time() if timestamp is None else timestamp
        self.calls.append(frame_id)

        if self.fail_next > 0:
            self.fail_next -= 1
            return empty_result(
                frame_id, timestamp, self.frame_width, self.frame_height,
                "no_pupil_detected",
            )

        return self._result(frame_id, timestamp)

    def process_encoded(self, payload: str, frame_id=None, timestamp=None) -> FrameResult:
        if self.require_decode:
            from .frame_source import decode_base64_frame

            frame = decode_base64_frame(payload)
            return self.process_frame(frame, frame_id=frame_id, timestamp=timestamp)

        if not payload:
            return empty_result(
                frame_id or uuid.uuid4().hex[:12],
                time.time() if timestamp is None else timestamp,
                0, 0, "decode_error: empty frame payload",
            )
        return self.process_frame(None, frame_id=frame_id, timestamp=timestamp)

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------

    def _result(self, frame_id: str, timestamp: float) -> FrameResult:
        tx, ty = self._target
        w, h = self.frame_width, self.frame_height

        pupils: Dict[str, PupilDetection] = {}
        regions: Dict[str, EyeRegion] = {}
        for side, base_x in (("left", 0.35), ("right", 0.65)):
            region = EyeRegion(
                side=side,
                x1=int(w * (base_x - 0.06)), y1=int(h * 0.40),
                x2=int(w * (base_x + 0.06)), y2=int(h * 0.50),
            )
            regions[side] = region

            # Pupil sits in the middle of the eye at centre-screen and
            # travels roughly +/-30% of the eye box towards the target --
            # a crude but monotonic stand-in for the real relationship.
            x_eye = 0.5 + (tx - 0.5) * 0.6
            y_eye = 0.5 + (ty - 0.5) * 0.6
            x_px = region.x1 + x_eye * region.width
            y_px = region.y1 + y_eye * region.height

            pupils[side] = PupilDetection(
                side=side,
                x_px=x_px, y_px=y_px,
                x_frame=x_px / w, y_frame=y_px / h,
                x_eye=x_eye, y_eye=y_eye,
                confidence=self.confidence,
                bbox_px=(x_px - 4, y_px - 4, x_px + 4, y_px + 4),
                eye_region=region,
            )

        return FrameResult(
            frame_id=frame_id,
            timestamp=timestamp,
            frame_width=w,
            frame_height=h,
            face_found=True,
            pupils=pupils,
            eye_regions=regions,
            head_proxy={
                "interocular_norm": 0.30,
                "eye_mid_x": 0.5, "eye_mid_y": 0.45,
                "roll_norm": 0.0, "nose_x": 0.5, "nose_y": 0.55,
            },
        )


__all__ = [
    "StubPipeline",
    "synthetic_frame",
    "synthetic_eye_frame",
    "synthetic_frame_b64",
]
