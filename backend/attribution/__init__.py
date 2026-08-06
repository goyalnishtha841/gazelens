"""
backend/attribution -- gaze stream + UI layout -> SessionMetrics.

    from attribution import analyze_session, build_ui_config, GazeSample

    report = analyze_session(samples, ui_config, session_id="s1")
    orchestrator.run_pipeline(report.metrics)     # straight into the agents

The missing link between raw gaze and the agent chain. Its only inputs are
(1) gaze coordinates with timestamps and (2) element bounding boxes -- it
imports nothing from backend/cv, backend/calibration or
backend/gaze_estimation, so it is developable and testable entirely
independently of them. See CONTRACT.md.

Output is backend/agents' own SessionMetrics class, loaded from that module
by file path (see agents_schema.py), so conformance is structural rather
than a copy that can drift.

Relative imports and the one sys.path line, same as backend/calibration and
backend/gaze_estimation: several backend packages define schemas.py, so flat
sibling imports would let one shadow another.
"""

import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from .agents_schema import SessionMetrics                  # noqa: E402
from .geometry import (                                    # noqa: E402
    BBox,
    BBoxFormatError,
    dispersion,
    hit_test,
    nearest_element,
    overlapping_pairs,
    parse_bbox,
)
from .elements import (                                    # noqa: E402
    ELEMENT_TYPES,
    IMPORTANCE_VALUES,
    Element,
    ElementConfigError,
    UIConfig,
    build_ui_config,
)
from .fixations import (                                   # noqa: E402
    DISPERSION_THRESHOLD,
    MAX_GAP,
    MIN_FIXATION_DURATION,
    AttributionTrace,
    Fixation,
    GazeSample,
    Visit,
    attribute,
    detect_fixations,
)
from .metrics import AttributionReport, build_metrics      # noqa: E402
from .engine import analyze_session, gaze_samples_from_dicts   # noqa: E402
from .routes import router                                 # noqa: E402

__all__ = [
    "router",
    "SessionMetrics",
    "analyze_session",
    "gaze_samples_from_dicts",
    "AttributionReport",
    "build_metrics",
    "GazeSample",
    "Fixation",
    "Visit",
    "AttributionTrace",
    "attribute",
    "detect_fixations",
    "UIConfig",
    "Element",
    "build_ui_config",
    "ElementConfigError",
    "IMPORTANCE_VALUES",
    "ELEMENT_TYPES",
    "BBox",
    "BBoxFormatError",
    "parse_bbox",
    "hit_test",
    "nearest_element",
    "overlapping_pairs",
    "dispersion",
    "MIN_FIXATION_DURATION",
    "DISPERSION_THRESHOLD",
    "MAX_GAP",
]
