"""
test_cv.py

Run with: python3 test_cv.py   (from inside backend/cv)

Covers the parts of the CV layer that don't need a camera, weights, or
mediapipe: the coordinate conventions, the failure paths, and the stub
pipeline that backend/calibration's tests depend on.

Anything requiring the real detector is skipped with a printed note rather
than failed -- models/*.pt is gitignored, so a clean clone genuinely cannot
run it, and a red suite on a clean clone teaches everyone to ignore the suite.
"""

import sys
from pathlib import Path

# backend/ on the path so this runs directly (`python3 test_cv.py`) as well
# as under an import of the cv package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from cv.schemas import EyeRegion, FrameResult, empty_result
from cv.frame_source import FrameDecodeError, decode_base64_frame
from cv.pipeline import PupilPipeline, get_pipeline, set_pipeline
from cv.pupil_detector import (
    DetectorUnavailable,
    IRIS_ONLY_CONFIDENCE,
    PupilDetector,
    resolve_weights,
)
from cv.testing import StubPipeline, synthetic_eye_frame, synthetic_frame

passed = 0
failed = 0
skipped = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


def skip(label, why):
    global skipped
    print(f"  SKIP  {label} ({why})")
    skipped += 1


def _has(module_name):
    """Is an optional dependency importable? Used to widen coverage, never
    to weaken it -- nothing here is skipped because a check is inconvenient."""
    import importlib.util

    return importlib.util.find_spec(module_name) is not None


print("schemas -- EyeRegion geometry")
region = EyeRegion("left", 100, 200, 160, 230)
check("width", region.width == 60)
check("height", region.height == 30)
check("valid box is valid", region.is_valid)
check("inverted box is not valid", not EyeRegion("left", 160, 200, 100, 230).is_valid)

print("\nschemas -- FrameResult accessors")
empty = empty_result("f1", 1.0, 640, 480, "no_face_detected")
check("empty result has no pupils", not empty.has_any_pupil)
check("empty result face_found is False", empty.face_found is False)
check("empty result mean_confidence is 0", empty.mean_confidence == 0.0)
check("note preserved", empty.note == "no_face_detected")
check("empty result is JSON-shaped", isinstance(empty.to_dict()["pupils"], dict))

stub = StubPipeline()
stub.aim_at(0.5, 0.5)
centre = stub.process_frame(None)
check("both pupils found", centre.has_both_pupils)
check("left/right accessors work", centre.left is not None and centre.right is not None)
check("mean_confidence averages", abs(centre.mean_confidence - 0.91) < 1e-6)

print("\ncoordinate conventions -- eye_norm is the head-invariant one")
check("centre target puts pupil mid-eye", abs(centre.left.x_eye - 0.5) < 1e-6)

stub.aim_at(0.9, 0.1)
corner = stub.process_frame(None)
check("looking right moves pupil right in eye", corner.left.x_eye > centre.left.x_eye)
check("looking up moves pupil up in eye", corner.left.y_eye < centre.left.y_eye)
check("eye_norm stays in [0,1]", 0.0 <= corner.left.x_eye <= 1.0)
check("frame_norm stays in [0,1]", 0.0 <= corner.left.x_frame <= 1.0)
check("pixel coords land inside the frame",
      0 <= corner.left.x_px <= corner.frame_width)

print("\nframe decoding -- bad input must not raise past the pipeline")
try:
    decode_base64_frame("not base64 at all !!!")
    check("garbage base64 raises FrameDecodeError", False)
except FrameDecodeError:
    check("garbage base64 raises FrameDecodeError", True)
except ImportError:
    skip("garbage base64 raises FrameDecodeError", "opencv not installed")

try:
    decode_base64_frame("")
    check("empty payload raises FrameDecodeError", False)
except FrameDecodeError:
    check("empty payload raises FrameDecodeError", True)

print("\npipeline -- a miss is a FrameResult, never an exception")
blinker = StubPipeline(fail_next=1)
missed = blinker.process_frame(None)
check("blink returns a result", isinstance(missed, FrameResult))
check("blink has no pupils", not missed.has_any_pupil)
check("blink is labelled, not silent", missed.note == "no_pupil_detected")
check("next frame recovers", blinker.process_frame(None).has_both_pupils)
check("empty encoded payload is a noted miss, not a raise",
      "decode_error" in StubPipeline().process_encoded("").note)

