"""
pupil_detector.py

Wraps models/pupil_yolo_final.pt (YOLOv8n -- the detector the benchmark
picked for the live pipeline) for single-frame inference.

The public surface is deliberately one method:

    detector.detect(frame_bgr) -> FrameResult

No calibration awareness, no session state, no notion of a screen. That is
what lets calibration and, later, live gaze estimation share this unchanged.

CPU only. Ultralytics will happily grab CUDA if it sees it; we pin device
to "cpu" explicitly so behaviour is identical on the dev laptops and on
whatever machine runs the pilot study.
"""

import time
import uuid
from pathlib import Path
from typing import Optional

from .schemas import EyeRegion, FrameResult, PupilDetection, empty_result
from .landmarks import EyeLandmarker, LandmarkerUnavailable

# models/ sits at the repo root: backend/cv/pupil_detector.py -> ../../models
_MODELS = Path(__file__).resolve().parents[2] / "models"

# The real detector: YOLOv8n trained on LPW, the model behind the README's
# benchmark table. Gitignored, kept in Drive.
DEFAULT_WEIGHTS = _MODELS / "pupil_yolo_final.pt"

# A stand-in trained on synthetic eyes by scripts/make_smoketest_detector.py.
# Exists so a fresh clone can exercise the live pipeline at all -- models/*.pt
# is gitignored, so without it webcam_demo.py cannot start and the end-to-end
# path goes untested on every machine without Drive access.
SMOKETEST_WEIGHTS = _MODELS / "pupil_smoketest.pt"

# Escape hatch for anyone keeping weights outside the repo.
WEIGHTS_ENV_VAR = "GAZELENS_PUPIL_WEIGHTS"


def resolve_weights(explicit: Optional[Path] = None) -> tuple[Optional[Path], bool]:
    """Pick the weights to use. Returns (path, is_smoketest).

    Order: explicit argument, then $GAZELENS_PUPIL_WEIGHTS, then the real
    detector, then the synthetic smoke-test stand-in. Returns (None, False)
    when nothing is available.

    The real weights always win over the smoke-test ones, so dropping
    pupil_yolo_final.pt into models/ silently upgrades every caller. The
    is_smoketest flag exists so nothing can report a measurement taken with
    the stand-in without knowing it -- see PupilDetector.is_smoketest.
    """
    if explicit is not None:
        return Path(explicit), False

    from os import environ

    override = environ.get(WEIGHTS_ENV_VAR)
    if override:
        return Path(override), False
    if DEFAULT_WEIGHTS.exists():
        return DEFAULT_WEIGHTS, False
    if SMOKETEST_WEIGHTS.exists():
        return SMOKETEST_WEIGHTS, True
    return None, False

# The benchmark ran at YOLO's default 0.25. Kept the same so live behaviour
# matches the reported precision/recall rather than a quietly different
# operating point.
DEFAULT_CONF = 0.25


class DetectorUnavailable(RuntimeError):
    """Weights missing, or ultralytics not installed."""


