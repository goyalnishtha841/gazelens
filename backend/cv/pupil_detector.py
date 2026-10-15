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
WEIGHTS_ENV_VAR = "FIXATION_PUPIL_WEIGHTS"


def resolve_weights(explicit: Optional[Path] = None) -> tuple[Optional[Path], bool]:
    """Pick the weights to use. Returns (path, is_smoketest).

    Order: explicit argument, then $FIXATION_PUPIL_WEIGHTS, then the real
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

# Iris fusion: blend YOLO's pupil box with MediaPipe's iris-centre landmark
# (already computed for free during eye-cropping, see landmarks.py) rather
# than trusting YOLO alone.
#
# Why: in visible light (no IR illuminator) the pupil/iris contrast is low,
# especially with dark eyes -- exactly why the benchmark's recall collapses
# under glasses (0.278) and outdoor light (0.427). The iris/sclera boundary
# is much higher-contrast and far more stable to detect. gaze_estimation's
# calibration regression doesn't care which anatomical point it's fed, so
# swapping/blending the source is transparent to everything downstream.
#
# Disable via $FIXATION_PUPIL_FUSION=0 to reproduce the benchmark's
# YOLO-only numbers exactly -- the paper's reported precision/recall assume
# an unblended detector, and this flag keeps that reproducible without a
# second code path.
FUSION_ENV_VAR = "FIXATION_PUPIL_FUSION"

# Confidence value reported for an iris-only point. MediaPipe doesn't expose
# a per-landmark confidence, so this is a fixed nominal value rather than a
# measurement -- picked to sit comfortably above DEFAULT_CONF so an
# iris-only sample isn't mistaken for a marginal YOLO detection downstream.
IRIS_ONLY_CONFIDENCE = 0.5

# How far apart YOLO's box centre and the iris centre can be (in eye_norm
# units, i.e. fraction of the eye crop) before YOLO is treated as a false
# positive rather than blended in. A correct detection should have the two
# nearly concentric; anything this far off the eye box is more likely a
# reflection, eyelash, or glasses-frame edge than the actual pupil.
OUTLIER_EYE_NORM_DIST = 0.35


# Where the live pipeline's pupil point comes from:
#   "iris"  -- MediaPipe's iris landmark only. No YOLO, no weights needed.
#              The default for get_pipeline(): on a laptop webcam the eye is
#              ~30px wide, LPW-trained YOLO is out of domain there, and the
#              first real calibration with YOLO in the loop had no usable
#              gaze signal. Gaze itself is regressed from landmark features
#              (cv/landmarks.py _gaze_features), not from this point.
#   "fused" -- YOLO blended with iris (see fuse_iris below). Kept for the
#              detector-vs-iris ablation in the paper.
#   "yolo"  -- YOLO alone, as benchmarked.
# PupilDetector's own default stays "fused" (via fuse_iris) so the detector
# tests and benchmark scripts are unchanged; only get_pipeline() opts in.
PUPIL_SOURCE_ENV_VAR = "FIXATION_PUPIL_SOURCE"
PUPIL_SOURCES = ("iris", "fused", "yolo")
LIVE_DEFAULT_PUPIL_SOURCE = "iris"

# Above this mean eyeBlink score the iris landmark is a guess on a closed
# lid, so the eye is reported as not found.
BLINK_REJECT_SCORE = 0.5


def live_pupil_source() -> str:
    from os import environ

    val = (environ.get(PUPIL_SOURCE_ENV_VAR) or LIVE_DEFAULT_PUPIL_SOURCE).strip().lower()
    if val not in PUPIL_SOURCES:
        raise ValueError(f"${PUPIL_SOURCE_ENV_VAR}={val!r}; expected one of {PUPIL_SOURCES}")
    return val


def _fusion_enabled(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return explicit
    from os import environ

    val = environ.get(FUSION_ENV_VAR)
    if val is None:
        return True
    return val.strip().lower() not in ("0", "false", "no", "")


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
        fuse_iris: Optional[bool] = None,
        pupil_source: Optional[str] = None,
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
        # See FUSION_ENV_VAR above -- explicit arg wins, then the env var,
        # then on by default.
        self.fuse_iris = _fusion_enabled(fuse_iris)
        if pupil_source is None:
            pupil_source = "fused" if self.fuse_iris else "yolo"
        if pupil_source not in PUPIL_SOURCES:
            raise ValueError(f"pupil_source {pupil_source!r}; expected one of {PUPIL_SOURCES}")
        self.pupil_source = pupil_source
        # An explicit pupil_source wins over the fusion env var.
        self.fuse_iris = pupil_source == "fused"
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
        if self.pupil_source == "iris":
            return self.landmarker.available
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

        if self.pupil_source == "iris":
            blink = (head_proxy or {}).get("blink", 0.0)
            if blink > BLINK_REJECT_SCORE:
                result.note = "no_pupil_detected"
                return result
            for side, region in regions.items():
                if region.iris_x_px is None or region.iris_y_px is None:
                    continue
                result.pupils[side] = self._point_to_detection(
                    region, w, h, region.iris_x_px, region.iris_y_px,
                    confidence=round(1.0 - blink, 4), source="iris",
                )
            if not result.pupils:
                result.note = "no_pupil_detected"
            return result

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
        yolo = self._yolo_best_box(crop_bgr, region)

        iris_px = None
        if region.iris_x_px is not None and region.iris_y_px is not None:
            iris_px = (region.iris_x_px, region.iris_y_px)

        if not self.fuse_iris or iris_px is None:
            # No iris to fuse with (fusion off, or a landmarker -- real or
            # stubbed -- that doesn't provide one): YOLO alone, unchanged
            # from pre-fusion behaviour. This is also the path the benchmark
            # numbers were measured on.
            if yolo is None:
                return None
            x_px, y_px, confidence, bbox_px = yolo
            return self._point_to_detection(
                region, frame_w, frame_h, x_px, y_px, confidence,
                source="yolo", bbox_px=bbox_px,
            )

        if yolo is None:
            # YOLO missed this frame entirely -- exactly the case fusion
            # exists for (glasses/outdoor recall collapse). Iris carries it.
            return self._point_to_detection(
                region, frame_w, frame_h,
                iris_px[0], iris_px[1], IRIS_ONLY_CONFIDENCE, source="iris",
            )

        yolo_x, yolo_y, yolo_conf, yolo_bbox = yolo
        yolo_eye = self._eye_norm(yolo_x, yolo_y, region)
        iris_eye = self._eye_norm(iris_px[0], iris_px[1], region)
        dist = ((yolo_eye[0] - iris_eye[0]) ** 2 + (yolo_eye[1] - iris_eye[1]) ** 2) ** 0.5

        if dist > OUTLIER_EYE_NORM_DIST:
            # YOLO's box and the iris centre disagree by more than a real
            # pupil plausibly could -- trust iris over what's likely a false
            # positive (reflection, eyelash, glasses-frame edge).
            return self._point_to_detection(
                region, frame_w, frame_h,
                iris_px[0], iris_px[1], IRIS_ONLY_CONFIDENCE, source="iris",
            )

        # Confidence-weighted blend, in full-frame pixel space (the region
        # box maps affinely to both eye_norm and frame_norm, so blending
        # here and re-deriving the other two representations is equivalent
        # to blending in either of them). High YOLO confidence trusts YOLO;
        # a marginal detection leans on the more stable iris signal.
        w = yolo_conf
        blend_x = w * yolo_x + (1 - w) * iris_px[0]
        blend_y = w * yolo_y + (1 - w) * iris_px[1]
        return self._point_to_detection(
            region, frame_w, frame_h, blend_x, blend_y, yolo_conf,
            source="fused", bbox_px=yolo_bbox,
        )

    def _yolo_best_box(self, crop_bgr, region: EyeRegion):
        """Runs YOLO on one eye crop. Returns (x_px, y_px, confidence,
        bbox_px) in full-frame pixels for the most confident box, or None
        on a miss."""
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
        bbox_px = (region.x1 + x1, region.y1 + y1, region.x1 + x2, region.y1 + y2)
        return region.x1 + cx_crop, region.y1 + cy_crop, confidence, bbox_px

    @staticmethod
    def _eye_norm(x_px: float, y_px: float, region: EyeRegion) -> tuple[float, float]:
        x_eye = (x_px - region.x1) / region.width if region.width else 0.0
        y_eye = (y_px - region.y1) / region.height if region.height else 0.0
        return x_eye, y_eye

    @staticmethod
    def _point_to_detection(
        region: EyeRegion,
        frame_w: int,
        frame_h: int,
        x_px: float,
        y_px: float,
        confidence: float,
        source: str,
        bbox_px: Optional[tuple[float, float, float, float]] = None,
    ) -> PupilDetection:
        x_eye, y_eye = PupilDetector._eye_norm(x_px, y_px, region)
        # An iris-derived point has no YOLO box to report, so bbox_px
        # collapses to a single point rather than carrying a sentinel a
        # caller would have to special-case.
        return PupilDetection(
            side=region.side,
            x_px=x_px,
            y_px=y_px,
            x_frame=x_px / frame_w,
            y_frame=y_px / frame_h,
            x_eye=x_eye,
            y_eye=y_eye,
            confidence=confidence,
            bbox_px=bbox_px if bbox_px is not None else (x_px, y_px, x_px, y_px),
            eye_region=region,
            source=source,
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
    "FUSION_ENV_VAR",
    "PUPIL_SOURCE_ENV_VAR",
    "PUPIL_SOURCES",
    "live_pupil_source",
    "IRIS_ONLY_CONFIDENCE",
    "OUTLIER_EYE_NORM_DIST",
    "resolve_weights",
]