print("\npipeline -- swappable singleton (how calibration gets tested)")
set_pipeline(stub)
check("get_pipeline returns the injected stub", get_pipeline() is stub)
set_pipeline(None)
check("reset rebuilds a real pipeline", isinstance(get_pipeline(), PupilPipeline))
set_pipeline(None)

print("\nsynthetic frames")
frame = synthetic_frame(320, 240)
check("synthetic frame has the requested shape", frame.shape == (240, 320, 3))
check("synthetic frame is uint8 BGR", frame.dtype == np.uint8)

print("\ndetector internals -- crop -> frame -> eye_norm mapping must be exact")
# The arithmetic that turns a box inside an eye crop back into full-frame and
# eye-normalised coordinates. Everything downstream (calibration targets, the
# gaze regression) is built on it being right, and it is the one part of the
# detector that a missing .pt file would otherwise leave completely untested.
#
# Stubs the landmarker and the YOLO model, so this runs anywhere. The box
# container is exercised with numpy and, when torch is installed, with real
# torch tensors too -- ultralytics returns the latter, and the .tolist()
# handling has to cope with both.


class _StubLandmarker:
    """Fixed eye boxes, so the mapping can be checked against known numbers."""

    def __init__(self):
        self.regions = {
            "left": EyeRegion("left", 100, 200, 160, 230),    # 60 x 30
            "right": EyeRegion("right", 300, 200, 380, 240),  # 80 x 40
        }

    available = True

    def eye_regions(self, frame):
        return self.regions, {"interocular_norm": 0.3}

    def close(self):
        pass


def _boxes_container(array_lib):
    conf = array_lib.asarray([0.30, 0.91])
    xyxy = array_lib.asarray([[1.0, 1.0, 3.0, 3.0], [10.0, 4.0, 18.0, 10.0]])

    class _Boxes:
        def __init__(self):
            self.conf = conf
            self.xyxy = xyxy

        def __len__(self):
            return 2

    class _Pred:
        boxes = _Boxes()

    class _Model:
        def predict(self, crop, **kw):
            return [_Pred()]

        def to(self, device):
            return self

    return _Model()


for lib_name, lib in [("numpy", np)] + (
    [("torch", __import__("torch"))] if _has("torch") else []
):
    detector = PupilDetector(weights_path="unused.pt", landmarker=_StubLandmarker())
    detector._model = _boxes_container(lib)          # skip real weight loading
    res = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))

    ok = True
    for side, pupil in res.pupils.items():
        region = res.eye_regions[side]
        # best box centre is (14, 7) within the crop
        ok &= abs(pupil.confidence - 0.91) < 1e-6          # most confident wins
        ok &= pupil.x_px == region.x1 + 14.0
        ok &= pupil.y_px == region.y1 + 7.0
        ok &= abs(pupil.x_eye - 14.0 / region.width) < 1e-9
        ok &= abs(pupil.y_eye - 7.0 / region.height) < 1e-9
        ok &= abs(pupil.x_frame - pupil.x_px / res.frame_width) < 1e-9
        ok &= region.x1 <= pupil.x_px <= region.x2

    check(f"both eyes mapped ({lib_name} boxes)", len(res.pupils) == 2)
    check(f"most-confident box wins and maps exactly ({lib_name} boxes)", bool(ok))
    check(f"eye_norm differs per eye box size ({lib_name} boxes)",
          res.pupils["left"].y_eye != res.pupils["right"].y_eye)

print("\npupil detector -- iris fusion")
# Fully synthetic: a controllable iris centre plus a controllable YOLO box,
# so all three fusion branches (blend / iris-fallback / outlier-reject) and
# the fuse_iris=False escape hatch can be checked against known numbers,
# with no dependence on real weights or a real face.


class _IrisLandmarker:
    """One eye region (60x30 at (100,200), matching _StubLandmarker above)
    with a caller-supplied iris centre."""

    available = True

    def __init__(self, iris_x_px, iris_y_px):
        region = EyeRegion("left", 100, 200, 160, 230)
        region.iris_x_px = iris_x_px
        region.iris_y_px = iris_y_px
        self.regions = {"left": region}

    def eye_regions(self, frame):
        return self.regions, {"interocular_norm": 0.3}

    def close(self):
        pass


