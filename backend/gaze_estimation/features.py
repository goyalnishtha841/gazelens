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


FEATURE_SETS = {
    "mean_eye": _mean_eye,
    "both_eyes": _both_eyes,
}

FEATURE_DIMS = {"mean_eye": 2, "both_eyes": 4}

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
    return dataset


def features_from_pupils(
    left: Optional[Tuple[float, float]],
    right: Optional[Tuple[float, float]],
    feature_set: str,
) -> Optional[List[float]]:
    """Live-inference counterpart of the training extractors.

    Takes eye-normalised pupil centres straight from a cv.FrameResult
    (`detection.x_eye`, `detection.y_eye`) and applies EXACTLY the same
    feature construction used at training time. Deliberately routed through
    the same functions rather than reimplemented -- a train/serve feature
    mismatch is silent and would show up only as mysteriously bad gaze.
    """
    row: Dict[str, float] = {}
    if left is not None:
        row[COL_LEFT_EYE[0]], row[COL_LEFT_EYE[1]] = float(left[0]), float(left[1])
    if right is not None:
        row[COL_RIGHT_EYE[0]], row[COL_RIGHT_EYE[1]] = float(right[0]), float(right[1])
    return FEATURE_SETS[feature_set](row)


__all__ = [
    "Dataset",
    "FEATURE_SETS",
    "FEATURE_DIMS",
    "DEFAULT_FEATURE_SET",
    "MIN_POINTS_TO_FIT",
    "InsufficientCalibrationData",
    "build_dataset",
    "features_from_pupils",
]