class PupilDetector:
    """Landmark -> crop -> YOLO -> pupil centre, for one frame at a time."""

    def __init__(
        self,
        weights_path: Optional[Path] = None,
        conf: float = DEFAULT_CONF,
        landmarker: Optional[EyeLandmarker] = None,
        full_frame_fallback: bool = False,
    ):
        resolved, is_smoketest = resolve_weights(weights_path)
        # Falls back to DEFAULT_WEIGHTS purely so the error message names the
        # file people expect to be missing, rather than saying "None".
        self.weights_path = resolved if resolved is not None else DEFAULT_WEIGHTS
        self.is_smoketest = is_smoketest
        self.conf = conf
        self.landmarker = landmarker if landmarker is not None else EyeLandmarker()
        # Off by default: running the LPW-trained detector on a whole webcam
        # scene is out of distribution and mostly produces confident
        # nonsense. Useful only for debugging a landmarker problem.
        self.full_frame_fallback = full_frame_fallback
        self._model = None

    # ------------------------------------------------------------------
    # model loading

    def _ensure_model(self):
        """Load weights once, on first inference rather than at construction.

        Constructing a PupilDetector must stay cheap and side-effect free --
        the FastAPI app builds one at import time, and a missing .pt file
        (it's gitignored and lives in Drive) should fail at the first
        capture request with a clear message, not stop the server booting.
        """
        if self._model is not None:
            return self._model

        if not self.weights_path.exists():
            raise DetectorUnavailable(
                f"Pupil weights not found at {self.weights_path}.\n"
                "models/*.pt is gitignored. Any one of these fixes it:\n"
                "  - copy pupil_yolo_final.pt from Drive into models/  (the real detector)\n"
                f"  - set ${WEIGHTS_ENV_VAR} to weights kept elsewhere\n"
                "  - python scripts/make_smoketest_detector.py         "
                "(synthetic stand-in, NOT for measurements)"
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise DetectorUnavailable(
                "ultralytics is not installed -- `pip install -r requirements.txt`."
            ) from exc

        model = YOLO(str(self.weights_path))
        model.to("cpu")
        self._model = model
        return model

    @property
    def available(self) -> bool:
        """True if a real detection could actually run right now."""
        try:
            self._ensure_model()
        except DetectorUnavailable:
            return False
        return self.landmarker.available

    # ------------------------------------------------------------------
    # inference

    def detect(
        self,
        frame_bgr,
        frame_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> FrameResult:
        """One frame in, one FrameResult out. Never raises on a miss."""
        frame_id = frame_id or uuid.uuid4().hex[:12]
        timestamp = time.time() if timestamp is None else timestamp
        h, w = frame_bgr.shape[:2]

        try:
            regions, head_proxy = self.landmarker.eye_regions(frame_bgr)
        except LandmarkerUnavailable:
            raise
        except Exception as exc:                       # noqa: BLE001
            # A landmarker hiccup on one frame is a dropped sample, not a
            # dead session -- report it and let the caller count misses.
            return empty_result(frame_id, timestamp, w, h, f"landmarker_error: {exc}")

        if not regions:
            if not self.full_frame_fallback:
                return empty_result(frame_id, timestamp, w, h, "no_face_detected")
            regions = {"left": EyeRegion("left", 0, 0, w, h)}
            head_proxy = None

        result = FrameResult(
            frame_id=frame_id,
            timestamp=timestamp,
            frame_width=w,
            frame_height=h,
            face_found=True,
            eye_regions=regions,
            head_proxy=head_proxy,
        )

        for side, region in regions.items():
            crop = frame_bgr[region.y1:region.y2, region.x1:region.x2]
            if crop.size == 0:
                continue
            detection = self._detect_in_crop(crop, region, w, h)
            if detection is not None:
                result.pupils[side] = detection

        if not result.pupils:
            # Face found but no pupil -- almost always a blink. Named so the
            # calibration quality report can distinguish it from "no face",
            # which means the participant left the frame.
            result.note = "no_pupil_detected"

        return result

    def _detect_in_crop(
        self,
        crop_bgr,
        region: EyeRegion,
        frame_w: int,
        frame_h: int,
    ) -> Optional[PupilDetection]:
        model = self._ensure_model()
        preds = model.predict(crop_bgr, conf=self.conf, device="cpu", verbose=False)
        if not preds:
            return None

        boxes = preds[0].boxes
        if boxes is None or len(boxes) == 0:
            return None

        # One pupil per eye by definition -- take the most confident box and
        # discard the rest rather than averaging, which would drag the centre
        # towards whatever the false positive was.
        confs = boxes.conf.tolist()
        best = max(range(len(confs)), key=confs.__getitem__)
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[best].tolist())
        confidence = float(confs[best])

        cx_crop = (x1 + x2) / 2
        cy_crop = (y1 + y2) / 2

        return PupilDetection(
            side=region.side,
            x_px=region.x1 + cx_crop,
            y_px=region.y1 + cy_crop,
            x_frame=(region.x1 + cx_crop) / frame_w,
            y_frame=(region.y1 + cy_crop) / frame_h,
            x_eye=cx_crop / region.width if region.width else 0.0,
            y_eye=cy_crop / region.height if region.height else 0.0,
            confidence=confidence,
            bbox_px=(region.x1 + x1, region.y1 + y1, region.x1 + x2, region.y1 + y2),
            eye_region=region,
        )

    def close(self) -> None:
        self.landmarker.close()


__all__ = [
    "PupilDetector",
    "DetectorUnavailable",
    "DEFAULT_WEIGHTS",
    "SMOKETEST_WEIGHTS",
    "WEIGHTS_ENV_VAR",
    "DEFAULT_CONF",
    "resolve_weights",
]
