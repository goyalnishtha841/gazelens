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

# Iris centre landmarks (only present because face_landmarker.task ships
# MediaPipe's attention-mesh refinement, which is always on in the Tasks
# API -- see the module docstring). Each eye gets 5 points: a centre plus 4
# boundary points; only the centre is used here.
#
# Verified empirically against a live frame, not just against MediaPipe's
# published FACEMESH_LEFT_IRIS/RIGHT_IRIS constants -- those name the sets
# by the mesh's own left/right, which turned out to be the opposite of this
# file's camera-side convention (region.iris_x_px landed outside its own
# eye box until this was swapped). 468 -> left, 473 -> right here.
_IRIS_CENTER_IDX = {"left": 468, "right": 473}

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
            # Both feed _gaze_features: blendshapes carry MediaPipe's own
            # eyeLook* gaze estimates, the matrix carries real head pose.
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        try:
            self._landmarker = FaceLandmarker.create_from_options(options)
        except (OSError, RuntimeError) as exc:
            # Native library failed to load (e.g. a container missing
            # libGLESv2). Unavailable, not a crash -- /health must still answer.
            raise LandmarkerUnavailable(f"mediapipe could not start: {exc}") from exc
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
                iris = lm[_IRIS_CENTER_IDX[side]]
                region.iris_x_px = iris.x * w
                region.iris_y_px = iris.y * h
                regions[side] = region

        proxy = self._head_proxy(lm)
        proxy.update(self._gaze_features(lm, w, h, result))
        return regions, proxy

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

    @staticmethod
    def _gaze_features(lm, w: int, h: int, result) -> Dict[str, float]:
        """Gaze features straight from the face mesh. Merged into head_proxy.

        This is the signal the live gaze model is trained on (see
        gaze_estimation/features.py, the "iris*" feature sets). It replaced
        pupil-in-eye-box as the primary feature after the first real
        calibration showed that one carried no gaze signal at webcam
        resolution (r = 0.04 against the target).

        * iris_h / iris_v -- iris centre relative to the two eye corners,
          in units of eye width. The corners barely move when the eye
          rotates, unlike the eyelids the old eye box was built from, which
          follow vertical gaze and cancel it out. Measured in pixels (not
          MediaPipe's normalised coords) so a non-square frame doesn't skew
          the angle. v is perpendicular to the corner line, so head roll
          drops out.
        * lid_l / lid_r -- eyelid opening (upper-to-lower lid distance) in
          eye widths. The lids follow vertical gaze -- they drop when you
          look down -- which is a usable vertical cue on a webcam, where
          the iris itself moves only a pixel or two vertically.
        * bs_h / bs_v -- MediaPipe's eyeLook* blendshapes, combined across
          both eyes so the in/out naming convention cancels.
        * head_yaw / head_pitch / head_roll (degrees) and head_tx/ty/tz
          (cm) -- real 6-DoF pose from the facial transformation matrix, so
          the regression can separate "eyes moved" from "head moved".

        Any group whose model output is missing is simply absent from the
        dict; the feature sets that need it then drop the frame.
        """
        import math

        out: Dict[str, float] = {}

        def px(i):
            return lm[i].x * w, lm[i].y * h

        # (corner on image-left, corner on image-right, iris centre,
        #  upper lid, lower lid)
        eyes = {"l": (33, 133, 468, 159, 145), "r": (362, 263, 473, 386, 374)}
        for tag, (ia, ib, ii, iu, il) in eyes.items():
            (ax, ay), (bx, by), (cx, cy) = px(ia), px(ib), px(ii)
            ux, uy = bx - ax, by - ay
            width = math.hypot(ux, uy)
            if width < 1e-6:
                continue
            ux, uy = ux / width, uy / width
            dx, dy = cx - ax, cy - ay
            out[f"iris_h_{tag}"] = (dx * ux + dy * uy) / width
            out[f"iris_v_{tag}"] = (dy * ux - dx * uy) / width
            (ux2, uy2), (lx2, ly2) = px(iu), px(il)
            out[f"lid_{tag}"] = math.hypot(lx2 - ux2, ly2 - uy2) / width

        blendshapes = getattr(result, "face_blendshapes", None)
        if blendshapes:
            s = {c.category_name: float(c.score) for c in blendshapes[0]}
            keys = ("eyeLookInLeft", "eyeLookOutLeft", "eyeLookInRight",
                    "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
                    "eyeLookDownLeft", "eyeLookDownRight")
            if all(k in s for k in keys):
                # Looking to one side turns one eye "in" and the other "out",
                # so this difference has a consistent sign whichever eye
                # MediaPipe calls Left.
                out["bs_h"] = ((s["eyeLookOutLeft"] - s["eyeLookInLeft"])
                               - (s["eyeLookOutRight"] - s["eyeLookInRight"])) / 2
                out["bs_v"] = ((s["eyeLookUpLeft"] + s["eyeLookUpRight"])
                               - (s["eyeLookDownLeft"] + s["eyeLookDownRight"])) / 2
            if "eyeBlinkLeft" in s and "eyeBlinkRight" in s:
                out["blink"] = (s["eyeBlinkLeft"] + s["eyeBlinkRight"]) / 2

        matrices = getattr(result, "facial_transformation_matrixes", None)
        if matrices is not None and len(matrices) > 0:
            m = matrices[0]
            r20, r21, r22 = float(m[2][0]), float(m[2][1]), float(m[2][2])
            out["head_pitch"] = math.degrees(math.atan2(r21, r22))
            out["head_yaw"] = math.degrees(math.atan2(-r20, math.hypot(r21, r22)))
            out["head_roll"] = math.degrees(math.atan2(float(m[1][0]), float(m[0][0])))
            out["head_tx"] = float(m[0][3])
            out["head_ty"] = float(m[1][3])
            out["head_tz"] = float(m[2][3])

        return out


__all__ = [
    "EyeLandmarker",
    "LandmarkerUnavailable",
    "DEFAULT_LANDMARKER_ASSET",
    "FACE_LANDMARKER_URL",
]
