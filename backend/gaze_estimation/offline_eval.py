"""
offline_eval.py

Score every gaze-model variant on every saved session's ACCURACY-CHECK dots.

Each session has two kinds of data on disk:
  * calibration rows  -- backend/calibration, what a model is trained on
  * check frames      -- gaze_models/<id>.validation.jsonl, written by the
                         validate endpoint: frames captured at 5 NEW dots
                         shown after calibration

A variant is retrained from each session's calibration rows alone and
scored on that session's check frames, exactly as the live system would
see them. That is the honest test: leave-one-point-out on calibration rows
shares every confound of the sitting it came from (the row-order head-drift
problem was invisible to it), the check dots don't.

Variants:
  * auto           -- what ships: train_from_rows' own model selection
  * <set>/frames   -- one feature set, fitted on every calibration frame
  * <set>/medians  -- one feature set, fitted on one median row per dot.
                      Frame-level noise in the features shrinks a fitted
                      slope towards zero (errors-in-variables), which shows
                      up as compressed predictions; per-dot medians remove
                      most of that noise before fitting.

Run it through scripts/evaluate_gaze_sessions.py.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np

from calibration import get_store as get_calibration_store

from .features import FEATURE_SETS, InsufficientCalibrationData, build_dataset
from .model import GazeModel
from .training import (
    MODEL_DIR,
    load_rows_from_session,
    train_from_rows,
    validation_frames_path_for,
)

METHODS = ("frames", "medians")
DEFAULT_RIDGE = 1e-2
AUTO = "auto"


# ----------------------------------------------------------------------
# loading


def find_sessions(model_dir: Optional[Path] = None) -> List[str]:
    """Sessions that have saved check frames, oldest first."""
    directory = Path(model_dir) if model_dir else MODEL_DIR
    paths = sorted(directory.glob("*.validation.jsonl"), key=lambda p: p.stat().st_mtime)
    return [p.name[: -len(".validation.jsonl")] for p in paths]


def check_frame_to_row(frame: Dict) -> Dict:
    """One saved check frame -> the same flat row shape calibration exports,
    so FEATURE_SETS extractors read it unchanged."""
    row = {k: v for k, v in (frame.get("head_proxy") or {}).items()}
    for side, p in (frame.get("pupils") or {}).items():
        row[f"{side}_x_eye"], row[f"{side}_y_eye"] = p["x_eye"], p["y_eye"]
    return row


def load_check_dots(path: Path) -> List[Dict]:
    """Check frames grouped into dots: [{point_index, target_x, target_y, rows}].

    A dot that was redone appears twice in the file; only its last attempt
    is kept, matching what validation.record_point stores. Attempts are told
    apart by the per-request "attempt" id; files written before that field
    existed fall back to "a new attempt starts when point_index changes".
    """
    attempts: Dict[int, Dict] = {}
    last_key = None
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            frame = json.loads(line)
            idx = frame["point_index"]
            key = frame.get("attempt") or idx
            if key != last_key:
                attempts[idx] = {"point_index": idx, "target_x": frame["target_x"],
                                 "target_y": frame["target_y"], "rows": []}
                last_key = key
            attempts[idx]["rows"].append(check_frame_to_row(frame))
    return [attempts[k] for k in sorted(attempts)]


# ----------------------------------------------------------------------
# fitting


Predictor = Callable[[Dict], Optional[np.ndarray]]


def _predictor(model: GazeModel) -> Predictor:
    extract = FEATURE_SETS[model.feature_set]

    def predict(row: Dict) -> Optional[np.ndarray]:
        feats = extract(row)
        return None if feats is None else model.predict(np.asarray([feats], dtype=float))[0]

    return predict


def fit_variant(rows: Sequence[Dict], feature_set: str, method: str,
                ridge: float = DEFAULT_RIDGE) -> Optional[Predictor]:
    """A degree-1 model for one feature set and fitting method, or None when
    this session can't build that feature set (e.g. no eyelid columns)."""
    try:
        ds = build_dataset(rows, feature_set=feature_set)
    except InsufficientCalibrationData:
        return None
    X, y = ds.X, ds.y
    if method == "medians":
        groups = np.unique(ds.groups)
        X = np.asarray([np.median(ds.X[ds.groups == g], axis=0) for g in groups])
        y = np.asarray([ds.y[ds.groups == g][0] for g in groups])
    elif method != "frames":
        raise ValueError(f"method {method!r}; expected one of {METHODS}")
    model = GazeModel.fit(X, y, feature_set=feature_set, degree=1, ridge=ridge,
                          screen_width=ds.screen_width, screen_height=ds.screen_height)
    return _predictor(model)


