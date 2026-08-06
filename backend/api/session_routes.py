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
    DELETE /api/sessions/{id}               discard
    GET    /api/sessions/meta/test-uis      available test pages

Every route depends on get_current_user, and every lookup goes through
deps.owned_session, so a session belonging to another user is a 404 -- see
deps.py for why 404 and not 403.

Finalising runs in a BackgroundTask: the chain ends in a Chromium PDF render
that takes seconds, and holding the request open for it would time out the
browser and give the frontend nothing to show. The session goes to
"processing" immediately and /report answers 202 until it's done.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from . import pipeline
from .db import DATA_DIR, SessionLocal, get_db
from .deps import get_current_user, owned_session
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
    ReportPendingResponse,
    ReportResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    TestUIsResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _next_action(session: SessionModel) -> str:
    """What the client should do next.

    Returned so the live-session UI doesn't have to reimplement this status
    machine to decide between "calibrate" and "record" -- two copies of that
    logic would drift the first time a status is added.
    """
    if session.status == STATUS_FAILED:
        return "restart"
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
    data.has_report = session.report is not None
    return data


# ----------------------------------------------------------------------


@router.get("/meta/test-uis", response_model=TestUIsResponse)
async def list_test_uis(_: User = Depends(get_current_user)) -> TestUIsResponse:
    """Which ui_page values a test_ui session can use."""
    return TestUIsResponse(
        ui_pages=list(AVAILABLE_TEST_UIS),
        note="Interim layouts in backend/api/layouts.py. The real element "
             "configs belong with the pages in test_uis/ (separate task).",
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

    capture_meta = None

    if payload.mode == MODE_URL:
        # Screenshot the page and auto-detect its elements via backend/render.
        # Done inline rather than in the background because the session cannot
        # proceed without a layout, and the client is already showing a
        # spinner on "start session".
        capture = pipeline.capture_page(payload.target_url)

        if capture.get("ok"):
            ui_page = "captured_page"
            layout = capture["layout"]
            is_placeholder = False
            capture_meta = {
                k: capture.get(k) for k in
                ("final_url", "title", "detected", "kept",
                 "low_confidence_fraction", "classification", "warnings",
                 "screenshot_path")
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
    detail = SessionDetailResponse.model_validate(session)
    detail.has_report = session.report is not None
    detail.calibration = pipeline.calibration_summary(session.calibration_session_id)
    detail.element_layout = session.element_layout
    detail.next_action = _next_action(session)
    return detail


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
    message = "calibration linked"
    if payload.train_model:
        ok, metrics, detail = pipeline.train_gaze_model(payload.calibration_session_id)
        session.gaze_model_trained = ok
        message = f"calibration linked; gaze model {detail}"
        if not ok:
            # Not fatal: a poor calibration is a real study outcome and the
            # participant can recalibrate without losing the session record.
            session.error = detail

    db.commit()
    db.refresh(session)

    return CalibrationLinkResponse(
        session_id=session.id,
        calibration_session_id=payload.calibration_session_id,
        status=session.status,
        gaze_model_trained=session.gaze_model_trained,
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
        try:
            gaze = pipeline.read_gaze(Path(session.gaze_path))
            result = pipeline.analyse_session(
                session_id=session.id,
                gaze_points=gaze,
                layout=session.element_layout or {},
                ui_page=session.ui_page or "unknown_page",
                output_dir=Path(DATA_DIR) / session.id,
            )

            db.add(Report(
                session_id=session.id,
                pipeline_result=result["pipeline_result"],
                metrics=result["metrics"],
                html_path=result["html_path"],
                pdf_path=result["pdf_path"],
                heatmap_path=result["heatmap_path"],
                pdf_backend=result["pdf_backend"],
            ))
            session.status = STATUS_COMPLETE
            session.completed_at = datetime.now(timezone.utc)
            session.error = result.get("render_error")
        except Exception as exc:            # noqa: BLE001
            # The status must always land somewhere terminal. A session stuck
            # on "processing" forever is worse than one that says why it
            # failed -- the dashboard would poll it indefinitely.
            session.status = STATUS_FAILED
            session.error = f"{type(exc).__name__}: {exc}"
            session.completed_at = datetime.now(timezone.utc)
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
    """Run the analysis chain. Returns immediately; poll the session or report."""
    session = owned_session(session_id, user, db)

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
        pipeline_result=report.pipeline_result,
        metrics=report.metrics,
        html_path=report.html_path,
        pdf_path=report.pdf_path,
        heatmap_path=report.heatmap_path,
        pdf_backend=report.pdf_backend,
        layout_is_placeholder=session.layout_is_placeholder,
        warnings=warnings,
        created_at=report.created_at,
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
