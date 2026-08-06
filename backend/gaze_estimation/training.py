"""
training.py

Stored calibration session -> fitted, evaluated, persisted gaze model.

    result = train_session("cal_a1b2c3d4e5f6")
    result.model.predict_one(left, right)

Reads backend/calibration's own objects directly (via its store), so there
is no translation layer and no second copy of its schema. A CSV path also
works, for a session handed over as a file.

Training a session is a few closed-form solves over at most a few hundred
rows -- milliseconds on CPU, no GPU anywhere in the path.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from calibration import get_store as get_calibration_store
from calibration.storage import SessionNotFound

from .evaluation import cross_validate, select_model, training_error
from .features import (
    FEATURE_SETS,
    Dataset,
    InsufficientCalibrationData,
    build_dataset,
)
from .model import GazeModel

MODEL_DIR = Path(__file__).resolve().parent / "gaze_models"


@dataclass
class TrainingResult:
    """Everything a caller needs to decide whether to trust this model."""

    model: GazeModel
    metrics: Dict                 # held-out, leave-one-point-out
    training_metrics: Dict        # fit error, for the overfitting gap only
    selection: Dict
    model_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
    trained_in_ms: float = 0.0

    @property
    def median_error_px(self) -> float:
        return self.metrics.get("median_error_px", 0.0)


# Held-out median error beyond which the mapping isn't worth attributing gaze
# with. ~5% of a 1920x1080 diagonal is roughly 110px -- about the size of a
# button. Past that, "which element was looked at" stops being answerable, and
# every downstream metric the agents reason over inherits the error.
POOR_FIT_PX_FRACTION = 0.05


def load_rows_from_session(session_id: str) -> List[Dict]:
    """Pull training rows out of a stored calibration session."""
    try:
        session = get_calibration_store().get(session_id)
    except SessionNotFound as exc:
        raise SessionNotFound(
            f"no calibration session {session_id!r} -- calibrate before training"
        ) from exc
    return session.training_rows()


def load_rows_from_csv(csv_path: Path) -> List[Dict]:
    """Read the cal_<id>.csv export backend/calibration writes on completion."""
    import csv as _csv

    with Path(csv_path).open(encoding="utf-8", newline="") as fh:
        return list(_csv.DictReader(fh))


def _build_datasets(rows: Sequence[Dict], min_confidence: float) -> Dict[str, Dataset]:
    """One Dataset per feature set. Sets that can't be built are skipped.

    `both_eyes` legitimately fails on a session where the participant was
    half-blinking throughout -- that's a reason to drop the candidate, not to
    fail the training run.
    """
    datasets: Dict[str, Dataset] = {}
    errors: Dict[str, str] = {}
    for name in FEATURE_SETS:
        try:
            datasets[name] = build_dataset(rows, feature_set=name,
                                           min_confidence=min_confidence)
        except InsufficientCalibrationData as exc:
            errors[name] = str(exc)

    if not datasets:
        raise InsufficientCalibrationData(
            "no feature set could be built from this session: "
            + "; ".join(f"{k}: {v}" for k, v in errors.items())
        )
    return datasets


def train_from_rows(
    rows: Sequence[Dict],
    session_id: str = "",
    participant_id: str = "",
    min_confidence: float = 0.0,
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
    feature_set: Optional[str] = None,
    degree: Optional[int] = None,
    persist: bool = True,
    model_dir: Optional[Path] = None,
) -> TrainingResult:
    """Fit, cross-validate, and persist a per-session gaze model.

    Per-session by design: gaze mapping does not transfer between people or
    camera setups. Head position, seating distance, lighting and lens all
    shift the pupil-to-screen relationship, so a model trained on one sitting
    is a model for that sitting. `feature_set`/`degree` override automatic
    selection when a caller wants a fixed configuration (e.g. to hold it
    constant across participants for a paper).
    """
    started = time.perf_counter()
    warnings: List[str] = []

    datasets = _build_datasets(rows, min_confidence)

    if feature_set or degree:
        # Manual override -- still cross-validated, so the reported error
        # stays honest even when the configuration was dictated.
        chosen_fs = feature_set or next(iter(datasets))
        if chosen_fs not in datasets:
            raise InsufficientCalibrationData(
                f"feature_set {chosen_fs!r} has no usable rows in this session"
            )
        chosen = {"feature_set": chosen_fs, "degree": degree or 2, "ridge": 1e-4}
        selection = {
            "chosen": chosen,
            "selection_criterion": "caller override (not auto-selected)",
            "leaderboard": [],
        }
    else:
        selection = select_model(datasets, viewing_distance_cm, screen_diagonal_in)
        chosen = selection["chosen"]

    dataset = datasets[chosen["feature_set"]]

    metrics = cross_validate(
        dataset, chosen["degree"], chosen["ridge"],
        viewing_distance_cm, screen_diagonal_in,
    )

    # Final model is fitted on ALL points; the error reported with it comes
    # from the leave-one-point-out run above, never from this fit.
    model = GazeModel.fit(
        dataset.X, dataset.y,
        feature_set=chosen["feature_set"],
        degree=chosen["degree"],
        ridge=chosen["ridge"],
        screen_width=dataset.screen_width,
        screen_height=dataset.screen_height,
        session_id=session_id,
        participant_id=participant_id,
        n_points=dataset.n_points,
    )
    fit_metrics = training_error(model, dataset, viewing_distance_cm, screen_diagonal_in)
    model.metrics = metrics
    model.selection = selection

    # ---- warnings: things a caller should see before trusting this ----
    diagonal = (dataset.screen_width ** 2 + dataset.screen_height ** 2) ** 0.5
    if metrics["median_error_px"] > POOR_FIT_PX_FRACTION * diagonal:
        warnings.append(
            f"held-out median error {metrics['median_error_px']:.0f}px exceeds "
            f"{POOR_FIT_PX_FRACTION:.0%} of the screen diagonal -- gaze-to-element "
            f"attribution will be unreliable; consider recalibrating"
        )
    if fit_metrics["median_error_px"] > 0 and \
            metrics["median_error_px"] > 3 * fit_metrics["median_error_px"]:
        warnings.append(
            f"held-out error ({metrics['median_error_px']:.0f}px) is far above "
            f"training error ({fit_metrics['median_error_px']:.0f}px) -- the model "
            f"is fitting session noise"
        )
    if dataset.n_points < 9:
        warnings.append(
            f"only {dataset.n_points} calibration points had usable data; "
            f"9 is the intended minimum"
        )
    if dataset.dropped_rows:
        warnings.append(
            f"{dataset.dropped_rows} of {dataset.dropped_rows + dataset.n_samples} "
            f"rows were unusable (no pupil, or below min_confidence)"
        )

    result = TrainingResult(
        model=model,
        metrics=metrics,
        training_metrics=fit_metrics,
        selection=selection,
        warnings=warnings,
        trained_in_ms=(time.perf_counter() - started) * 1000,
    )

    if persist and session_id:
        result.model_path = save_model(model, model_dir)
    return result


def train_session(
    session_id: str,
    min_confidence: float = 0.0,
    viewing_distance_cm: Optional[float] = None,
    screen_diagonal_in: Optional[float] = None,
    feature_set: Optional[str] = None,
    degree: Optional[int] = None,
    model_dir: Optional[Path] = None,
) -> TrainingResult:
    """Train from a calibration session held by backend/calibration's store."""
    session = get_calibration_store().get(session_id)
    return train_from_rows(
        session.training_rows(),
        session_id=session.session_id,
        participant_id=session.participant_id,
        min_confidence=min_confidence,
        viewing_distance_cm=viewing_distance_cm,
        screen_diagonal_in=screen_diagonal_in,
        feature_set=feature_set,
        degree=degree,
        model_dir=model_dir,
    )


