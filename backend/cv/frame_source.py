"""
frame_source.py

Getting frames into the detector, from the two places they come from:

  * the browser, as base64 JPEG/PNG over HTTP (calibration, live session)
  * a local webcam via OpenCV (webcam_demo.py, offline testing)

Both end up as the same BGR numpy array, so backend/cv/pupil_detector.py
never has to care which one it's looking at.
"""

import base64
import binascii
import re
from typing import Iterator, Optional

import numpy as np

# Browsers send canvas.toDataURL() output: "data:image/jpeg;base64,/9j/4AAQ..."
_DATA_URL_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)

# Guard against a malformed or hostile client posting a huge payload. A
# 640x480 JPEG is ~50KB; 8MB is generous headroom for a 4K still.
MAX_FRAME_BYTES = 8 * 1024 * 1024


class FrameDecodeError(ValueError):
    """The posted frame wasn't decodable image data."""


def decode_base64_frame(payload: str):
    """base64 (with or without data-URL prefix) -> BGR numpy array."""
    if not payload:
        raise FrameDecodeError("empty frame payload")

    import cv2  # local import so the module stays importable without OpenCV

    stripped = _DATA_URL_RE.sub("", payload).strip()
    try:
        raw = base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FrameDecodeError(f"not valid base64: {exc}") from exc

    if len(raw) > MAX_FRAME_BYTES:
        raise FrameDecodeError(
            f"frame is {len(raw)} bytes, over the {MAX_FRAME_BYTES} byte limit"
        )

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise FrameDecodeError("base64 decoded, but the bytes aren't a readable image")
    return frame


def encode_frame_base64(frame_bgr, quality: int = 85) -> str:
    """BGR array -> base64 JPEG. Used by the tests and the demo overlay."""
    import cv2

    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise FrameDecodeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def webcam_frames(
    camera_index: int = 0,
    width: Optional[int] = 640,
    height: Optional[int] = 480,
) -> Iterator["np.ndarray"]:
    """Yield frames from a local webcam until the stream ends or the caller stops.

    640x480 by default: the detector runs on eye crops, so a larger capture
    buys almost no accuracy while costing real latency on CPU.
    """
    import cv2

    cap = cv2.VideoCapture(camera_index)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    if not cap.isOpened():
        raise RuntimeError(f"could not open camera {camera_index}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()


__all__ = [
    "decode_base64_frame",
    "encode_frame_base64",
    "webcam_frames",
    "FrameDecodeError",
    "MAX_FRAME_BYTES",
]