def _single_box_model(box_xyxy, conf):
    """A stub YOLO model reporting exactly one in-crop box, or a miss."""

    class _Boxes:
        def __init__(self):
            self._n = 0 if box_xyxy is None else 1
            self.conf = np.asarray([] if box_xyxy is None else [conf])
            self.xyxy = np.asarray([] if box_xyxy is None else [box_xyxy]).reshape(self._n, 4)

        def __len__(self):
            return self._n

    class _Pred:
        boxes = _Boxes()

    class _Model:
        def predict(self, crop, **kw):
            return [_Pred()]

        def to(self, device):
            return self

    return _Model()


# Iris fixed at eye_norm (0.5, 0.5) -> full-frame (130, 215) in the 60x30 box.
iris_x_px, iris_y_px = 130.0, 215.0

# YOLO agrees closely (eye_norm (0.6, 0.6), dist ~0.14 < the 0.35 outlier
# threshold) -- both signals blend, weighted by YOLO's own confidence.
agree = PupilDetector(
    weights_path="unused.pt", landmarker=_IrisLandmarker(iris_x_px, iris_y_px)
)
agree._model = _single_box_model((34.0, 16.0, 38.0, 20.0), 0.8)  # centre (36, 18) in-crop
res = agree.detect(np.zeros((480, 640, 3), dtype=np.uint8))
pupil = res.pupils["left"]
check("agreeing YOLO+iris blends", pupil.source == "fused")
expected_x = 0.8 * 136.0 + 0.2 * iris_x_px
expected_y = 0.8 * 218.0 + 0.2 * iris_y_px
check("blend is weighted by YOLO's confidence", abs(pupil.x_px - expected_x) < 1e-6
      and abs(pupil.y_px - expected_y) < 1e-6)

# YOLO misses the frame entirely -- iris carries the point on its own.
miss = PupilDetector(
    weights_path="unused.pt", landmarker=_IrisLandmarker(iris_x_px, iris_y_px)
)
miss._model = _single_box_model(None, 0.0)
res = miss.detect(np.zeros((480, 640, 3), dtype=np.uint8))
pupil = res.pupils["left"]
check("YOLO miss falls back to iris", pupil.source == "iris")
check("iris-only point is exactly the iris centre",
      pupil.x_px == iris_x_px and pupil.y_px == iris_y_px)
check("iris-only confidence is the fixed nominal value",
      pupil.confidence == IRIS_ONLY_CONFIDENCE)

# YOLO fires, but nowhere near the iris (eye_norm ~(0.02, 0.03), dist ~0.67)
# -- treated as a false positive and rejected in favour of iris.
outlier = PupilDetector(
    weights_path="unused.pt", landmarker=_IrisLandmarker(iris_x_px, iris_y_px)
)
outlier._model = _single_box_model((0.0, 0.0, 2.0, 2.0), 0.9)
res = outlier.detect(np.zeros((480, 640, 3), dtype=np.uint8))
pupil = res.pupils["left"]
check("YOLO box far from iris is rejected as an outlier", pupil.source == "iris")

# fuse_iris=False must reproduce pre-fusion behaviour exactly, even when
# iris is available and disagrees -- this is the benchmark-reproducibility
# escape hatch, so it has to actually ignore iris, not just weight it low.
disabled = PupilDetector(
    weights_path="unused.pt",
    landmarker=_IrisLandmarker(iris_x_px, iris_y_px),
    fuse_iris=False,
)
disabled._model = _single_box_model((0.0, 0.0, 2.0, 2.0), 0.9)
res = disabled.detect(np.zeros((480, 640, 3), dtype=np.uint8))
pupil = res.pupils["left"]
check("fuse_iris=False keeps pure YOLO even off-iris", pupil.source == "yolo")
check("fuse_iris=False reports YOLO's own confidence", pupil.confidence == 0.9)
check("fuse_iris=False keeps YOLO's real box, not a collapsed point",
      pupil.bbox_px[2] - pupil.bbox_px[0] > 0)

