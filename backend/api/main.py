"""
main.py

The GazeLens API.

    cd backend
    uvicorn api.main:app --reload --port 8000
    # docs at http://localhost:8000/docs

NOTE ON THE RUN COMMAND: this is `cd backend && uvicorn api.main:app`, not
`cd backend/api && uvicorn main:app`. backend/api is a package now, and it has
to be, because several backend packages define a schemas.py -- running from
inside the directory would put api/schemas.py on sys.path where it can shadow
attribution's or gaze_estimation's. Same reason backend/cv and
backend/calibration use relative imports.

WHAT THIS APP IS
----------------
The README described a backend/api with signup/login/JWT as already built and
tested. That code was never pushed to origin/main -- this file started as a
placeholder that mounted the calibration router so it could be exercised at
all. It now carries the real thing: users, JWT auth, sessions, and the
orchestration that runs the whole pipeline. See CONTRACT.md.

Mounted routers:
    /api/auth           users, login, JWT
    /api/sessions       session lifecycle + reports  (auth required)
    /api/calibration    calibration data collection
    /api/gaze           per-session gaze model training + inference
    /api/attribution    gaze stream -> UI metrics
    /api/render         arbitrary-URL screenshot + element detection
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# backend/ on the path so the sibling packages (calibration, gaze_estimation,
# attribution) import by their own names regardless of where uvicorn started.
_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from attribution import router as attribution_router          # noqa: E402
from calibration import router as calibration_router          # noqa: E402
from gaze_estimation import router as gaze_router             # noqa: E402
from render import router as render_router                    # noqa: E402

from .auth_routes import router as auth_router                # noqa: E402
from .db import init_db                                       # noqa: E402
from .session_routes import router as session_router          # noqa: E402

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Idempotent create_all. Fine at this scale; see db.init_db for why there
    # is no migration tool yet and when to add one.
    #
    # lifespan rather than @app.on_event("startup"): on_event is deprecated in
    # this FastAPI version and emits a DeprecationWarning on import.
    init_db()
    yield


app = FastAPI(
    title="GazeLens API",
    description="Webcam gaze estimation and multi-agent UX evaluation.",
    version="1.0.0",
    lifespan=lifespan,
)

# The Vite dev server runs on a different origin, so the browser preflights
# every POST. Dev origins only -- tighten before this is exposed anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(session_router)
app.include_router(calibration_router)
app.include_router(gaze_router)
app.include_router(attribution_router)
app.include_router(render_router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Liveness, plus whether live capture can actually run on this machine.

    cv_available is False on a clean clone (models/*.pt is gitignored).
    Surfacing it here beats finding out from a 500 on the first frame.
    """
    import cv

    from .db import DATABASE_URL

    return {
        "status": "ok",
        "cv_available": cv.get_pipeline().available,
        "weights_path": str(cv.DEFAULT_WEIGHTS),
        "weights_present": cv.DEFAULT_WEIGHTS.exists(),
        "database": DATABASE_URL.split("///")[-1],
    }
