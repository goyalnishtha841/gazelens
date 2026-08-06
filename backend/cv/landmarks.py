"""
landmarks.py

MediaPipe FaceLandmarker wrapper. Its only job: given a frame, hand back two
eye crop boxes in full-frame pixels (plus a coarse head-position proxy).

Why landmark first instead of running YOLO on the whole frame: the detector
was trained on LPW, which is close-up eye imagery, not full webcam scenes.
Cropping to the eye before inference keeps the input distribution close to
what the model actually saw in training, and shrinks the search space so a
nostril or a dark shirt button can't win as "pupil".

WHICH MEDIAPIPE API
-------------------
This uses the **Tasks** API (`mediapipe.tasks.python.vision.FaceLandmarker`),
not the older `mp.solutions.face_mesh.FaceMesh`.

`mp.solutions` has been removed from MediaPipe -- it is absent from 0.10.35
and from 1.0.0, so there is no currently-installable version that still has
it. Pinning back to an old release to keep the legacy call would be chasing
a dead end.

The landmark topology is identical between the two (the same 478-point face
mesh, irises at 468-477), so every index constant below is unchanged from
the FaceMesh version. Only the plumbing differs.

Unlike FaceMesh, the Tasks API needs an explicit model bundle on disk:
`models/face_landmarker.task`. It is gitignored like `models/*.pt` --
fetch it with `python scripts/fetch_face_landmarker.py`.

Everything here is imported lazily, so this module -- and therefore the whole
calibration API -- stays importable on a machine that can't install
mediapipe. The test suites depend on that.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

from .schemas import EyeRegion

# models/ sits at the repo root: backend/cv/landmarks.py -> ../../models
DEFAULT_LANDMARKER_ASSET = (
    Path(__file__).resolve().parents[2] / "models" / "face_landmarker.task"
)

FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

# FaceMesh landmark indices bounding each eye. These are the eye-contour
# rings; the extremes of each set give a tight box around the visible eye.
# Camera-left (image-left) is the participant's right eye -- see schemas.py.
_LEFT_EYE_IDX = (
    33, 7, 163, 144, 145, 153, 154, 155, 133,
    246, 161, 160, 159, 158, 157, 173,
)
_RIGHT_EYE_IDX = (
    362, 382, 381, 380, 374, 373, 390, 249, 263,
    466, 388, 387, 386, 385, 384, 398,
)

# Extra margin around the landmark hull, as a fraction of box size. The
# contour hugs the eyelids; the pupil can sit right on that edge when the
# user looks to a screen corner, which is exactly the case calibration
# cares about most. Without padding those samples get clipped.
_PAD_X = 0.30
_PAD_Y = 0.55


class LandmarkerUnavailable(RuntimeError):
    """mediapipe/OpenCV missing, or the model bundle isn't on disk."""