print("\nreal detector -- construction must stay cheap and lazy")
detector = PupilDetector(weights_path="does_not_exist.pt")
check("missing weights does not raise at construction", detector is not None)
check("missing weights reports unavailable", detector.available is False)

# Weights load lazily, on the first crop that needs them -- so a frame with
# no face never touches them. Force a face with the stub landmarker,
# otherwise this asserts nothing on a machine where landmarking works.
no_face = PupilDetector(weights_path="does_not_exist.pt", landmarker=_StubLandmarker())
try:
    no_face.detect(np.zeros((480, 640, 3), dtype=np.uint8))
    check("missing weights raises DetectorUnavailable once a crop needs them", False)
except DetectorUnavailable:
    check("missing weights raises DetectorUnavailable once a crop needs them", True)

blank = PupilDetector(weights_path="does_not_exist.pt")
if blank.landmarker.available:
    result = blank.detect(synthetic_frame(320, 240))
    check("a frame with no face never touches the weights",
          result.note == "no_face_detected" and not result.has_any_pupil)
else:
    skip("a frame with no face never touches the weights",
         "landmarking unavailable in this environment")

print("\nreal detector -- end to end with whatever weights exist")
# Runs against the real LPW detector when it's present, and against the
# synthetic stand-in from scripts/make_smoketest_detector.py otherwise, so
# this path is exercised on machines without Drive access instead of being
# skipped everywhere. What's asserted is the PLUMBING -- landmark, crop,
# infer, map back into frame coordinates -- never detection accuracy, which
# would be meaningless with the stand-in.
weights, is_smoketest = resolve_weights()

if weights is None:
    skip("real detector end-to-end",
         "no weights: add pupil_yolo_final.pt or run scripts/make_smoketest_detector.py")
else:
    real = PupilDetector()
    if not real.available:
        skip("real detector end-to-end", "mediapipe/ultralytics not installed")
    else:
        label = "smoke-test stand-in" if is_smoketest else "real LPW detector"
        print(f"        using {weights.name} ({label})")
        check("detector reports whether it's running on stand-in weights",
              real.is_smoketest == is_smoketest)

        result = real.detect(synthetic_frame())
        check("real inference on a face-less frame returns a FrameResult",
              isinstance(result, FrameResult))
        check("...and reports no face rather than inventing pupils",
              result.note == "no_face_detected" and not result.has_any_pupil)

        # A real eye crop through the real model: bypass the landmarker with
        # fixed boxes so this needs no face image, then assert every
        # coordinate the rest of the pipeline depends on.
        eye = synthetic_eye_frame()
        boxed = PupilDetector(landmarker=_StubLandmarker())
        eye_result = boxed.detect(eye)
        check("real model runs on eye crops without raising",
              isinstance(eye_result, FrameResult) and eye_result.face_found)
        for side, pupil in eye_result.pupils.items():
            region = eye_result.eye_regions[side]
            check(f"{side}: pupil maps back inside its own eye box",
                  region.x1 <= pupil.x_px <= region.x2
                  and region.y1 <= pupil.y_px <= region.y2)
            check(f"{side}: eye_norm in range", 0.0 <= pupil.x_eye <= 1.0)
            check(f"{side}: frame_norm consistent with pixels",
                  abs(pupil.x_frame - pupil.x_px / eye_result.frame_width) < 1e-9)
        if is_smoketest:
            # Only meaningful for the stand-in, which was trained on exactly
            # this kind of drawn eye. The real detector was trained on LPW
            # photographs and is not expected to fire on a synthetic drawing.
            check("stand-in actually detects the synthetic pupils it was "
                  "trained on", eye_result.has_any_pupil)

print("\npupil detector -- iris-only source (the live default)")
# pupil_source="iris" must never touch YOLO: no weights, no model.
iris_only = PupilDetector(
    weights_path="unused.pt", landmarker=_IrisLandmarker(iris_x_px, iris_y_px),
    pupil_source="iris",
)
check("iris source is available without any weights", iris_only.available)
res = iris_only.detect(np.zeros((480, 640, 3), dtype=np.uint8))
check("iris source returns the iris centre", res.pupils["left"].x_px == iris_x_px
      and res.pupils["left"].y_px == iris_y_px and res.pupils["left"].source == "iris")
