"""
routes.py

FastAPI router for gaze estimation.

    POST   /api/gaze/models/{session_id}/train       fit from calibration data
    GET    /api/gaze/models/{session_id}             model info + held-out error
    GET    /api/gaze/models                          list trained models
    DELETE /api/gaze/models/{session_id}             discard
    POST   /api/gaze/models/{session_id}/estimate    one frame -> one GazePoint
    POST   /api/gaze/models/{session_id}/estimate/batch   a burst of frames

Thin, same as backend/calibration/routes.py: validate, delegate, respond.

Note on the estimate endpoints: they take PUPIL COORDINATES, not frames.
This module never touches webcam data -- backend/cv turns frames into pupil
positions, and this turns pupil positions into screen positions. For a real
live session the two are better composed in-process (see estimator.
estimate_frame_result) than over HTTP; these endpoints exist so the flow is
callable from the frontend and testable in isolation.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from calibration.storage import SessionNotFound

from .estimator import clear_estimator, get_estimator
from .features import InsufficientCalibrationData
from .schemas import (
    EstimateBatchRequest,
    EstimateBatchResponse,
    EstimateRequest,
    EstimateResponse,
    GazePointModel,
    ModelSummary,
    TrainRequest,
    TrainResponse,
)
from .training import (
    POOR_FIT_PX_FRACTION,
    delete_model,
    has_model,
    list_models,
    load_model,
    train_session,
)

router = APIRouter(prefix="/api/gaze", tags=["gaze estimation"])


def _estimator(session_id: str, smoothing: float = 0.0):
    try:
        return get_estimator(session_id, smoothing=smoothing)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no trained gaze model for session {session_id!r}. "
                f"POST /api/gaze/models/{session_id}/train first."
            ),
        ) from exc


def _to_pupil(p):
    return (p.x, p.y) if p is not None else None


# ----------------------------------------------------------------------


@router.post("/models/{session_id}/train", response_model=TrainResponse)
async def train(
    session_id: str, payload: Optional[TrainRequest] = None
) -> TrainResponse:
    """Fit a per-session gaze model from that session's calibration data.

    Per session, per sitting: the pupil-to-screen mapping depends on head
    position, seating distance, lighting and camera angle, none of which
    survive a change of participant or setup.

    The body is optional -- training with no arguments is the common case.
    Defaulted here rather than in the signature: a `TrainRequest()` default
    would build one instance at import time and share it across every request,
    which is a mutable process-wide object masquerading as a per-call default.
    """
    payload = payload or TrainRequest()
    try:
        result = train_session(
            session_id,
            min_confidence=payload.min_confidence,
            viewing_distance_cm=payload.viewing_distance_cm,
            screen_diagonal_in=payload.screen_diagonal_in,
            feature_set=payload.feature_set,
            degree=payload.degree,
        )
    except SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no calibration session {session_id!r} -- calibrate first",
        ) from exc
    except InsufficientCalibrationData as exc:
        # 422 rather than 500: the request was well-formed, the stored
        # calibration just isn't good enough to fit anything on.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # A retrained session must not keep serving the old model from cache.
    clear_estimator(session_id)

    model = result.model
    diagonal = (model.screen_width ** 2 + model.screen_height ** 2) ** 0.5
    usable = result.median_error_px <= POOR_FIT_PX_FRACTION * diagonal

    return TrainResponse(
        session_id=model.session_id,
        participant_id=model.participant_id,
        n_points=model.n_points,
        n_samples=model.n_samples,
        selection=result.selection,
        metrics=result.metrics,
        training_metrics=result.training_metrics,
        model_path=str(result.model_path) if result.model_path else None,
        trained_in_ms=result.trained_in_ms,
        usable_for_attribution=usable,
        warnings=result.warnings,
    )


@router.get("/models", response_model=List[ModelSummary])
async def list_trained_models() -> List[ModelSummary]:
    return [ModelSummary(**m) for m in list_models()]


@router.get("/models/{session_id}", response_model=TrainResponse)
async def get_model(session_id: str) -> TrainResponse:
    """A trained model's stored accuracy, without retraining it."""
    if not has_model(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no trained gaze model for session {session_id!r}",
        )
    model = load_model(session_id)
    diagonal = (model.screen_width ** 2 + model.screen_height ** 2) ** 0.5
    median = model.metrics.get("median_error_px", 0.0)

    return TrainResponse(
        session_id=model.session_id,
        participant_id=model.participant_id,
        n_points=model.n_points,
        n_samples=model.n_samples,
        selection=model.selection,
        metrics=model.metrics,
        # Null, not a copy of `metrics`. A stored model no longer has the
        # calibration data it was fitted to, so its training error cannot be
        # recomputed -- and echoing the held-out numbers here would hand a
        # caller a different measurement under this field's name, making the
        # overfitting gap it exists to expose look like exactly zero.
        training_metrics=None,
        model_path=None,
        trained_in_ms=0.0,
        usable_for_attribution=median <= POOR_FIT_PX_FRACTION * diagonal,
        warnings=[],
    )


@router.delete("/models/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trained_model(session_id: str) -> None:
    clear_estimator(session_id)
    if not delete_model(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no trained gaze model for session {session_id!r}",
        )


@router.post("/models/{session_id}/estimate", response_model=EstimateResponse)
async def estimate(session_id: str, payload: EstimateRequest) -> EstimateResponse:
    """One frame's pupil positions -> one screen coordinate."""
    est = _estimator(session_id, payload.smoothing)
    point = est.estimate(
        left=_to_pupil(payload.left),
        right=_to_pupil(payload.right),
        timestamp=payload.timestamp,
        confidence=payload.confidence,
    )
    return EstimateResponse(
        session_id=session_id,
        gaze=GazePointModel(**point.to_dict()),
        model_median_error_px=est.median_error_px,
    )


@router.post("/models/{session_id}/estimate/batch", response_model=EstimateBatchResponse)
async def estimate_batch(
    session_id: str, payload: EstimateBatchRequest
) -> EstimateBatchResponse:
    """A burst of frames -> a slice of the gaze stream.

    Invalid frames are returned in place rather than dropped, so the caller
    can see where the gaps are -- a missing frame silently removed would read
    downstream as continuous attention.
    """
    est = _estimator(session_id, payload.smoothing)
    points = est.estimate_batch([
        {
            "left": _to_pupil(f.left),
            "right": _to_pupil(f.right),
            "timestamp": f.timestamp,
            "confidence": f.confidence,
        }
        for f in payload.frames
    ])
    valid = sum(1 for p in points if p.valid)
    return EstimateBatchResponse(
        session_id=session_id,
        gaze=[GazePointModel(**p.to_dict()) for p in points],
        valid_count=valid,
        invalid_count=len(points) - valid,
        model_median_error_px=est.median_error_px,
    )


__all__ = ["router"]
