"""
routes.py

FastAPI router for calibration data collection.

    POST   /api/calibration/sessions                       start a session
    POST   /api/calibration/sessions/{id}/samples          submit a burst of frames
    POST   /api/calibration/sessions/{id}/complete         finish + export
    GET    /api/calibration/sessions/{id}                  progress + quality
    GET    /api/calibration/sessions                       list
    DELETE /api/calibration/sessions/{id}                  discard
    GET    /api/calibration/patterns                       the target grids

The router is thin on purpose: validate, hand to cv, hand to session,
persist, respond. All the actual logic lives in session.py and storage.py so
it stays testable without HTTP -- and so this file is cheap to rewrite when
the real frontend contract turns up.

No auth dependency is attached here. backend/api's JWT code isn't in the
repo; when it is, add its dependency to the router in one line rather than
per route -- see CONTRACT.md.
"""

from typing import List

from fastapi import APIRouter, HTTPException, status

import cv

from .points import DEFAULT_PATTERN, PATTERNS, generate_points, point_at
from .schemas import (
    CalibrationPointModel,
    CompleteCalibrationResponse,
    PatternsResponse,
    PupilReading,
    SessionStatusResponse,
    SessionSummary,
    StartCalibrationRequest,
    StartCalibrationResponse,
    SubmitSamplesRequest,
    SubmitSamplesResponse,
)
from .session import (
    STATUS_COMPLETE,
    CalibrationSession,
    sample_from_frame_result,
)
from .storage import SessionNotFound, get_store

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


def _load(session_id: str) -> CalibrationSession:
    try:
        return get_store().get(session_id)
    except SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"calibration session {session_id!r} not found",
        ) from exc


def _points_model(session: CalibrationSession) -> List[CalibrationPointModel]:
    return [CalibrationPointModel(**p.to_dict()) for p in session.points]


def _status_payload(session: CalibrationSession) -> SessionStatusResponse:
    return SessionStatusResponse(
        session_id=session.session_id,
        participant_id=session.participant_id,
        pattern=session.pattern,
        status=session.status,
        screen_width=session.screen_width,
        screen_height=session.screen_height,
        samples_per_point=session.samples_per_point,
        points=_points_model(session),
        sample_counts=session.sample_counts(),
        points_remaining=session.points_remaining(),
        is_complete=session.is_complete(),
        quality=session.quality(),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# ----------------------------------------------------------------------


@router.get("/patterns", response_model=PatternsResponse)
async def list_patterns() -> PatternsResponse:
    """The target grids, so the client renders exactly what the server scores."""
    return PatternsResponse(
        patterns={
            n: [CalibrationPointModel(**p.to_dict()) for p in generate_points(n)]
            for n in sorted(PATTERNS)
        },
        default_pattern=DEFAULT_PATTERN,
    )


@router.post(
    "/sessions",
    response_model=StartCalibrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_calibration(payload: StartCalibrationRequest) -> StartCalibrationResponse:
    """Open a session and hand back the full target sequence."""
    session = CalibrationSession.create(
        participant_id=payload.participant_id,
        pattern=payload.pattern,
        screen_width=payload.screen_width,
        screen_height=payload.screen_height,
        samples_per_point=payload.samples_per_point,
    )
    get_store().save(session)

    return StartCalibrationResponse(
        session_id=session.session_id,
        participant_id=session.participant_id,
        pattern=session.pattern,
        samples_per_point=session.samples_per_point,
        points=_points_model(session),
        status=session.status,
    )


@router.post("/sessions/{session_id}/samples", response_model=SubmitSamplesResponse)
async def submit_samples(session_id: str, payload: SubmitSamplesRequest) -> SubmitSamplesResponse:
    """Run a burst of frames through the pupil detector and store the hits."""
    session = _load(session_id)

    if session.status == STATUS_COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session {session_id!r} is already complete; start a new one",
        )

    try:
        grid_point = point_at(session.pattern, payload.point_index)
    except IndexError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # Client-declared target wins when supplied -- it's what was actually on
    # screen. Both coordinates or neither; one alone is a client bug and
    # silently half-applying it would poison the training data.
    if (payload.target_x is None) != (payload.target_y is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target_x and target_y must be supplied together",
        )
    if payload.target_x is not None:
        target_x, target_y, target_source = payload.target_x, payload.target_y, "client"
    else:
        target_x, target_y, target_source = grid_point.x, grid_point.y, "server_grid"

    pipeline = cv.get_pipeline()

    accepted = 0
    rejected = 0
    last_reading = None
    notes: List[str] = []

    for frame_b64 in payload.frames:
        result = pipeline.process_encoded(frame_b64)
        sample = sample_from_frame_result(result, payload.point_index, target_x, target_y)
        if sample is None:
            rejected += 1
            session.record_rejection()
            if result.note and result.note not in notes:
                notes.append(result.note)
            continue

        session.add_sample(sample)
        accepted += 1
        last_reading = {
            side: PupilReading(
                x_eye=p.x_eye, y_eye=p.y_eye,
                x_frame=p.x_frame, y_frame=p.y_frame,
                confidence=p.confidence,
            )
            for side, p in result.pupils.items()
        }

    # Persist even a fully-rejected batch: the rejection count is part of the
    # quality signal, and losing it would make a bad calibration look clean.
    get_store().save(session)

    count = len(session.samples_for_point(payload.point_index))
    return SubmitSamplesResponse(
        session_id=session.session_id,
        point_index=payload.point_index,
        target_x=target_x,
        target_y=target_y,
        target_source=target_source,
        accepted=accepted,
        rejected=rejected,
        samples_for_point=count,
        samples_required=session.samples_per_point,
        point_complete=count >= session.samples_per_point,
        points_remaining=session.points_remaining(),
        session_complete=session.is_complete(),
        last_reading=last_reading,
        note="; ".join(notes),
    )


@router.post("/sessions/{session_id}/complete", response_model=CompleteCalibrationResponse)
async def complete_calibration(session_id: str) -> CompleteCalibrationResponse:
    """Close the session and write the training export.

    Completing a poor calibration is allowed -- it is saved with
    ready_for_regression=False rather than refused. Throwing away a
    participant's data because coverage came out at 70% would be worse than
    keeping it clearly labelled.
    """
    session = _load(session_id)
    quality = session.quality()
    paths = get_store().complete(session)

    return CompleteCalibrationResponse(
        session_id=session.session_id,
        status=session.status,
        total_samples=len(session.samples),
        quality=quality,
        session_file=str(paths["json"]),
        training_csv=str(paths["csv"]),
        training_row_count=len(session.training_rows()),
        ready_for_regression=bool(quality["usable"]),
    )


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions() -> List[SessionSummary]:
    return [SessionSummary(**s) for s in get_store().list_sessions()]


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session(session_id: str) -> SessionStatusResponse:
    return _status_payload(_load(session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> None:
    if not get_store().delete(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"calibration session {session_id!r} not found",
        )


__all__ = ["router"]
