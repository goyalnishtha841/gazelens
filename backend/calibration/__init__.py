"""
backend/calibration -- calibration data collection.

    from calibration import router
    app.include_router(router)

Collects (on-screen target, pupil position) pairs via backend/cv and stores
them in the shape backend/gaze_estimation will train its regression on. It
does not fit any model itself -- see CONTRACT.md for the handoff.

Relative imports throughout, for the reason spelled out in backend/cv/
__init__.py: both packages define a schemas.py, so flat sibling imports
would let one shadow the other. The one sys.path line below puts backend/
on the path so `import cv` resolves from routes.py no matter which
directory uvicorn was launched from.
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from .points import (                   # noqa: E402
    DEFAULT_PATTERN,
    PATTERNS,
    CalibrationPoint,
    generate_points,
    point_at,
)
from .session import (                  # noqa: E402
    DEFAULT_SAMPLES_PER_POINT,
    MIN_SAMPLES_PER_POINT,
    TRAINING_ROW_COLUMNS,
    CalibrationSample,
    CalibrationSession,
    sample_from_frame_result,
)
from .storage import (                  # noqa: E402
    DATA_DIR,
    CalibrationStore,
    SessionNotFound,
    get_store,
    set_store,
)
from .routes import router              # noqa: E402

__all__ = [
    "router",
    "PATTERNS",
    "DEFAULT_PATTERN",
    "CalibrationPoint",
    "generate_points",
    "point_at",
    "CalibrationSample",
    "CalibrationSession",
    "sample_from_frame_result",
    "TRAINING_ROW_COLUMNS",
    "DEFAULT_SAMPLES_PER_POINT",
    "MIN_SAMPLES_PER_POINT",
    "CalibrationStore",
    "SessionNotFound",
    "DATA_DIR",
    "get_store",
    "set_store",
]
