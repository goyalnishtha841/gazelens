"""
backend/gaze_estimation -- pupil position -> screen coordinate.

    from gaze_estimation import train_session, get_estimator

    train_session("cal_a1b2c3d4e5f6")                  # once, after calibration
    est = get_estimator("cal_a1b2c3d4e5f6")            # cached
    point = est.estimate(left=(0.51, 0.48), right=(0.49, 0.49))

Trains one model per calibration session from that session's own data --
gaze mapping doesn't transfer between people or camera setups. Reads
backend/calibration's stored format directly; never touches webcam frames.
Emits the raw gaze stream backend/attribution will consume (CONTRACT.md).

Relative imports and the one sys.path line, same as backend/calibration:
this package and backend/calibration both define schemas.py, so flat sibling
imports would let one shadow the other.
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from .features import (                     # noqa: E402
    DEFAULT_FEATURE_SET,
    FEATURE_SETS,
    Dataset,
    InsufficientCalibrationData,
    build_dataset,
    features_from_pupils,
)
from .model import GazeModel, max_degree_for, n_terms    # noqa: E402
from .evaluation import (                   # noqa: E402
    cross_validate,
    error_metrics,
    leave_one_point_out,
    select_model,
    training_error,
)
from .synthetic import (                    # noqa: E402
    GOOD_SESSION,
    NOISY_SESSION,
    PRISTINE_SESSION,
    GazeGeometry,
    SessionProfile,
    generate_calibration_session,
    generate_training_rows,
    synthetic_gaze_stream,
)
from .training import (                     # noqa: E402
    MODEL_DIR,
    POOR_FIT_PX_FRACTION,
    TrainingResult,
    delete_model,
    has_model,
    list_models,
    load_model,
    save_model,
    train_from_rows,
    train_session,
)
from .estimator import (                    # noqa: E402
    GazePoint,
    LiveGazeEstimator,
    clear_cache,
    clear_estimator,
    gaze_stream,
    get_estimator,
    register_estimator,
    set_model_dir,
)
from .routes import router                  # noqa: E402

__all__ = [
    "router",
    # model
    "GazeModel",
    "max_degree_for",
    "n_terms",
    # features
    "Dataset",
    "FEATURE_SETS",
    "DEFAULT_FEATURE_SET",
    "InsufficientCalibrationData",
    "build_dataset",
    "features_from_pupils",
    # evaluation
    "cross_validate",
    "error_metrics",
    "leave_one_point_out",
    "select_model",
    "training_error",
    # synthetic data
    "GazeGeometry",
    "SessionProfile",
    "GOOD_SESSION",
    "NOISY_SESSION",
    "PRISTINE_SESSION",
    "generate_calibration_session",
    "generate_training_rows",
    "synthetic_gaze_stream",
    # training
    "TrainingResult",
    "train_session",
    "train_from_rows",
    "save_model",
    "load_model",
    "has_model",
    "list_models",
    "delete_model",
    "MODEL_DIR",
    "POOR_FIT_PX_FRACTION",
    # live inference
    "GazePoint",
    "LiveGazeEstimator",
    "get_estimator",
    "register_estimator",
    "clear_estimator",
    "clear_cache",
    "set_model_dir",
    "gaze_stream",
]
