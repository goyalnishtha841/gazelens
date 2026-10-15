"""
features.py

The seam between backend/calibration's stored format and this module's
regression. Every assumption about that format lives here and nowhere else,
so if calibration's schema changes, this is the only file to update.

Input is a "training row" exactly as backend/calibration produces it -- see
backend/calibration/CONTRACT.md. Both sources work unchanged:

  * CalibrationSession.training_rows()  -> list[dict] with real floats/None
  * cal_<id>.csv via csv.DictReader     -> list[dict] with strings and ""

so nothing here needs a translation layer in front of it.

WHY x_eye AND NOT x_frame
-------------------------
`left_x_eye`/`left_y_eye` are the pupil centre WITHIN its own eye box.
`left_x_frame`/`left_y_frame` are the pupil centre in the whole webcam frame.

Only the first is invariant to where the head sits: if the participant slides
left in their chair without moving their eyes, x_frame changes and x_eye does
not. Regressing on x_frame would learn "head position -> screen position" and
fall apart the moment they shift. The frame columns are carried through as
diagnostics, not used as features.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# Column names from backend/calibration -- the contract, restated here so a
# mismatch shows up as an obvious KeyError in one place.
COL_TARGET = ("target_x", "target_y")
COL_LEFT_EYE = ("left_x_eye", "left_y_eye")
COL_RIGHT_EYE = ("right_x_eye", "right_y_eye")
COL_POINT_INDEX = "point_index"
COL_CONFIDENCE = "confidence"
COL_SCREEN = ("screen_width", "screen_height")

# backend/cv.FrameResult.head_proxy's keys (see cv/landmarks.py's
# EyeLandmarker._head_proxy) -- captured on every calibration row already
# (CalibrationSession.TRAINING_ROW_COLUMNS), but never read as a feature
# until _both_eyes_head below. Not a real 6-DoF pose, just cheap landmark
# ratios: interocular_norm tracks distance-from-camera, eye_mid_x/y tracks
# where the head is pointed, roll_norm tracks head tilt.
COL_HEAD = ("interocular_norm", "eye_mid_x", "eye_mid_y", "roll_norm")


def _num(row: Dict, key: str) -> Optional[float]:
    """Read one cell as a float, tolerating the CSV's empty-string Nones.

    calibration writes None for an eye it didn't find that frame; csv turns
    that into "". Both mean the same thing and must not become 0.0 -- a pupil
    at eye-box coordinate 0.0 is the far corner of the eye, which is a real
    and very different measurement.
    """
    value = row.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------
# feature sets


def _mean_eye(row: Dict) -> Optional[List[float]]:
    """Average of whichever eyes were found. 2 features.

    Averaging both eyes halves the detector's per-frame jitter, and the
    fallback to a single eye keeps blink-adjacent frames usable instead of
    throwing away the sample.
    """
    xs, ys = [], []
    for cx, cy in (COL_LEFT_EYE, COL_RIGHT_EYE):
        x, y = _num(row, cx), _num(row, cy)
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return [sum(xs) / len(xs), sum(ys) / len(ys)]


def _both_eyes(row: Dict) -> Optional[List[float]]:
    """Both eyes kept separate. 4 features.

    Requires both eyes present -- one-eyed rows are dropped for this feature
    set rather than mirrored, because inventing the missing eye's position
    would feed the regression a measurement nobody made. The two feature sets
    therefore see slightly different row counts; model selection compares
    them on held-out POINTS, which is unaffected by that.

    Worth having as a candidate: the eyes are not redundant. Their
    disparity carries depth/vergence information that a mean throws away.
    Whether that helps at 9-16 points is exactly what cross-validation is
    there to decide.
    """
    out: List[float] = []
    for cx, cy in (COL_LEFT_EYE, COL_RIGHT_EYE):
        x, y = _num(row, cx), _num(row, cy)
        if x is None or y is None:
            return None
        out.extend([x, y])
    return out


def _both_eyes_head(row: Dict) -> Optional[List[float]]:
    """Both eyes (4) + head proxy (4) = 8 features.

    Pure pupil position (both_eyes/mean_eye) assumes the head never moves
    between calibration and use -- exactly the failure mode _head_proxy's
    docstring in cv/landmarks.py names as "the failure that ruins a
    calibration". Adding it as a feature rather than a filter lets the
    regression learn how much a given head-position shift actually moves
    the true gaze point, instead of us hand-picking a drift threshold to
    reject samples by.

    Requires both eyes AND a head reading -- same reasoning as _both_eyes
    for why a partial row is dropped rather than guessed: model selection
    compares feature sets on held-out points, so losing rows to a stricter
    requirement only costs this candidate, not the session.
    """
    out = _both_eyes(row)
    if out is None:
        return None
    for col in COL_HEAD:
        v = _num(row, col)
        if v is None:
            return None
        out.append(v)
    return out


# --- landmark feature sets ---------------------------------------------
# Built from cv/landmarks.py _gaze_features rather than from a detected
# pupil. These are what make webcam gaze work at all: on the first real
# calibration the pupil-in-eye-box sets above had no correlation with the
# target, because the eye box follows the eyelids and the detector was out
# of domain. Iris-relative-to-eye-corners, MediaPipe's eyeLook* blendshapes
# and real head pose are the standard webcam-gaze inputs.

COL_IRIS = ("iris_h_l", "iris_v_l", "iris_h_r", "iris_v_r")
COL_BLEND = ("bs_h", "bs_v")
COL_POSE = ("head_yaw", "head_pitch", "head_tx", "head_ty")
COL_BLINK = "blink"


def _cols(row: Dict, cols: Sequence[str]) -> Optional[List[float]]:
    out: List[float] = []
    for c in cols:
        v = _num(row, c)
        if v is None:
            return None
        out.append(v)
    return out


def _iris_mean(row: Dict) -> Optional[List[float]]:
    """Iris position averaged over both eyes. 2 features.

    Both eyes are measured along the same image-left-to-right corner axis,
    so averaging is meaningful and halves landmark jitter. Falls back to
    one eye, like _mean_eye.
    """
    hs, vs = [], []
    for side in ("l", "r"):
        h, v = _num(row, f"iris_h_{side}"), _num(row, f"iris_v_{side}")
        if h is not None and v is not None:
            hs.append(h)
            vs.append(v)
    if not hs:
        return None
    return [sum(hs) / len(hs), sum(vs) / len(vs)]


def _iris_both(row: Dict) -> Optional[List[float]]:
    """Both eyes' iris positions kept separate. 4 features."""
    return _cols(row, COL_IRIS)


