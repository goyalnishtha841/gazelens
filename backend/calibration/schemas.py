"""
schemas.py

Pydantic request/response models -- the HTTP boundary only.

Pydantic appears here and nowhere else in the module. Everything inward of
the route layer (session.py, storage.py, points.py, and all of backend/cv)
uses plain dataclasses, matching backend/agents. The rule: Pydantic where
untrusted JSON arrives and needs validating, dataclasses everywhere else.

NOTE ON THE FIELD NAMES -- frontend/Calibration.jsx and
frontend/src/api/client.js are not in this repo (the README lists them as
built, but they've never been pushed), so this contract was defined here
rather than read off the client. It is documented in CONTRACT.md. If the
real client sends different names, this file is the only place that needs
to change: the route layer converts to internal types immediately.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .points import DEFAULT_PATTERN, PATTERNS
from .session import DEFAULT_SAMPLES_PER_POINT


class CalibrationPointModel(BaseModel):
    """One on-screen target, normalised to [0, 1] of the viewport."""

    index: int
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


# ----------------------------------------------------------------------
# POST /api/calibration/sessions


class StartCalibrationRequest(BaseModel):
    participant_id: str = Field(..., min_length=1, max_length=128)
    pattern: int = Field(DEFAULT_PATTERN, description="9 or 16 targets")
    screen_width: int = Field(..., gt=0, le=16384, description="viewport px")
    screen_height: int = Field(..., gt=0, le=16384, description="viewport px")
    samples_per_point: int = Field(DEFAULT_SAMPLES_PER_POINT, ge=1, le=120)

    @field_validator("pattern")
    @classmethod
    def _known_pattern(cls, v: int) -> int:
        if v not in PATTERNS:
            raise ValueError(f"pattern must be one of {sorted(PATTERNS)}")
        return v


class StartCalibrationResponse(BaseModel):
    session_id: str
    participant_id: str
    pattern: int
    samples_per_point: int
    points: List[CalibrationPointModel]
    status: str


# ----------------------------------------------------------------------
# POST /api/calibration/sessions/{session_id}/samples


class SubmitSamplesRequest(BaseModel):
    """A burst of frames captured while one target was on screen.

    Frames are base64 (a raw string or a full `data:image/jpeg;base64,...`
    data URL -- canvas.toDataURL() output can be posted as-is).

    A burst rather than one frame per request: the client holds each target
    for roughly a second, and batching that fixation into a single POST
    keeps the round-trip count down and guarantees every frame in the batch
    really did belong to the same target.
    """

    point_index: int = Field(..., ge=0)
    frames: List[str] = Field(..., min_length=1, max_length=120)

    # Optional client-side target override. Present because the server owns
    # the grid, but if Calibration.jsx lays its targets out differently, the
    # truth is what was actually on the participant's screen -- so the client
    # is allowed to say so, and the server records which source it used.
    target_x: Optional[float] = Field(None, ge=0.0, le=1.0)
    target_y: Optional[float] = Field(None, ge=0.0, le=1.0)

    client_timestamp: Optional[float] = None


class PupilReading(BaseModel):
    """Echoed back per eye so the client can draw a live preview dot."""

    x_eye: float
    y_eye: float
    x_frame: float
    y_frame: float
    confidence: float


class SubmitSamplesResponse(BaseModel):
    session_id: str
    point_index: int
    target_x: float
    target_y: float
    target_source: str                    # "server_grid" | "client"

    accepted: int                          # frames that yielded a pupil
    rejected: int                          # blinks, no face, undecodable
    samples_for_point: int                 # running total for this target
    samples_required: int
    point_complete: bool

    points_remaining: List[int]
    session_complete: bool

    # Most recent usable reading, for the client's preview overlay. Null when
    # every frame in the batch was a miss.
    last_reading: Optional[Dict[str, PupilReading]] = None
    note: str = ""


# ----------------------------------------------------------------------
# GET /api/calibration/sessions/{session_id}


class QualityModel(BaseModel):
    usable: bool
    reasons: List[str]
    point_coverage: float
    points_covered: int
    points_total: int
    total_samples: int
    rejected_frames: int
    detection_rate: float
    both_eyes_rate: float
    mean_confidence: float


class SessionStatusResponse(BaseModel):
    session_id: str
    participant_id: str
    pattern: int
    status: str
    screen_width: int
    screen_height: int
    samples_per_point: int
    points: List[CalibrationPointModel]
    sample_counts: Dict[int, int]
    points_remaining: List[int]
    is_complete: bool
    quality: QualityModel
    created_at: float
    updated_at: float


class SessionSummary(BaseModel):
    session_id: Optional[str] = None
    participant_id: Optional[str] = None
    pattern: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[float] = None
    total_samples: int = 0
    usable: Optional[bool] = None


# ----------------------------------------------------------------------
# POST /api/calibration/sessions/{session_id}/complete


class CompleteCalibrationResponse(BaseModel):
    session_id: str
    status: str
    total_samples: int
    quality: QualityModel

    # Where the data landed. backend/gaze_estimation reads training_csv --
    # that's the handoff.
    session_file: str
    training_csv: str
    training_row_count: int

    # False when quality.usable is False. The session is still saved; this is
    # the flag telling the next stage not to trust it blindly.
    ready_for_regression: bool


class PatternsResponse(BaseModel):
    """GET /api/calibration/patterns -- lets the client render the same grid
    the server will score against, instead of hardcoding it twice."""

    patterns: Dict[int, List[CalibrationPointModel]]
    default_pattern: int


__all__ = [
    "CalibrationPointModel",
    "StartCalibrationRequest",
    "StartCalibrationResponse",
    "SubmitSamplesRequest",
    "SubmitSamplesResponse",
    "PupilReading",
    "QualityModel",
    "SessionStatusResponse",
    "SessionSummary",
    "CompleteCalibrationResponse",
    "PatternsResponse",
]