class EyeLandmarker:
    """Frame -> eye crop boxes."""

    def __init__(
        self,
        model_asset_path: Optional[Path] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        video_mode: bool = False,
    ):
        self.model_asset_path = (
            Path(model_asset_path) if model_asset_path else DEFAULT_LANDMARKER_ASSET
        )
        self._min_det = min_detection_confidence
        self._min_track = min_tracking_confidence

        # IMAGE mode by default, deliberately.
        #
        # VIDEO mode carries tracking state between frames, which is faster
        # and steadier -- but it requires strictly increasing timestamps, and
        # the pipeline object is a process-wide singleton (cv.get_pipeline()).
        # Calibration posts frames in bursts over separate HTTP requests, and
        # two participants could share the process, so ordering is not
        # something this layer can guarantee. Stateless IMAGE mode costs some
        # CPU and removes a whole class of order-dependent bug from a study
        # that only runs once.
        #
        # webcam_demo.py opts into video_mode=True, where the stream really
        # is one continuous ordered source.
        self.video_mode = video_mode
        self._landmarker = None
        self._frame_index = 0     # monotonic clock for VIDEO mode

    # ------------------------------------------------------------------

    def _ensure_landmarker(self):
        if self._landmarker is not None:
            return self._landmarker
        try:
            import cv2  # noqa: F401 -- imported here so a missing OpenCV is
                        # reported as "can't landmark" rather than surfacing
                        # mid-frame as a generic per-frame error
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import (
                FaceLandmarker,
                FaceLandmarkerOptions,
                RunningMode,
            )
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise LandmarkerUnavailable(
                f"live landmarking needs mediapipe + opencv ({exc}). "
                "Both are only required for live capture, not for the "
                "calibration or gaze-estimation tests."
            ) from exc

        if not self.model_asset_path.exists():
            raise LandmarkerUnavailable(
                f"face landmarker bundle not found at {self.model_asset_path}. "
                "It is gitignored like models/*.pt -- fetch it with "
                "`python scripts/fetch_face_landmarker.py`."
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_asset_path)),
            running_mode=RunningMode.VIDEO if self.video_mode else RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=self._min_det,
            min_tracking_confidence=self._min_track,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        return self._landmarker

    @property
    def available(self) -> bool:
        try:
            self._ensure_landmarker()
            return True
        except LandmarkerUnavailable:
            return False

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        self._frame_index = 0

    def reset(self) -> None:
        """Drop tracking state. Call between participants in VIDEO mode."""
        if self.video_mode:
            self.close()

    # ------------------------------------------------------------------

    def eye_regions(self, frame_bgr) -> Tuple[Dict[str, EyeRegion], Optional[Dict[str, float]]]:
        """Returns ({side: EyeRegion}, head_proxy). Empty dict if no face."""
        landmarker = self._ensure_landmarker()   # raises LandmarkerUnavailable
                                                 # if the environment can't do
                                                 # this at all
        import cv2
        import mediapipe as mp

        h, w = frame_bgr.shape[:2]

        # MediaPipe wants RGB; OpenCV hands us BGR.
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB),
        )

        if self.video_mode:
            # Frame counter rather than wall-clock: the API requires strictly
            # increasing timestamps, and a counter guarantees that even if
            # frames arrive late or the clock steps backwards.
            self._frame_index += 1
            result = landmarker.detect_for_video(mp_image, self._frame_index * 33)
        else:
            result = landmarker.detect(mp_image)

        if not result.face_landmarks:
            return {}, None

        lm = result.face_landmarks[0]
        regions: Dict[str, EyeRegion] = {}
        for side, idx in (("left", _LEFT_EYE_IDX), ("right", _RIGHT_EYE_IDX)):
            region = self._box_from_indices(lm, idx, side, w, h)
            if region is not None and region.is_valid:
                regions[side] = region

        return regions, self._head_proxy(lm)

    @staticmethod
    def _box_from_indices(lm, indices, side: str, w: int, h: int) -> Optional[EyeRegion]:
        xs = [lm[i].x * w for i in indices]
        ys = [lm[i].y * h for i in indices]
        if not xs or not ys:
            return None

        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        pad_x = (x2 - x1) * _PAD_X
        pad_y = (y2 - y1) * _PAD_Y

        # Clamp to the frame, otherwise the crop silently comes back
        # a different size than the box says it is and eye_norm drifts.
        return EyeRegion(
            side=side,
            x1=int(max(0, round(x1 - pad_x))),
            y1=int(max(0, round(y1 - pad_y))),
            x2=int(min(w, round(x2 + pad_x))),
            y2=int(min(h, round(y2 + pad_y))),
        )

    @staticmethod
    def _head_proxy(lm) -> Dict[str, float]:
        """Cheap stand-in for head pose.

        Takes no frame size: every value below is derived from MediaPipe's
        already-normalised landmark coordinates and is deliberately kept in
        [0,1], so it stays comparable across camera resolutions. (It used to
        accept w/h and ignore them, which implied a dependence that was never
        there.)

        Interocular distance tracks how far the user is from the camera;
        the eye midpoint tracks where they've moved to. Together those catch
        the failure that ruins a calibration: the participant leaning in or
        sliding sideways between calibration and the live session, which
        shifts pupil position without any change in where they're looking.
        Full 6-DoF pose would be better -- this is enough to flag drift.
        """
        lx, ly = lm[33].x, lm[33].y          # outer corner, camera-left eye
        rx, ry = lm[263].x, lm[263].y        # outer corner, camera-right eye
        dx, dy = rx - lx, ry - ly
        return {
            "interocular_norm": float((dx ** 2 + dy ** 2) ** 0.5),
            "eye_mid_x": float((lx + rx) / 2),
            "eye_mid_y": float((ly + ry) / 2),
            "roll_norm": float(dy),          # vertical offset between corners
            "nose_x": float(lm[1].x),
            "nose_y": float(lm[1].y),
        }


__all__ = [
    "EyeLandmarker",
    "LandmarkerUnavailable",
    "DEFAULT_LANDMARKER_ASSET",
    "FACE_LANDMARKER_URL",
]