def _iris_blend(row: Dict) -> Optional[List[float]]:
    """Mean iris position + MediaPipe's own eyeLook estimate. 4 features."""
    iris, blend = _iris_mean(row), _cols(row, COL_BLEND)
    if iris is None or blend is None:
        return None
    return iris + blend


def _iris_pose(row: Dict) -> Optional[List[float]]:
    """iris_blend + head yaw/pitch/x/y. 8 features.

    Lets the regression learn that turning the head moves the gaze point
    even when the eyes stay put. Only offered when the head actually moved
    during calibration (see MIN_POSE_STD in build_dataset) -- otherwise
    there is nothing to learn that relationship from.
    """
    base, pose = _iris_blend(row), _cols(row, COL_POSE)
    if base is None or pose is None:
        return None
    return base + pose


def _lid_mean(row: Dict) -> Optional[List[float]]:
    """Eyelid opening averaged over whichever eyes were measured. 1 feature."""
    vals = [v for v in (_num(row, "lid_l"), _num(row, "lid_r")) if v is not None]
    return [sum(vals) / len(vals)] if vals else None


def _iris_lid(row: Dict) -> Optional[List[float]]:
    """iris_blend + eyelid opening. 5 features.

    Added for the vertical axis, which was the weak one on real data: iris
    vertical position varied between calibration rows by about as much as
    it jittered within one, while the lids track vertical gaze more
    visibly at webcam resolution.
    """
    base, lid = _iris_blend(row), _lid_mean(row)
    if base is None or lid is None:
        return None
    return base + lid


def _iris_lid_pose(row: Dict) -> Optional[List[float]]:
    """iris_pose + eyelid opening. 9 features (pose stays at columns 4-7,
    where build_dataset's head-movement check reads it)."""
    base, lid = _iris_pose(row), _lid_mean(row)
    if base is None or lid is None:
        return None
    return base + lid


FEATURE_SETS = {
    "mean_eye": _mean_eye,
    "both_eyes": _both_eyes,
    "both_eyes_head": _both_eyes_head,
    "iris": _iris_mean,
    "iris_both": _iris_both,
    "iris_blend": _iris_blend,
    "iris_pose": _iris_pose,
    "iris_lid": _iris_lid,
    "iris_lid_pose": _iris_lid_pose,
}

