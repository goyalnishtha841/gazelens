"""
evaluation.py

Honest accuracy, and the model selection built on top of it.

THE ONE RULE: HOLD OUT POINTS, NOT ROWS
---------------------------------------
Calibration records ~15 frames per target. Those frames differ only by
detector noise -- the participant fixated one target throughout. A random
80/20 split over ROWS therefore puts near-identical rows in both train and
test: the model has effectively already seen every test row, and the
reported error comes out several times better than the truth.

So every split here is over `groups` (point_index). Leave-one-point-out asks
the only question that matters: given the OTHER calibration points, how far
off is this one? That is the same question the live session asks at every
screen position that wasn't a calibration target.

The README already carries an "optimistic, train and val point at the same
folder" caveat on the detector benchmark. One such number in a paper is a
known limitation; two starts to look like a pattern.

METRICS
-------
Primary: median Euclidean pixel error over held-out points. Median rather
than mean because a single bad calibration point -- a blink, a glance away
at the wrong moment -- otherwise dominates and makes an adequate session
look broken.

Degrees of visual angle are reported ONLY when the caller supplies viewing
distance and physical screen size. backend/calibration stores screen size in
PIXELS only, so degrees are not derivable from a stored session alone. Rather
than assume a viewing distance and quietly publish a number that depends on
it, the field is omitted when the inputs are absent. See CONTRACT.md.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .features import Dataset
from .model import DEFAULT_RIDGE, GazeModel, max_degree_for, n_terms

# Candidate grid for model selection. Small on purpose: with 9-16 folds,
# an exhaustive search over dozens of candidates would itself start
# overfitting the cross-validation.
CANDIDATE_RIDGES = (1e-6, 1e-4, 1e-2)


def _percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if values.size else 0.0


def error_metrics(
    pred_norm: np.ndarray,
    true_norm: np.ndarray,
    screen_width: int,
    screen_height: int,
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
) -> Dict:
    """Predicted vs true normalised coords -> a full error report."""
    pred = np.atleast_2d(np.asarray(pred_norm, dtype=float))
    true = np.atleast_2d(np.asarray(true_norm, dtype=float))

    dx_px = (pred[:, 0] - true[:, 0]) * screen_width
    dy_px = (pred[:, 1] - true[:, 1]) * screen_height
    euclid = np.sqrt(dx_px ** 2 + dy_px ** 2)

    diagonal_px = math.hypot(screen_width, screen_height)

    metrics: Dict = {
        "n": int(euclid.size),
        "median_error_px": float(np.median(euclid)) if euclid.size else 0.0,
        "mean_error_px": float(np.mean(euclid)) if euclid.size else 0.0,
        "p95_error_px": _percentile(euclid, 95),
        "max_error_px": float(np.max(euclid)) if euclid.size else 0.0,
        "mean_abs_x_px": float(np.mean(np.abs(dx_px))) if euclid.size else 0.0,
        "mean_abs_y_px": float(np.mean(np.abs(dy_px))) if euclid.size else 0.0,
        "median_error_pct_diagonal": (
            float(np.median(euclid) / diagonal_px * 100) if euclid.size else 0.0
        ),
        "screen_width": int(screen_width),
        "screen_height": int(screen_height),
    }

    # Degrees only when the geometry was actually supplied -- see docstring.
    if viewing_distance_cm and screen_diagonal_in:
        diagonal_cm = screen_diagonal_in * 2.54
        px_per_cm = diagonal_px / diagonal_cm
        for key, px in (
            ("median_error_deg", metrics["median_error_px"]),
            ("mean_error_deg", metrics["mean_error_px"]),
            ("p95_error_deg", metrics["p95_error_px"]),
        ):
            cm = px / px_per_cm
            # Angle subtended at the eye by an on-screen offset of `cm`,
            # at `viewing_distance_cm`. Small-angle-safe form.
            metrics[key] = float(math.degrees(2 * math.atan(cm / (2 * viewing_distance_cm))))
        metrics["viewing_distance_cm"] = float(viewing_distance_cm)
        metrics["screen_diagonal_in"] = float(screen_diagonal_in)
    else:
        metrics["degrees_unavailable"] = (
            "viewing_distance_cm and screen_diagonal_in were not supplied; "
            "backend/calibration stores screen size in pixels only, so visual "
            "angle cannot be derived from the session alone"
        )

    return metrics


# ----------------------------------------------------------------------


@dataclass
class FoldResults:
    """Held-out predictions at two granularities.

    Both are needed, and they answer different questions:

      * point-level -- the fixation is averaged over its frames before
        scoring. This measures the MAPPING's accuracy, with detector jitter
        averaged out, and is the number comparable to calibration accuracy
        figures in the literature.

      * frame-level -- every held-out frame scored individually. This is what
        a single live gaze estimate actually gives you, jitter included, and
        it is always the larger number. Reporting only the point-level figure
        would overstate live performance by roughly sqrt(frames per point).
    """

    point_pred: np.ndarray
    point_true: np.ndarray
    points: List[int]
    frame_pred: np.ndarray
    frame_true: np.ndarray


def leave_one_point_out(
    dataset: Dataset,
    degree: int,
    ridge: float = DEFAULT_RIDGE,
) -> FoldResults:
    """Refit without each point in turn, predict it, collect the results."""
    point_pred: List[np.ndarray] = []
    point_true: List[np.ndarray] = []
    kept: List[int] = []
    frame_pred: List[np.ndarray] = []
    frame_true: List[np.ndarray] = []

    for point in dataset.unique_points:
        test_mask = dataset.groups == point
        train_mask = ~test_mask
        if train_mask.sum() == 0 or np.unique(dataset.groups[train_mask]).size < 2:
            continue

        model = GazeModel.fit(
            dataset.X[train_mask],
            dataset.y[train_mask],
            feature_set=dataset.feature_set,
            degree=degree,
            ridge=ridge,
            screen_width=dataset.screen_width,
            screen_height=dataset.screen_height,
        )
        predicted = model.predict(dataset.X[test_mask])
        actual = dataset.y[test_mask]

        point_pred.append(predicted.mean(axis=0))
        point_true.append(actual.mean(axis=0))
        kept.append(int(point))
        frame_pred.append(predicted)
        frame_true.append(actual)

    if not point_pred:
        empty = np.empty((0, 2))
        return FoldResults(empty, empty, [], empty, empty)

    return FoldResults(
        point_pred=np.asarray(point_pred),
        point_true=np.asarray(point_true),
        points=kept,
        frame_pred=np.concatenate(frame_pred),
        frame_true=np.concatenate(frame_true),
    )


def _aggregate_by_group(
    values: np.ndarray, groups: np.ndarray
) -> Tuple[np.ndarray, List[int]]:
    """Mean of `values` within each group, in sorted group order."""
    unique = np.unique(groups)
    return (
        np.asarray([values[groups == g].mean(axis=0) for g in unique]),
        [int(g) for g in unique],
    )


def cross_validate(
    dataset: Dataset,
    degree: int,
    ridge: float = DEFAULT_RIDGE,
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
) -> Dict:
    """Leave-one-point-out error report for one candidate configuration."""
    folds = leave_one_point_out(dataset, degree, ridge)
    metrics = error_metrics(
        folds.point_pred, folds.point_true,
        dataset.screen_width, dataset.screen_height,
        viewing_distance_cm, screen_diagonal_in,
    )
    metrics["validation"] = "leave_one_point_out"
    metrics["folds"] = len(folds.points)

    # What one live frame gives you, jitter included -- always worse than the
    # point-averaged figure above. See FoldResults.
    if folds.frame_pred.size:
        frame_metrics = error_metrics(
            folds.frame_pred, folds.frame_true,
            dataset.screen_width, dataset.screen_height,
        )
        metrics["per_frame_median_error_px"] = frame_metrics["median_error_px"]
        metrics["per_frame_p95_error_px"] = frame_metrics["p95_error_px"]

    # Per-point error, so a single bad calibration target can be identified
    # and re-presented rather than quietly dragging the whole session down.
    if folds.points:
        dx = (folds.point_pred[:, 0] - folds.point_true[:, 0]) * dataset.screen_width
        dy = (folds.point_pred[:, 1] - folds.point_true[:, 1]) * dataset.screen_height
        per_point = np.sqrt(dx ** 2 + dy ** 2)
        metrics["per_point_error_px"] = {
            int(p): round(float(e), 2)
            for p, e in zip(folds.points, per_point, strict=True)
        }
        worst = int(np.argmax(per_point))
        metrics["worst_point"] = {
            "point_index": folds.points[worst],
            "error_px": round(float(per_point[worst]), 2),
        }
    return metrics


def training_error(
    model: GazeModel,
    dataset: Dataset,
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
) -> Dict:
    """Error on the data the model was fitted to.

    Aggregated per point, exactly like the held-out figure -- otherwise the
    two aren't comparable and the overfitting gap between them is meaningless
    (per-frame error carries detector jitter that point-averaging removes,
    which can make training error look WORSE than held-out error).

    Reported alongside the held-out number, never instead of it.
    """
    pred_by_point, _ = _aggregate_by_group(model.predict(dataset.X), dataset.groups)
    true_by_point, _ = _aggregate_by_group(dataset.y, dataset.groups)

    metrics = error_metrics(
        pred_by_point, true_by_point,
        dataset.screen_width, dataset.screen_height,
        viewing_distance_cm, screen_diagonal_in,
    )
    metrics["validation"] = "training_fit_not_held_out"
    return metrics


# ----------------------------------------------------------------------


def candidate_configs(n_points: int, feature_sets: Sequence[str]) -> List[Dict]:
    """Every (feature_set, degree, ridge) worth trying at this point count.

    Degrees above the capacity cap for a given feature set are never
    generated, so a 9-point session simply cannot select a model that would
    interpolate its own targets. See model.max_degree_for.
    """
    configs: List[Dict] = []
    for fs in feature_sets:
        top = max_degree_for(fs, n_points)
        for degree in range(1, top + 1):
            for ridge in CANDIDATE_RIDGES:
                configs.append({"feature_set": fs, "degree": degree, "ridge": ridge})
    return configs


def select_model(
    datasets: Dict[str, Dataset],
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
) -> Dict:
    """Pick the configuration with the lowest held-out median error.

    `datasets` maps feature_set -> Dataset (they differ: `both_eyes` drops
    one-eyed rows). Ties break towards the SIMPLER model -- lower degree
    first, then fewer features -- because at 9-16 points a marginal
    cross-validation win is well inside the noise, and the simpler mapping is
    the one more likely to hold up on the next participant.
    """
    n_points = max(ds.n_points for ds in datasets.values())
    configs = candidate_configs(n_points, list(datasets))

    results: List[Dict] = []
    for cfg in configs:
        ds = datasets.get(cfg["feature_set"])
        if ds is None or ds.n_points < 3:
            continue
        metrics = cross_validate(
            ds, cfg["degree"], cfg["ridge"],
            viewing_distance_cm, screen_diagonal_in,
        )
        if not metrics["folds"]:
            continue
        results.append({
            **cfg,
            "median_error_px": metrics["median_error_px"],
            "mean_error_px": metrics["mean_error_px"],
            "n_parameters": n_terms(ds.X.shape[1], cfg["degree"]),
            "n_points": ds.n_points,
        })

    if not results:
        raise ValueError("no candidate model could be cross-validated on this session")

    results.sort(key=lambda r: (
        round(r["median_error_px"], 3),      # rounded: sub-pixel CV wins are noise
        r["degree"],
        r["n_parameters"],
    ))
    best = results[0]

    return {
        "chosen": {k: best[k] for k in ("feature_set", "degree", "ridge")},
        "chosen_median_error_px": best["median_error_px"],
        "n_parameters": best["n_parameters"],
        "n_candidates": len(results),
        "selection_criterion": "lowest leave-one-point-out median pixel error, ties to simpler",
        # Kept so the paper can report what the alternatives actually scored,
        # rather than asserting the winner was obviously right.
        "leaderboard": [
            {
                "feature_set": r["feature_set"],
                "degree": r["degree"],
                "ridge": r["ridge"],
                "n_parameters": r["n_parameters"],
                "median_error_px": round(r["median_error_px"], 2),
            }
            for r in results[:8]
        ],
    }


__all__ = [
    "error_metrics",
    "FoldResults",
    "leave_one_point_out",
    "cross_validate",
    "training_error",
    "candidate_configs",
    "select_model",
    "CANDIDATE_RIDGES",
]
