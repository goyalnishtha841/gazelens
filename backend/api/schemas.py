"""
schemas.py

Pydantic request/response models for the auth and session API.

CONTRACT NOTE -- frontend/src/api/client.js is NOT in this repo. The README
describes a built frontend whose session/report calls are mocked there, but
neither the frontend nor backend/render has ever been pushed to origin/main.
So this shape was defined here rather than read off the client, following the
screens the README lists (landing, auth, calibration, live session, dashboard,
report view). See CONTRACT.md for the field-by-field rationale and for what to
check when the real client.js turns up.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from .layouts import AVAILABLE_TEST_UIS
from .models import MODE_TEST_UI, SESSION_MODES, SESSION_STATUSES
from .security import MIN_PASSWORD_LENGTH


# ----------------------------------------------------------------------
# auth


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)
    # Shown in the app ("Hi Nishtha"), so it is required rather than guessed
    # from the email. Strength rules for the password live in
    # security.validate_new_password, applied by the signup route.
    full_name: str = Field(..., max_length=80)

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        name = " ".join(v.split())
        if len(name) < 2:
            raise ValueError("enter your name (at least 2 characters)")
        if not any(c.isalpha() for c in name):
            raise ValueError("your name must contain letters")
        return name


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    # Named token_type and lowercase "bearer" to match the OAuth2 convention
    # FastAPI's OAuth2PasswordBearer and every HTTP client expect.
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ----------------------------------------------------------------------
# sessions


class CreateSessionRequest(BaseModel):
    """Start a session.

    mode="test_ui" needs ui_page; mode="url" needs target_url. Enforced here
    rather than in the route so an invalid combination is a 422 with a field
    path, not a 500 three modules deep.
    """

    mode: str = Field(MODE_TEST_UI, description=f"one of {list(SESSION_MODES)}")
    ui_page: Optional[str] = Field(
        None, description=f"required for mode='test_ui'; one of {list(AVAILABLE_TEST_UIS)}"
    )
    target_url: Optional[str] = Field(None, max_length=2048,
                                      description="required for mode='url'")
    label: Optional[str] = Field(None, max_length=255,
                                 description="free-text name for the dashboard")
    # Reuse a calibration the participant already completed, instead of
    # recalibrating for every session in a sitting.
    calibration_session_id: Optional[str] = Field(None, max_length=40)

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v: str) -> str:
        if v not in SESSION_MODES:
            raise ValueError(f"mode must be one of {list(SESSION_MODES)}")
        return v

    @field_validator("target_url")
    @classmethod
    def _http_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("target_url must start with http:// or https://")
        return v

    def validate_combination(self) -> None:
        if self.mode == MODE_TEST_UI:
            if not self.ui_page:
                raise ValueError("ui_page is required when mode='test_ui'")
            if self.ui_page not in AVAILABLE_TEST_UIS:
                raise ValueError(
                    f"unknown ui_page {self.ui_page!r}; "
                    f"available: {list(AVAILABLE_TEST_UIS)}"
                )
        else:
            if not self.target_url:
                raise ValueError("target_url is required when mode='url'")


class SessionResponse(BaseModel):
    id: str
    mode: str
    ui_page: Optional[str] = None
    target_url: Optional[str] = None
    label: Optional[str] = None
    status: str
    error: Optional[str] = None

    calibration_session_id: Optional[str] = None
    gaze_model_trained: bool = False
    gaze_point_count: int = 0

    # True when the element boxes were not derived from the page actually
    # shown -- currently every mode='url' session, since backend/render isn't
    # in the repo. Surfaced so no caller mistakes those metrics for real ones.
    layout_is_placeholder: bool = False

    has_report: bool = False
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Pulled from the report's own pipeline_result when has_report is True,
    # so a dashboard can show issue counts without a second fetch per
    # session. None (not 0) when there's no report yet -- 0 would claim a
    # clean bill of health that hasn't actually been earned.
    issue_count: Optional[int] = None
    high_issue_count: Optional[int] = None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Paginated, because the dashboard lists every session a user ever ran."""

    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(SessionResponse):
    """One session, plus the state of the modules it depends on."""

    calibration: Optional[Dict[str, Any]] = None
    element_layout: Optional[Dict[str, Any]] = None
    # mode='url' only: what backend/render detected and how much it guessed.
    capture_meta: Optional[Dict[str, Any]] = None
    # What the client should do next -- so the live-session UI doesn't have to
    # reimplement the status machine to know whether to calibrate or record.
    next_action: Optional[str] = None


class CalibrationLinkRequest(BaseModel):
    """Attach a completed calibration session and train its gaze model."""

    calibration_session_id: str = Field(..., min_length=1, max_length=40)
    train_model: bool = True
    # The live session's CURRENT window.innerWidth/innerHeight, so the
    # server can refuse to link against a calibration recorded at a
    # different screen size rather than silently training/serving a
    # mapping calibrated for different screen geometry. Optional only for
    # backward compatibility with any caller that predates this check --
    # omitting it skips the check entirely rather than assuming a match.
    screen_width: Optional[int] = Field(None, gt=0, le=16384)
    screen_height: Optional[int] = Field(None, gt=0, le=16384)


