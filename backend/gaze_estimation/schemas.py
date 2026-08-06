"""
schemas.py

Pydantic request/response models -- the HTTP boundary only.

Same rule as backend/calibration: Pydantic where untrusted JSON arrives,
plain dataclasses everywhere inward of the route layer.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .features import DEFAULT_FEATURE_SET, FEATURE_SETS


class TrainRequest(BaseModel):
    """Train a gaze model from a stored calibration session.

    All fields optional: the default path is "train session X with whatever
    backend/calibration stored for it, and pick the model yourself".
    """

    min_confidence: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Drop calibration rows whose detector confidence is below this.",
    )

    # Needed for degrees of visual angle, and ONLY for that. backend/
    # calibration records screen size in pixels, so these cannot be recovered
    # from a stored session -- without them the response reports pixel error
    # only rather than assuming a viewing distance.
    viewing_distance_cm: Optional[float] = Field(
        None, gt=0, le=300,
        description="Eye-to-screen distance. Supply with screen_diagonal_in to get degrees.",
    )
    screen_diagonal_in: Optional[float] = Field(
        None, gt=0, le=120,
        description="Physical screen diagonal in inches.",
    )

    # Overrides for automatic model selection -- e.g. holding the
    # configuration fixed across participants for a paper.
    feature_set: Optional[str] = Field(None, description=f"one of {sorted(FEATURE_SETS)}")
    degree: Optional[int] = Field(None, ge=1, le=3)

    @model_validator(mode="after")
    def _check(self) -> "TrainRequest":
        if self.feature_set and self.feature_set not in FEATURE_SETS:
            raise ValueError(f"feature_set must be one of {sorted(FEATURE_SETS)}")
        if (self.viewing_distance_cm is None) != (self.screen_diagonal_in is None):
            raise ValueError(
                "viewing_distance_cm and screen_diagonal_in must be supplied "
                "together -- visual angle needs both"
            )
        return self


class ChosenModel(BaseModel):
    feature_set: str
    degree: int
    ridge: float


class LeaderboardEntry(BaseModel):
    feature_set: str
    degree: int
    ridge: float
    n_parameters: int
    median_error_px: float


class SelectionReport(BaseModel):
    chosen: ChosenModel
    selection_criterion: str
    n_parameters: Optional[int] = None
    n_candidates: Optional[int] = None
    leaderboard: List[LeaderboardEntry] = Field(default_factory=list)


class ErrorMetrics(BaseModel):
    """Held-out accuracy. `validation` states how it was measured.

    Degrees fields are absent unless viewing distance + screen size were
    supplied on the request; `degrees_unavailable` explains why when so.
    """

    n: int
    validation: str = ""
    folds: Optional[int] = None

    median_error_px: float
    mean_error_px: float
    p95_error_px: float
    max_error_px: float
    mean_abs_x_px: float
    mean_abs_y_px: float
    median_error_pct_diagonal: float

    # Error on individual held-out FRAMES rather than point averages -- what a
    # single live gaze estimate actually delivers. Always the larger number.
    per_frame_median_error_px: Optional[float] = None
    per_frame_p95_error_px: Optional[float] = None

    screen_width: int
    screen_height: int

    median_error_deg: Optional[float] = None
    mean_error_deg: Optional[float] = None
    p95_error_deg: Optional[float] = None
    viewing_distance_cm: Optional[float] = None
    screen_diagonal_in: Optional[float] = None
    degrees_unavailable: Optional[str] = None

    per_point_error_px: Dict[int, float] = Field(default_factory=dict)
    worst_point: Optional[Dict] = None


class TrainResponse(BaseModel):
    session_id: str
    participant_id: str

    n_points: int
    n_samples: int

    selection: SelectionReport
    metrics: ErrorMetrics                # leave-one-point-out -- the honest one
    # Fit error, for the overfitting gap only -- never quote it alone.
    # Optional because a model reloaded from disk no longer has its training
    # data, so the fit error cannot be recomputed. It comes back null there
    # rather than being filled with the held-out numbers, which would be a
    # different measurement wearing this field's name.
    training_metrics: Optional[ErrorMetrics] = None

    model_path: Optional[str] = None
    trained_in_ms: float

    # False when held-out error is too large to attribute gaze to UI elements
    # with. The model is still saved and still callable -- this is the flag
    # that says don't build a UX report on it.
    usable_for_attribution: bool
    warnings: List[str] = Field(default_factory=list)


class ModelSummary(BaseModel):
    session_id: str
    participant_id: str
    feature_set: str
    degree: int
    n_points: int
    median_error_px: Optional[float] = None
    trained_at: float


# ----------------------------------------------------------------------
# live inference


class PupilInput(BaseModel):
    """One eye's pupil centre, normalised WITHIN its eye box ([0,1]).

    These are `x_eye`/`y_eye` from a cv.PupilDetection -- not frame
    coordinates. Sending frame coordinates would be silently wrong rather
    than an error, so it's worth being explicit: the model was trained on
    eye-box coordinates and will produce nonsense from anything else.
    """

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class EstimateRequest(BaseModel):
    left: Optional[PupilInput] = None
    right: Optional[PupilInput] = None
    timestamp: Optional[float] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    smoothing: float = Field(
        0.0, ge=0.0, lt=1.0,
        description="EMA factor for a live cursor. Leave at 0 for the raw "
                    "stream attribution consumes.",
    )

    @model_validator(mode="after")
    def _at_least_one_eye(self) -> "EstimateRequest":
        if self.left is None and self.right is None:
            raise ValueError("at least one of left/right pupil must be supplied")
        return self


class FrameInput(BaseModel):
    left: Optional[PupilInput] = None
    right: Optional[PupilInput] = None
    timestamp: Optional[float] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class EstimateBatchRequest(BaseModel):
    """A burst of frames. Frames with no pupil are allowed here -- they come
    back as invalid GazePoints, preserving the gap in the stream."""

    frames: List[FrameInput] = Field(..., min_length=1, max_length=1000)
    smoothing: float = Field(0.0, ge=0.0, lt=1.0)


class GazePointModel(BaseModel):
    timestamp: float
    x: float
    y: float
    x_px: float
    y_px: float
    valid: bool
    in_bounds: bool
    confidence: float
    note: str = ""


class EstimateResponse(BaseModel):
    session_id: str
    gaze: GazePointModel
    # The model's own held-out error, so a consumer can state an error bar
    # without going back to the training run.
    model_median_error_px: Optional[float] = None


class EstimateBatchResponse(BaseModel):
    session_id: str
    gaze: List[GazePointModel]
    valid_count: int
    invalid_count: int
    model_median_error_px: Optional[float] = None


__all__ = [
    "TrainRequest",
    "TrainResponse",
    "SelectionReport",
    "ChosenModel",
    "LeaderboardEntry",
    "ErrorMetrics",
    "ModelSummary",
    "PupilInput",
    "FrameInput",
    "EstimateRequest",
    "EstimateBatchRequest",
    "EstimateResponse",
    "EstimateBatchResponse",
    "GazePointModel",
    "DEFAULT_FEATURE_SET",
]
