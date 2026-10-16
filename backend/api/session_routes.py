"""
session_routes.py

The session lifecycle, and the only place the whole pipeline is driven.

    POST   /api/sessions                    start
    GET    /api/sessions                    list (paginated, filterable)
    GET    /api/sessions/{id}               status + metadata
    POST   /api/sessions/{id}/calibration   attach calibration, train gaze model
    POST   /api/sessions/{id}/gaze          append a batch of gaze points
    POST   /api/sessions/{id}/finalize      run attribution -> agents -> report
    GET    /api/sessions/{id}/report        the report, or 202 while pending
    GET    /api/sessions/{id}/heatmap       the report's heatmap image
    GET    /api/sessions/{id}/scanpath      the report's gaze-path image
    GET    /api/sessions/{id}/pdf           the report's rendered PDF
    DELETE /api/sessions/{id}               discard
    GET    /api/sessions/meta/test-uis      available test pages

Every route depends on get_current_user, and every lookup goes through
deps.owned_session, so a session belonging to another user is a 404 -- see
deps.py for why 404 and not 403.

Finalising runs in a BackgroundTask: the chain ends in a Chromium PDF render
that takes seconds, and holding the request open for it would time out the
browser and give the frontend nothing to show. The session goes to
"processing" immediately and /report answers 202 until it's done.

A BackgroundTask lives in the worker process, so if that process dies
mid-analysis (a native crash, a restart, --reload) nothing is left to mark the
session failed. Two things make that self-healing: startup marks every
leftover "processing" session failed (recover_interrupted_sessions, called
from main.lifespan), and any read of a session that has been processing for
longer than ANALYSIS_TIMEOUT_SECONDS marks it failed there and then
(expire_if_stale). A failed session can be finalised again -- the gaze stream
is still on disk -- so the participant never has to recalibrate or re-record.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from . import pipeline
from .db import DATA_DIR, SessionLocal, get_db
from .deps import get_current_user, owned_calibration, owned_session
from .layouts import AVAILABLE_TEST_UIS, UnknownTestUI, layout_for
from .models import (
    MODE_URL,
    STATUS_CALIBRATED,
    STATUS_COMPLETE,
    STATUS_CREATED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_RECORDING,
    Report,
    Session as SessionModel,
    User,
)
from .schemas import (
    CalibrationLinkRequest,
    CalibrationLinkResponse,
    CreateSessionRequest,
    FinalizeResponse,
    GazeBatchRequest,
    GazeBatchResponse,
    GazeFrameRequest,
    GazeFrameResponse,
    ReportPendingResponse,
    ReportResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    TestUIsResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# How long an analysis may run before a read treats it as dead. A normal run
# is well under a minute (the PDF render dominates); ten minutes leaves room
# for LLM mode on a slow network without leaving a crashed run spinning for
# long. Seconds, so the tests can set it small.
ANALYSIS_TIMEOUT_SECONDS = float(os.environ.get("GAZELENS_ANALYSIS_TIMEOUT_SECONDS", "600"))

INTERRUPTED_ERROR = ("analysis was interrupted before it finished (the server "
                     "restarted or crashed); please retry")
TIMED_OUT_ERROR = "analysis did not finish within {minutes:g} minutes; please retry"


def _as_utc(value: datetime) -> datetime:
    # SQLite hands DateTime(timezone=True) back naive; every value written
    # here is UTC, so that is what a naive one means.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _mark_failed(session: SessionModel, error: str) -> None:
    session.status = STATUS_FAILED
    session.error = error
    session.completed_at = datetime.now(timezone.utc)


def recover_interrupted_sessions(db: DBSession) -> int:
    """Fail every session left on "processing". Called once at startup.

    At startup no analysis can be running -- they are BackgroundTasks in this
    process, and this process has only just started -- so every such session
    was abandoned by a previous one. Assumes a single worker, which is how
    the Dockerfile and the dev command run it; with several workers, one
    starting up would fail another's in-flight run.
    """
    stuck = db.query(SessionModel).filter(SessionModel.status == STATUS_PROCESSING).all()
    for session in stuck:
        _mark_failed(session, INTERRUPTED_ERROR)
    if stuck:
        db.commit()
    return len(stuck)


def expire_if_stale(session: SessionModel, db: DBSession) -> bool:
    """Fail a session that has been processing for longer than the timeout.

    The startup sweep covers restarts; this covers a run that hung, or a
    deployment that recycles workers without a clean startup. True if the
    session was changed.
    """
    if session.status != STATUS_PROCESSING:
        return False
    started = session.processing_started_at
    if started is not None:
        elapsed = (datetime.now(timezone.utc) - _as_utc(started)).total_seconds()
        if elapsed <= ANALYSIS_TIMEOUT_SECONDS:
            return False
    # started is None: processing since before the column existed, so it
    # can't be a run this process knows about.
    _mark_failed(session, TIMED_OUT_ERROR.format(minutes=ANALYSIS_TIMEOUT_SECONDS / 60))
    db.commit()
    return True


def _next_action(session: SessionModel) -> str:
    """What the client should do next.

    Returned so the live-session UI doesn't have to reimplement this status
    machine to decide between "calibrate" and "record" -- two copies of that
    logic would drift the first time a status is added.
    """
    if session.status == STATUS_FAILED:
        # The gaze stream survives a failed analysis, so finalising again is
        # enough; only a session with nothing recorded needs starting over.
        return "retry" if session.gaze_point_count > 0 else "restart"
    if session.status == STATUS_COMPLETE:
        return "view_report"
    if session.status == STATUS_PROCESSING:
        return "wait"
    if not session.calibration_session_id:
        return "calibrate"
    if not session.gaze_model_trained:
        return "train_gaze_model"
    if session.gaze_point_count == 0:
        return "record"
    return "finalize"


def _to_response(session: SessionModel) -> SessionResponse:
    data = SessionResponse.model_validate(session)
    report = session.report
    data.has_report = report is not None
    if report is not None:
        issues = (report.pipeline_result or {}).get("issues", [])
        data.issue_count = len(issues)
        data.high_issue_count = sum(1 for i in issues if i.get("severity") == "High")
    return data


# ----------------------------------------------------------------------


@router.get("/meta/test-uis", response_model=TestUIsResponse)
async def list_test_uis(_: User = Depends(get_current_user)) -> TestUIsResponse:
    """Which ui_page values a test_ui session can use."""
    return TestUIsResponse(
        ui_pages=list(AVAILABLE_TEST_UIS),
        note="Served from test_uis/<ui_page>/index.html, elements from the "
             "matching elements.json next to it.",
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    """Create a session and resolve the element layout it will be scored against."""
    try:
        payload.validate_combination()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if payload.calibration_session_id:
        # Checked up front, not just on /calibration: a session row naming a
        # calibration is what makes a legacy (ownerless) one reachable, so
        # an unchecked id here would let anyone claim it.
        owned_calibration(payload.calibration_session_id, user, db)

    capture_meta = None

    if payload.mode == MODE_URL:
        # Screenshot the page and auto-detect its elements via backend/render.
        # Done inline rather than in the background because the session cannot
        # proceed without a layout, and the client is already showing a
        # spinner on "start session".
        # Kept so the report's heatmap can be drawn over the real page.
        shot = DATA_DIR / "captures" / f"{uuid.uuid4().hex}.png"
        capture = pipeline.capture_page(payload.target_url, screenshot_path=shot)

        if capture.get("ok"):
            ui_page = "captured_page"
            layout = pipeline.label_captured_layout(
                capture["layout"], capture.get("classification"))
            is_placeholder = False
            capture_meta = {
                k: capture.get(k) for k in
                ("final_url", "title", "detected", "kept",
                 "low_confidence_fraction", "classification", "warnings",
                 "screenshot_path",
                 # These three drive pipeline.to_document_space -- gaze can't
                 # be reconciled with the layout without them.
                 "scope", "viewport", "document_size", "page_screens")
            }
        else:
            # Falling back rather than failing: a page behind a consent wall
            # or a slow network shouldn't stop a participant being run. The
            # session is flagged so the report says the boxes aren't real.
            ui_page, layout, is_placeholder = layout_for(MODE_URL, None, payload.target_url)
            capture_meta = {"capture_failed": True, "reason": capture.get("reason")}
    else:
        try:
            ui_page, layout, is_placeholder = layout_for(
                payload.mode, payload.ui_page, payload.target_url
            )
        except UnknownTestUI as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    session = SessionModel(
        user_id=user.id,
        mode=payload.mode,
        ui_page=ui_page,
        target_url=payload.target_url,
        label=payload.label,
        status=STATUS_CREATED,
        calibration_session_id=payload.calibration_session_id,
        element_layout=layout,
        layout_is_placeholder=is_placeholder,
        capture_meta=capture_meta,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_response(session)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionListResponse:
    """This user's sessions, newest first. Never anyone else's."""
    query = db.query(SessionModel).filter(SessionModel.user_id == user.id)
    if status_filter:
        query = query.filter(SessionModel.status == status_filter)

    # Counted before pagination so the dashboard can render "showing 20 of
    # 137" rather than only knowing about the page it fetched.
    total = query.with_entities(func.count(SessionModel.id)).scalar() or 0
    rows = (
        query.order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    for row in rows:
        expire_if_stale(row, db)
    return SessionListResponse(
        sessions=[_to_response(s) for s in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionDetailResponse:
    session = owned_session(session_id, user, db)
    expire_if_stale(session, db)
    detail = SessionDetailResponse.model_validate(session)
    detail.has_report = session.report is not None
    detail.calibration = pipeline.calibration_summary(session.calibration_session_id)
    detail.element_layout = session.element_layout
    detail.next_action = _next_action(session)
    return detail


# How far apart current and calibration-time screen dimensions can be before
# refusing to link, as a fraction of the calibration's own size. Not zero --
# a scrollbar appearing/disappearing or a pixel of browser-chrome rounding
# shouldn't force a recalibration -- but small enough that it only absorbs
# that kind of noise, not an actually different window or monitor. Chosen,
# not measured: there's no real-participant error data yet to tune this
# against (see OPEN_ITEMS.md #2), so it stays conservative until there is.
SCREEN_MATCH_TOLERANCE = 0.02


def _screen_mismatch(
    calibration_width: int, calibration_height: int,
    current_width: Optional[int], current_height: Optional[int],
) -> bool:
    """True if the live session's screen is meaningfully different from the
    one the calibration was recorded on.

    Deliberately a yes/no check, not a correction: the gaze mapping is
    trained on this specific screen's geometry (see CalibrationLinkRequest's
    docstring), and there's no reliable way to convert that to a different
    screen size without either asking the participant for physical
    measurements or guessing camera intrinsics -- both worse than just
    requiring a recalibration.
    """
    if current_width is None or current_height is None:
        # Caller didn't supply it -- nothing to compare against, so this
        # check simply doesn't apply rather than assuming a mismatch.
        return False
    dw = abs(current_width - calibration_width) / calibration_width
    dh = abs(current_height - calibration_height) / calibration_height
    return dw > SCREEN_MATCH_TOLERANCE or dh > SCREEN_MATCH_TOLERANCE


@router.post("/{session_id}/calibration", response_model=CalibrationLinkResponse)
async def link_calibration(
    session_id: str,
    payload: CalibrationLinkRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> CalibrationLinkResponse:
    """Attach a completed calibration session and fit its gaze model.

    The calibration itself is collected by backend/calibration's own
    endpoints; this only links the result to a session and triggers training,
    so the two modules stay independently usable.
    """
    session = owned_session(session_id, user, db)
    if session.status in (STATUS_PROCESSING, STATUS_COMPLETE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session is already {session.status}",
        )

    # Only the caller's own calibration: linking someone else's would hand
    # this session (and its report) their eye data.
    owned_calibration(payload.calibration_session_id, user, db)
    summary = pipeline.calibration_summary(payload.calibration_session_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no calibration session {payload.calibration_session_id!r} -- "
                   f"collect it via /api/calibration first",
        )

    session.calibration_session_id = payload.calibration_session_id
    session.status = STATUS_CALIBRATED
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)

    metrics = None
    screen_mismatch = _screen_mismatch(
        summary["screen_width"], summary["screen_height"],
        payload.screen_width, payload.screen_height,
    )

    if screen_mismatch:
        # Refuse before spending a training run on a mapping we're about to
        # reject anyway -- same reasoning as skipping training on a
        # session that's already processing/complete above.
        session.gaze_model_trained = False
        message = (
            f"screen size changed since calibration ({summary['screen_width']}x"
            f"{summary['screen_height']} -> {payload.screen_width}x{payload.screen_height}); "
            f"recalibrate on this screen before starting a session"
        )
        session.error = message
    elif payload.train_model:
        ok, metrics, detail = pipeline.train_gaze_model(payload.calibration_session_id)
        session.gaze_model_trained = ok
        message = f"calibration linked; gaze model {detail}"
        if not ok:
            # Not fatal: a poor calibration is a real study outcome and the
            # participant can recalibrate without losing the session record.
            session.error = detail
    else:
        message = "calibration linked"

    db.commit()
    db.refresh(session)

    return CalibrationLinkResponse(
        session_id=session.id,
        calibration_session_id=payload.calibration_session_id,
        status=session.status,
        gaze_model_trained=session.gaze_model_trained,
        screen_mismatch=screen_mismatch,
        calibration=summary,
        gaze_model_metrics=metrics,
        message=message,
    )


@router.post("/{session_id}/gaze", response_model=GazeBatchResponse)
async def append_gaze(
    session_id: str,
    payload: GazeBatchRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> GazeBatchResponse:
    """Append a batch of estimated gaze points to the session's stream.

    Batched rather than one request per frame: at 30Hz that would be 1800
    requests a minute per participant. Invalid points should be included --
    backend/attribution needs the gaps.
    """
    session = owned_session(session_id, user, db)
    if session.status in (STATUS_PROCESSING, STATUS_COMPLETE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session is already {session.status}; gaze can no longer be added",
        )

    path = pipeline.gaze_path_for(DATA_DIR, session.id)
    accepted = pipeline.append_gaze(path, [p.model_dump() for p in payload.gaze])

    session.gaze_path = str(path)
    session.gaze_point_count += accepted
    session.status = STATUS_RECORDING
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
    db.commit()

    return GazeBatchResponse(
        session_id=session.id,
        accepted=accepted,
        total_points=session.gaze_point_count,
        status=session.status,
    )


@router.post("/{session_id}/gaze/frame", response_model=GazeFrameResponse)
def estimate_gaze_frame(
    session_id: str,
    payload: GazeFrameRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> GazeFrameResponse:
    """One webcam frame -> one on-screen gaze point, appended to the stream.

    Added for the live-session UI: browser JS can't run the pupil detector
    itself, so a frame has to be sent to the server and turned into a screen
    coordinate there. See pipeline.estimate_gaze_frame for why this
    composition (cv -> gaze_estimation) didn't already exist as one call.

    The point is appended to this session's gaze stream immediately -- same
    file /gaze writes to -- so the client doesn't also need to call /gaze
    itself; this endpoint IS the live gaze stream for a browser-driven
    session. Returned too, so the client can draw the cursor without a
    second round trip.

    A plain `def` on purpose: frame decoding, landmarking and inference are
    blocking CPU work. As `async def` they ran on the event loop, so every
    other request -- including the next frame -- queued behind them and the
    cursor lagged further the longer a session ran. FastAPI runs sync
    handlers in its threadpool.
    """
    session = owned_session(session_id, user, db)
    if session.status in (STATUS_PROCESSING, STATUS_COMPLETE):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session is already {session.status}; gaze can no longer be added",
        )
    if not session.calibration_session_id or not session.gaze_model_trained:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session has no trained gaze model -- "
                   "POST /api/sessions/{id}/calibration first",
        )

    try:
        point = pipeline.estimate_gaze_frame(
            session.calibration_session_id, payload.frame, timestamp=payload.timestamp,
            stage=payload.stage.model_dump() if payload.stage else None,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no trained gaze model for this session's calibration: {exc}",
        ) from exc

    if payload.scroll_x or payload.scroll_y:
        point["scroll_x"] = payload.scroll_x
        point["scroll_y"] = payload.scroll_y

    path = pipeline.gaze_path_for(DATA_DIR, session.id)
    pipeline.append_gaze(path, [point])

    session.gaze_path = str(path)
    session.gaze_point_count += 1
    session.status = STATUS_RECORDING
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
    db.commit()

    return GazeFrameResponse(session_id=session.id, gaze=point, status=session.status)


def _run_analysis(session_id: str) -> None:
    """Background worker: analyse the session and store its report.

    Opens its own DB session -- the request's Session is closed by the time a
    BackgroundTask runs, so reusing it would raise on first access.
    """
    db = SessionLocal()
    try:
        session = db.get(SessionModel, session_id)
        if session is None:
            return
        started_at = session.processing_started_at
        try:
            gaze = pipeline.read_gaze(Path(session.gaze_path))
            result = pipeline.analyse_session(
                session_id=session.id,
                gaze_points=gaze,
                layout=session.element_layout or {},
                ui_page=session.ui_page or "unknown_page",
                output_dir=Path(DATA_DIR) / session.id,
                capture_meta=session.capture_meta,
                calibration_session_id=session.calibration_session_id,
            )

            db.refresh(session)
            if session.report is not None or session.processing_started_at != started_at:
                # A newer run owns this session: this one was timed out and
                # retried while it was still going, and the retry got there
                # first (or is still going). Writing a second report would
                # break the one-report-per-session constraint.
                return
            db.add(Report(
                session_id=session.id,
                pipeline_result=result["pipeline_result"],
                metrics=result["metrics"],
                html_path=result["html_path"],
                pdf_path=result["pdf_path"],
                heatmap_path=result["heatmap_path"],
                scanpath_path=result["scanpath_path"],
                pdf_backend=result["pdf_backend"],
            ))
            session.status = STATUS_COMPLETE
            session.completed_at = datetime.now(timezone.utc)
            session.error = result.get("render_error")
        except Exception as exc:            # noqa: BLE001
            # The status must always land somewhere terminal. A session stuck
            # on "processing" forever is worse than one that says why it
            # failed -- the dashboard would poll it indefinitely.
            db.rollback()
            db.refresh(session)
            if session.processing_started_at != started_at:
                return                      # superseded by a retry, as above
            _mark_failed(session, f"{type(exc).__name__}: {exc}")
        db.commit()
    finally:
        db.close()


@router.post("/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session(
    session_id: str,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> FinalizeResponse:
    """Run the analysis chain. Returns immediately; poll the session or report.

    Also the retry: a failed session (crash, restart, timeout, pipeline
    error) is finalised again from the gaze stream already on disk.
    """
    session = owned_session(session_id, user, db)
    expire_if_stale(session, db)

    if session.status == STATUS_PROCESSING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="session is already being processed")
    if session.report is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="session already has a report")
    if session.gaze_point_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no gaze data -- POST to /gaze before finalising",
        )

    session.status = STATUS_PROCESSING
    session.error = None
    session.completed_at = None
    session.processing_started_at = datetime.now(timezone.utc)
    db.commit()

    background.add_task(_run_analysis, session.id)
    return FinalizeResponse(
        session_id=session.id,
        status=STATUS_PROCESSING,
        message="analysis started; poll GET /api/sessions/{id}/report",
    )


@router.get("/{session_id}/report",
            response_model=None,
            responses={200: {"model": ReportResponse},
                       202: {"model": ReportPendingResponse}})
async def get_report(
    session_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """The report, or 202 + status while the pipeline is still running.

    202 rather than 404 for a pending report: the resource will exist, and a
    404 would tell a polling dashboard to give up.
    """
    session = owned_session(session_id, user, db)
    expire_if_stale(session, db)
    report = session.report

    if report is None:
        response.status_code = status.HTTP_202_ACCEPTED
        if session.status == STATUS_FAILED:
            message = f"analysis failed: {session.error or 'unknown error'}"
        elif session.status == STATUS_PROCESSING:
            message = "analysis in progress"
        else:
            message = "no report yet -- finalise the session first"
        return ReportPendingResponse(
            session_id=session.id,
            status=session.status,
            ready=False,
            message=message,
            next_action=_next_action(session),
        )

    warnings = []
    meta = session.capture_meta or {}
    if session.layout_is_placeholder:
        reason = meta.get("reason")
        warnings.append(
            "Element boxes are a PLACEHOLDER, not detected from the page"
            + (f" ({reason})" if reason else "")
            + ". Per-element metrics in this report do not describe real UI elements."
        )
    elif session.mode == MODE_URL:
        # Auto-detected labels are heuristics over tags and class names, not
        # design intent. A reader comparing this to a hand-authored test_uis
        # report needs to know which one they're holding.
        low = meta.get("low_confidence_fraction")
        warnings.append(
            "Element types were auto-detected from the page, not authored by "
            "a designer"
            + (f"; {low:.0%} were inferred from class names or geometry rather "
               f"than tags" if isinstance(low, (int, float)) else "")
            + ". Treat per-element findings as provisional."
        )
        warnings.extend(meta.get("warnings") or [])
    if session.error:
        warnings.append(session.error)

    return ReportResponse(
        session_id=session.id,
        report_id=report.id,
        status=session.status,
        ui_page=session.ui_page,
        target_url=session.target_url,
        pipeline_result=report.pipeline_result,
        metrics=report.metrics,
        html_path=report.html_path,
        pdf_path=report.pdf_path,
        heatmap_path=report.heatmap_path,
        scanpath_path=report.scanpath_path,
        pdf_backend=report.pdf_backend,
        layout_is_placeholder=session.layout_is_placeholder,
        warnings=warnings,
        created_at=report.created_at,
    )


def _report_file(
    session_id: str, user: User, db: DBSession, attr: str, media_type: str, filename: Optional[str] = None
) -> FileResponse:
    """Shared body for /heatmap, /scanpath and /pdf -- same file, different column.

    Not a static mount: session_data/ holds every user's session files in
    one directory, and StaticFiles has no concept of ownership. Every other
    piece of a session's data goes through owned_session (404, not 403, for
    someone else's session -- see deps.py); an unauthenticated file mount
    would quietly carve an exception into that for exactly the artifacts a
    usability report is most likely to be screenshotted and shared. Routing
    through here keeps the same rule for these files.

    An <img src>/download link can't carry an Authorization header, so the
    frontend fetches this with a bearer token and turns the response into an
    object URL -- see client.js's getSessionImage / downloadSessionPdf.
    """
    session = owned_session(session_id, user, db)
    report = session.report
    path = getattr(report, attr, None) if report else None
    if not path or not Path(path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no {attr.replace('_path', '')} for this session",
        )
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/{session_id}/heatmap")
async def get_heatmap_image(
    session_id: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> FileResponse:
    return _report_file(session_id, user, db, "heatmap_path", "image/png")


@router.get("/{session_id}/scanpath")
async def get_scanpath_image(
    session_id: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> FileResponse:
    return _report_file(session_id, user, db, "scanpath_path", "image/png")


@router.get("/{session_id}/pdf")
async def get_report_pdf(
    session_id: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> FileResponse:
    """The rendered PDF report. 404 if WeasyPrint wasn't available at render
    time (report.pdf_path is None then) -- html_path/pdf_backend on the
    report response tells the caller the HTML version still exists.
    """
    return _report_file(
        session_id, user, db, "pdf_path", "application/pdf", filename=f"gazelens-report-{session_id}.pdf"
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> None:
    session = owned_session(session_id, user, db)
    # The report row cascades; the gaze file has to go explicitly since the
    # DB knows nothing about the filesystem.
    if session.gaze_path:
        Path(session.gaze_path).unlink(missing_ok=True)
    db.delete(session)
    db.commit()


__all__ = ["router"]