FEATURE_DIMS = {
    "mean_eye": 2, "both_eyes": 4, "both_eyes_head": 8,
    "iris": 2, "iris_both": 4, "iris_blend": 4, "iris_pose": 8,
    "iris_lid": 5, "iris_lid_pose": 9,
}

DEFAULT_FEATURE_SET = "mean_eye"


# ----------------------------------------------------------------------


@dataclass
class Dataset:
    """Rows turned into arrays, plus the grouping needed to validate honestly."""

    X: np.ndarray            # (n, d) pupil features
    y: np.ndarray            # (n, 2) target, normalised [0,1] screen coords
    groups: np.ndarray       # (n,) point_index -- THE grouping for CV
    confidence: np.ndarray   # (n,)
    feature_set: str
    screen_width: int
    screen_height: int
    dropped_rows: int        # rows this feature set couldn't use

    @property
    def n_samples(self) -> int:
        return int(self.X.shape[0])

    @property
    def n_points(self) -> int:
        """Distinct calibration points -- the EFFECTIVE sample size.

        Rows within one point differ only by detector noise: the participant
        was fixating a single target the whole time. Model capacity and
        cross-validation are both budgeted against this number, never
        against n_samples, which is ~15x larger and mostly duplicates.
        """
        return int(np.unique(self.groups).size)

    @property
    def unique_points(self) -> np.ndarray:
        return np.unique(self.groups)


class InsufficientCalibrationData(ValueError):
    """Not enough usable points/rows to fit anything trustworthy."""


# Below this, leave-one-point-out has too few folds to mean anything and the
# fit is unconstrained in at least one direction. calibration's own floor is
# 9 points; 4 is the absolute refusal line, not a recommendation.
MIN_POINTS_TO_FIT = 4

# A head_proxy column with almost no spread across the session is not a
# usable predictor -- it's a near-constant that z-score standardisation
# divides by its own tiny std, turning ordinary per-frame detector jitter
# into a huge standardised value the ridge fit can latch onto. A degree-1
# fit stays numerically well-posed on 16 points (max_degree_for allows it),
# but "well-posed" isn't "well-conditioned": a coefficient fit to explain
# noise in a near-constant column generalises to any input away from that
# exact narrow range as badly as fitting noise ever does. Requiring real
# spread here means both_eyes_head only gets offered as a candidate when
# the participant's head actually moved enough during calibration for the
# signal to mean something -- which is also exactly when it's worth having.
MIN_HEAD_FEATURE_STD = 0.01

# Same idea for iris_pose's real head pose: (yaw deg, pitch deg, tx cm,
# ty cm). Below these the pose columns are near-constant across the
# calibration and a coefficient on them would fit landmark jitter.
MIN_POSE_STD = (1.0, 1.0, 0.3, 0.3)

# Mean eyeBlink score above which a row is a (half-)closed eye: the iris
# landmark is then a guess on the lid, not a measurement.
BLINK_DROP_SCORE = 0.5