def fit_auto(rows: Sequence[Dict]) -> Optional[Predictor]:
    try:
        return _predictor(train_from_rows(rows, persist=False).model)
    except InsufficientCalibrationData:
        return None


# ----------------------------------------------------------------------
# scoring


@dataclass
class DotResult:
    session_id: str
    point_index: int
    target_x: float
    target_y: float
    pred_x: float
    pred_y: float
    dx_px: float          # signed: + means predicted right of the target
    dy_px: float          # signed: + means predicted below the target
    error_px: float


def score_dots(predict: Predictor, dots: Iterable[Dict], session_id: str,
               screen_w: int, screen_h: int) -> List[DotResult]:
    """Median prediction per dot (as validation.score_point does) -> error."""
    out = []
    for dot in dots:
        preds = [p for p in (predict(r) for r in dot["rows"]) if p is not None]
        if len(preds) < 3:
            continue
        px, py = np.median(np.asarray(preds), axis=0)
        dx = (px - dot["target_x"]) * screen_w
        dy = (py - dot["target_y"]) * screen_h
        out.append(DotResult(session_id, dot["point_index"], dot["target_x"],
                             dot["target_y"], float(px), float(py), float(dx),
                             float(dy), float(np.hypot(dx, dy))))
    return out


def _gain(targets: np.ndarray, preds: np.ndarray) -> Optional[float]:
    """Slope of predicted on target. 1.0 = full range; below 1 = compressed."""
    if targets.size < 2 or np.ptp(targets) < 1e-9:
        return None
    return float(np.polyfit(targets, preds, 1)[0])


@dataclass
class VariantSummary:
    variant: str
    sessions: int
    dots: int
    median_px: float
    p90_px: float
    max_px: float
    mean_dx_px: float
    mean_dy_px: float
    gain_x: Optional[float]
    gain_y: Optional[float]
    per_session_median_px: Dict[str, float] = field(default_factory=dict)


def summarise(variant: str, dots: Sequence[DotResult]) -> Optional[VariantSummary]:
    if not dots:
        return None
    err = np.asarray([d.error_px for d in dots])
    by_session: Dict[str, List[float]] = defaultdict(list)
    for d in dots:
        by_session[d.session_id].append(d.error_px)
    return VariantSummary(
        variant=variant,
        sessions=len(by_session),
        dots=len(dots),
        median_px=float(np.median(err)),
        p90_px=float(np.percentile(err, 90)),
        max_px=float(err.max()),
        mean_dx_px=float(np.mean([d.dx_px for d in dots])),
        mean_dy_px=float(np.mean([d.dy_px for d in dots])),
        gain_x=_gain(np.asarray([d.target_x for d in dots]), np.asarray([d.pred_x for d in dots])),
        gain_y=_gain(np.asarray([d.target_y for d in dots]), np.asarray([d.pred_y for d in dots])),
        per_session_median_px={s: float(np.median(v)) for s, v in by_session.items()},
    )


# ----------------------------------------------------------------------
# the whole run


def variant_names(feature_sets: Optional[Sequence[str]] = None) -> List[str]:
    sets = feature_sets or list(FEATURE_SETS)
    return [AUTO] + [f"{fs}/{m}" for fs in sets for m in METHODS]


def evaluate(session_ids: Sequence[str], feature_sets: Optional[Sequence[str]] = None,
             ridge: float = DEFAULT_RIDGE, model_dir: Optional[Path] = None,
             ) -> Dict[str, List[DotResult]]:
    """Every variant on every session -> {variant: [DotResult, ...]}."""
    results: Dict[str, List[DotResult]] = {v: [] for v in variant_names(feature_sets)}
    store = get_calibration_store()
    for sid in session_ids:
        rows = load_rows_from_session(sid)
        session = store.get(sid)
        dots = load_check_dots(validation_frames_path_for(sid, model_dir))
        for variant in results:
            if variant == AUTO:
                predict = fit_auto(rows)
            else:
                fs, method = variant.split("/")
                predict = fit_variant(rows, fs, method, ridge)
            if predict is not None:
                results[variant] += score_dots(predict, dots, sid,
                                               session.screen_width, session.screen_height)
    return results


__all__ = [
    "AUTO",
    "METHODS",
    "DotResult",
    "VariantSummary",
    "check_frame_to_row",
    "evaluate",
    "find_sessions",
    "fit_auto",
    "fit_variant",
    "load_check_dots",
    "score_dots",
    "summarise",
    "variant_names",
]