class CalibrationLinkResponse(BaseModel):
    session_id: str
    calibration_session_id: str
    status: str
    gaze_model_trained: bool
    # True when linking was refused because the caller's screen_width/
    # screen_height didn't match the calibration's recorded dimensions --
    # distinct from gaze_model_trained=False for a poor-quality calibration,
    # since the fix is "use the same screen you calibrated on", not
    # "recalibrate with better lighting". See session_routes.link_calibration.
    screen_mismatch: bool = False
    calibration: Optional[Dict[str, Any]] = None
    gaze_model_metrics: Optional[Dict[str, Any]] = None
    message: str


class GazePointInput(BaseModel):
    """One estimated gaze point, normalised [0,1] screen coordinates.

    Matches the GazePoint that backend/gaze_estimation emits. Invalid points
    (blinks) should be SENT, not filtered -- backend/attribution needs the gap
    to distinguish a blink from a glance away.
    """

    timestamp: float
    x: float
    y: float
    valid: bool = True
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    # Page scroll position when this point was captured, in CSS pixels.
    # REQUIRED for scrollable pages: gaze is viewport-relative, the layout of
    # a long page is document-relative, and without this the two can't be
    # reconciled -- every point lands on the first screen and the rest of the
    # page reads as ignored. Omit (or 0) for pages that don't scroll.
    scroll_x: float = Field(0.0, ge=0.0)
    scroll_y: float = Field(0.0, ge=0.0)


class GazeBatchRequest(BaseModel):
    gaze: List[GazePointInput] = Field(..., min_length=1, max_length=20_000)


class GazeBatchResponse(BaseModel):
    session_id: str
    accepted: int
    total_points: int
    status: str


class StageRect(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)


class GazeFrameRequest(BaseModel):
    """One webcam frame for the live session loop -- see pipeline.estimate_gaze_frame."""

    frame: str = Field(..., description="base64 JPEG, raw or a data: URL")
    timestamp: Optional[float] = None
    stage: Optional[StageRect] = Field(
        None,
        description="Where the evaluated page is drawn, as a fraction of the "
                    "viewport. The gaze model maps to the VIEWPORT (that is what "
                    "calibration targets were measured in); when the page sits "
                    "inside a smaller stage, gaze is remapped into it.",
    )
    # How far the page inside the stage was scrolled when this frame was
    # taken, in the captured page's CSS pixels. Needed for URL sessions on
    # long pages -- see GazePointInput.scroll_y and pipeline.to_document_space.
    scroll_x: float = Field(0.0, ge=0.0)
    scroll_y: float = Field(0.0, ge=0.0)


class GazeFrameResponse(BaseModel):
    session_id: str
    gaze: Dict[str, Any]   # the GazePoint dict, stored verbatim in the stream
    status: str


class FinalizeResponse(BaseModel):
    session_id: str
    status: str
    message: str


class ReportResponse(BaseModel):
    """The agent chain's output, unreshaped.

    `pipeline_result` is exactly what agents/orchestrator.run_pipeline()
    returned -- behavior_summary, issues, recommendations_kept,
    recommendations_rejected. Not flattened or renamed: backend/reports
    already consumes that shape, and a second shape here would be one more
    thing to keep in sync for no gain.
    """

    session_id: str
    report_id: str
    status: str
    ui_page: Optional[str] = None
    target_url: Optional[str] = None

    pipeline_result: Dict[str, Any]
    metrics: Dict[str, Any]

    html_path: Optional[str] = None
    pdf_path: Optional[str] = None
    heatmap_path: Optional[str] = None
    scanpath_path: Optional[str] = None
    pdf_backend: Optional[str] = None

    layout_is_placeholder: bool = False
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime


class ReportPendingResponse(BaseModel):
    """Returned with 202 while the pipeline hasn't produced a report yet."""

    session_id: str
    status: str
    ready: bool = False
    message: str
    next_action: Optional[str] = None


class TestUIsResponse(BaseModel):
    ui_pages: List[str]
    note: str


TokenResponse.model_rebuild()

__all__ = [
    "SignupRequest",
    "LoginRequest",
    "TokenResponse",
    "UserResponse",
    "CreateSessionRequest",
    "SessionResponse",
    "SessionListResponse",
    "SessionDetailResponse",
    "CalibrationLinkRequest",
    "CalibrationLinkResponse",
    "GazePointInput",
    "GazeBatchRequest",
    "GazeBatchResponse",
    "GazeFrameRequest",
    "GazeFrameResponse",
    "FinalizeResponse",
    "ReportResponse",
    "ReportPendingResponse",
    "TestUIsResponse",
    "SESSION_STATUSES",
]
