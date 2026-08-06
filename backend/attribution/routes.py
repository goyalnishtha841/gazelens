"""
routes.py

FastAPI router for gaze-to-UI attribution.

    POST /api/attribution/analyze     gaze stream + element boxes -> SessionMetrics
    GET  /api/attribution/defaults    the thresholds in force

Thin, same as backend/calibration and backend/gaze_estimation: validate,
delegate to engine.analyze_session, respond.

A NOTE ON HOW THIS IS MEANT TO BE CALLED
----------------------------------------
A live session should call `attribution.analyze_session()` IN-PROCESS, not
over HTTP. The gaze stream already exists in the server's memory; posting
tens of thousands of points back to the same process to have them counted
would be pure overhead. This endpoint exists for the frontend, for
re-analysing a stored session with different thresholds, and for letting the
module be exercised independently -- which is also why the thresholds are
request parameters rather than constants.
"""

from fastapi import APIRouter, HTTPException, status

from .elements import ElementConfigError, build_ui_config
from .engine import analyze_session
from .fixations import (
    DISPERSION_THRESHOLD,
    MAX_GAP,
    MIN_FIXATION_DURATION,
    SMOOTHING_WINDOW,
    GazeSample,
)
from .elements import ELEMENT_TYPES, IMPORTANCE_VALUES
from .schemas import AnalyzeRequest, AnalyzeResponse, DefaultsResponse

router = APIRouter(prefix="/api/attribution", tags=["attribution"])


@router.get("/defaults", response_model=DefaultsResponse)
async def defaults() -> DefaultsResponse:
    """The thresholds a result was produced under.

    Exposed because every number this module emits depends on them, and a
    metric quoted without its threshold isn't reproducible.
    """
    return DefaultsResponse(
        min_fixation_duration=MIN_FIXATION_DURATION,
        dispersion_threshold=DISPERSION_THRESHOLD,
        max_gap=MAX_GAP,
        smoothing_window=SMOOTHING_WINDOW,
        importance_values=list(IMPORTANCE_VALUES),
        element_types=list(ELEMENT_TYPES),
        notes={
            "dispersion": (
                "I-DT dispersion is (x-range + y-range) over the fixation, applied "
                "to smoothed gaze. It scales with the RANGE of gaze error (~8 sigma "
                "for a short fixation), not with sigma itself."
            ),
            "smoothing": (
                "Applied here rather than upstream: backend/gaze_estimation leaves "
                "its stream raw by design, because smoothing shortens saccades and "
                "stretches fixations -- the very things this module measures."
            ),
            "background": (
                "Gaze outside every element is attributed to no element but still "
                "counts toward total_gaze_time, which is what SessionMetrics."
                "dwell_pct divides by."
            ),
            "ttff": (
                "Elements never fixated are omitted from ttff (not zero, not "
                "infinity) -- agent1 computes first_noticed as min(ttff)."
            ),
        },
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Gaze stream + element bounding boxes -> the agents' SessionMetrics."""
    try:
        ui_config = build_ui_config(
            ui_page=payload.ui_page,
            elements={eid: spec.as_spec() for eid, spec in payload.elements.items()},
            viewport=payload.viewport,
            priority=payload.priority,
        )
    except ElementConfigError as exc:
        # 422, not 500: the request was well-formed JSON, the layout just
        # doesn't describe anything gaze can be attributed to.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if payload.priority:
        unknown = sorted(set(payload.priority) - set(ui_config.element_ids))
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"priority names elements not in the layout: {unknown}",
            )

    samples = [
        GazeSample(
            timestamp=g.timestamp, x=g.x, y=g.y,
            valid=g.valid, confidence=g.confidence,
        )
        for g in payload.gaze
    ]

    report = analyze_session(
        samples,
        ui_config,
        session_id=payload.session_id,
        min_fixation_duration=payload.min_fixation_duration,
        dispersion_threshold=payload.dispersion_threshold,
        max_gap=payload.max_gap,
        smoothing_window=payload.smoothing_window,
    )

    payload_out = report.to_dict()
    return AnalyzeResponse(
        metrics=payload_out["metrics"],
        diagnostics=payload_out["diagnostics"],
        heatmap_layout=ui_config.layout_for_heatmap(),
    )


__all__ = ["router"]