# ----------------------------------------------------------------------
# model persistence -- one JSON per session, so calibration happens once


def _model_dir(model_dir: Optional[Path] = None) -> Path:
    return Path(model_dir) if model_dir else MODEL_DIR


def model_path_for(session_id: str, model_dir: Optional[Path] = None) -> Path:
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        raise ValueError(f"invalid session id {session_id!r}")
    return _model_dir(model_dir) / f"{session_id}.json"


def save_model(model: GazeModel, model_dir: Optional[Path] = None) -> Path:
    return model.save(model_path_for(model.session_id, model_dir))


def load_model(session_id: str, model_dir: Optional[Path] = None) -> GazeModel:
    path = model_path_for(session_id, model_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no trained gaze model for session {session_id!r} -- train it first"
        )
    return GazeModel.load(path)


def has_model(session_id: str, model_dir: Optional[Path] = None) -> bool:
    try:
        return model_path_for(session_id, model_dir).exists()
    except ValueError:
        return False


def list_models(model_dir: Optional[Path] = None) -> List[Dict]:
    directory = _model_dir(model_dir)
    if not directory.exists():
        return []

    out: List[Dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            model = GazeModel.load(path)
        except (ValueError, OSError, KeyError):
            continue    # a stale-format or hand-edited model shouldn't take
                        # down the whole listing
        out.append({
            "session_id": model.session_id,
            "participant_id": model.participant_id,
            "feature_set": model.feature_set,
            "degree": model.degree,
            "n_points": model.n_points,
            "median_error_px": model.metrics.get("median_error_px"),
            "trained_at": model.trained_at,
        })
    return out


def delete_model(session_id: str, model_dir: Optional[Path] = None) -> bool:
    path = model_path_for(session_id, model_dir)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


__all__ = [
    "TrainingResult",
    "MODEL_DIR",
    "POOR_FIT_PX_FRACTION",
    "train_from_rows",
    "train_session",
    "load_rows_from_session",
    "load_rows_from_csv",
    "save_model",
    "load_model",
    "has_model",
    "list_models",
    "delete_model",
    "model_path_for",
]