def build_dataset(
    rows: Sequence[Dict],
    feature_set: str = DEFAULT_FEATURE_SET,
    min_confidence: float = 0.0,
) -> Dataset:
    """Training rows -> arrays. Raises InsufficientCalibrationData if thin."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(
            f"unknown feature_set {feature_set!r}; expected one of {sorted(FEATURE_SETS)}"
        )
    extract = FEATURE_SETS[feature_set]

    X: List[List[float]] = []
    y: List[List[float]] = []
    groups: List[int] = []
    conf: List[float] = []
    dropped = 0

    screen_w, screen_h = 0, 0

    for row in rows:
        tx, ty = _num(row, COL_TARGET[0]), _num(row, COL_TARGET[1])
        if tx is None or ty is None:
            dropped += 1
            continue

        blink = _num(row, COL_BLINK)
        if blink is not None and blink > BLINK_DROP_SCORE:
            dropped += 1
            continue

        c = _num(row, COL_CONFIDENCE)
        c = 0.0 if c is None else c
        if c < min_confidence:
            dropped += 1
            continue

        feats = extract(row)
        if feats is None:
            dropped += 1
            continue

        idx = _num(row, COL_POINT_INDEX)
        if idx is None:
            dropped += 1
            continue

        X.append(feats)
        y.append([tx, ty])
        groups.append(int(idx))
        conf.append(c)

        sw, sh = _num(row, COL_SCREEN[0]), _num(row, COL_SCREEN[1])
        if sw and sh:
            screen_w, screen_h = int(sw), int(sh)

    if not X:
        raise InsufficientCalibrationData(
            f"no usable rows for feature_set {feature_set!r} "
            f"({dropped} rows dropped: missing target, missing pupil, or below "
            f"min_confidence={min_confidence})"
        )

    dataset = Dataset(
        X=np.asarray(X, dtype=float),
        y=np.asarray(y, dtype=float),
        groups=np.asarray(groups, dtype=int),
        confidence=np.asarray(conf, dtype=float),
        feature_set=feature_set,
        screen_width=screen_w or 1920,
        screen_height=screen_h or 1080,
        dropped_rows=dropped,
    )

    if dataset.n_points < MIN_POINTS_TO_FIT:
        raise InsufficientCalibrationData(
            f"only {dataset.n_points} calibration point(s) have usable data "
            f"(need at least {MIN_POINTS_TO_FIT}). This session cannot be "
            f"trained on -- recalibrate."
        )

    if feature_set == "both_eyes_head":
        # Checked against eye_mid_x/eye_mid_y only (columns 5, 6 of the 8) --
        # the direct "the head slid sideways/up-down" signal, and the one
        # _head_proxy's own docstring names as the point of this feature.
        # interocular_norm (col 4) is excluded: cv/landmarks.py derives it
        # from the SAME two landmarks as eye_mid but only from their
        # separation, which normal seated translation barely changes (real
        # depth change -- leaning toward/away from the camera -- is what
        # moves it, a rarer motion than sliding). roll_norm (col 7) is
        # excluded because a session can translate without tilting. Neither
        # absence should refuse a session where the head demonstrably moved.
        eye_mid_std = dataset.X[:, 5:7].std(axis=0)
        if np.any(eye_mid_std < MIN_HEAD_FEATURE_STD):
            raise InsufficientCalibrationData(
                f"head pose barely moved during calibration "
                f"(eye_mid std={eye_mid_std.round(4).tolist()}, "
                f"need >= {MIN_HEAD_FEATURE_STD} on every axis) -- both_eyes_head would be "
                f"fitting detector noise on a near-constant column, not a real signal"
            )
    if feature_set in ("iris_pose", "iris_lid_pose"):
        pose_std = dataset.X[:, 4:8].std(axis=0)
        if np.any(pose_std < np.asarray(MIN_POSE_STD)):
            raise InsufficientCalibrationData(
                f"head pose barely moved during calibration "
                f"(yaw/pitch/tx/ty std={pose_std.round(2).tolist()}, need >= "
                f"{list(MIN_POSE_STD)}) -- nothing to learn head compensation from"
            )
    return dataset


def features_from_pupils(
    left: Optional[Tuple[float, float]],
    right: Optional[Tuple[float, float]],
    feature_set: str,
    head_proxy: Optional[Dict[str, float]] = None,
) -> Optional[List[float]]:
    """Live-inference counterpart of the training extractors.

    Takes eye-normalised pupil centres straight from a cv.FrameResult
    (`detection.x_eye`, `detection.y_eye`) and applies EXACTLY the same
    feature construction used at training time. Deliberately routed through
    the same functions rather than reimplemented -- a train/serve feature
    mismatch is silent and would show up only as mysteriously bad gaze.

    head_proxy: the FrameResult's own head_proxy dict (same keys as
    COL_HEAD), passed straight through -- only "both_eyes_head" reads it,
    everything else ignores the extra row keys.
    """
    row: Dict[str, float] = {}
    if left is not None:
        row[COL_LEFT_EYE[0]], row[COL_LEFT_EYE[1]] = float(left[0]), float(left[1])
    if right is not None:
        row[COL_RIGHT_EYE[0]], row[COL_RIGHT_EYE[1]] = float(right[0]), float(right[1])
    if head_proxy:
        # Every landmark-derived key (head proxy + cv/landmarks.py
        # _gaze_features) -- the extractors pick what they need.
        for col, value in head_proxy.items():
            if value is not None:
                row[col] = float(value)
    return FEATURE_SETS[feature_set](row)


__all__ = [
    "Dataset",
    "FEATURE_SETS",
    "FEATURE_DIMS",
    "DEFAULT_FEATURE_SET",
    "MIN_POINTS_TO_FIT",
    "COL_POSE",
    "InsufficientCalibrationData",
    "build_dataset",
    "features_from_pupils",
]