check("iris source never loaded a model", iris_only._model is None)


class _BlinkLandmarker(_IrisLandmarker):
    def eye_regions(self, frame):
        return self.regions, {"blink": 0.9}


blinking = PupilDetector(
    weights_path="unused.pt", landmarker=_BlinkLandmarker(iris_x_px, iris_y_px),
    pupil_source="iris",
)
res = blinking.detect(np.zeros((480, 640, 3), dtype=np.uint8))
check("a blinking frame reports no pupil", not res.has_any_pupil
      and res.note == "no_pupil_detected")
check("explicit pupil_source='yolo' turns fusion off",
      not PupilDetector(weights_path="unused.pt", landmarker=_IrisLandmarker(1, 1),
                        pupil_source="yolo").fuse_iris)


print("\nlandmarks -- gaze features from the face mesh")
from cv.landmarks import EyeLandmarker   # noqa: E402


class _P:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Cat:
    def __init__(self, name, score):
        self.category_name, self.score = name, score


def _mesh(iris_l, iris_r):
    lm = [_P(0.5, 0.5) for _ in range(478)]
    # 640x480 frame; each eye 64px wide, level
    lm[33], lm[133], lm[468] = _P(0.20, 0.40), _P(0.30, 0.40), _P(*iris_l)
    lm[362], lm[263], lm[473] = _P(0.60, 0.40), _P(0.70, 0.40), _P(*iris_r)
    return lm


class _Result:
    def __init__(self, blend=None, matrix=None):
        self.face_blendshapes = [blend] if blend is not None else []
        self.facial_transformation_matrixes = [matrix] if matrix is not None else []


feats = EyeLandmarker._gaze_features(_mesh((0.25, 0.40), (0.65, 0.40)), 640, 480, _Result())
check("iris at the corner midpoint -> iris_h 0.5",
      abs(feats["iris_h_l"] - 0.5) < 1e-9 and abs(feats["iris_h_r"] - 0.5) < 1e-9)
check("iris on the corner line -> iris_v 0", abs(feats["iris_v_l"]) < 1e-9)
feats = EyeLandmarker._gaze_features(_mesh((0.275, 0.41), (0.675, 0.41)), 640, 480, _Result())
check("iris moved right -> iris_h grows", feats["iris_h_l"] > 0.5)
check("iris moved down -> iris_v positive, in eye widths",
      abs(feats["iris_v_l"] - (0.01 * 480) / (0.10 * 640)) < 1e-9)
lidded = _mesh((0.25, 0.40), (0.65, 0.40))
lidded[159], lidded[145] = _P(0.25, 0.39), _P(0.25, 0.42)   # 14.4px apart, eye 64px wide
check("eyelid opening in eye widths",
      abs(EyeLandmarker._gaze_features(lidded, 640, 480, _Result())["lid_l"]
          - (0.03 * 480) / (0.10 * 640)) < 1e-9)
check("no blendshapes/matrix -> those keys absent, not zero",
      "bs_h" not in feats and "head_yaw" not in feats)

blend = [_Cat(n, 0.0) for n in ("eyeLookInLeft", "eyeLookInRight", "eyeLookUpLeft",
                                 "eyeLookUpRight", "eyeLookDownLeft", "eyeLookDownRight",
                                 "eyeBlinkLeft", "eyeBlinkRight")]
blend += [_Cat("eyeLookOutLeft", 0.6), _Cat("eyeLookOutRight", 0.0)]
yaw = np.radians(10.0)
matrix = np.eye(4)
matrix[:3, :3] = [[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]]
matrix[2, 3] = -50.0
feats = EyeLandmarker._gaze_features(_mesh((0.25, 0.40), (0.65, 0.40)), 640, 480,
                                     _Result(blend, matrix))
check("one eye looking out -> bs_h 0.3", abs(feats["bs_h"] - 0.3) < 1e-9)
check("head yaw read from the transformation matrix",
      abs(feats["head_yaw"] - 10.0) < 1e-6 and abs(feats["head_pitch"]) < 1e-6)
check("head distance read from the matrix", feats["head_tz"] == -50.0)

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed, {skipped} skipped\n{'=' * 40}")

if failed:
    raise SystemExit(1)
