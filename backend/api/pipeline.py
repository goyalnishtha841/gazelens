"""
pipeline.py

The integration layer. Everything else in backend/ is a module that does one
thing; this is the file that calls them in order:

    gaze stream (JSONL)
      -> attribution.analyze_session      -> SessionMetrics
      -> agents.orchestrator.run_pipeline -> findings/issues/recommendations
      -> reports.heatmap_stub             -> attention figure (PNG)
      -> reports.report_generator         -> HTML + PDF

It CALLS those modules and never reaches inside them. Where a module doesn't
exist yet the call is stubbed and clearly marked, rather than the whole
pipeline being blocked -- that is why a session can be run end to end today
even though backend/render was never pushed.

WHY backend/agents AND backend/reports ARE IMPORTED BY PATH
-----------------------------------------------------------
Both use flat sibling imports (`from schemas import ...`, `from pdf_backends
import ...`) and expect to be run from inside their own directory. Putting
them on sys.path permanently would let agents/schemas.py shadow the
schemas.py in api/, attribution/ and gaze_estimation/. `_module_from()` loads
them under private names with their own directory on sys.path only for the
duration of the import, so nothing leaks.
"""

import importlib.util
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parent.parent

# Serialises the sys.path juggling in _module_from. FastAPI serves requests
# from a threadpool, so two finalise calls can land here at once; without this
# they can interleave and one can import against the other's sys.path.
_IMPORT_LOCK = threading.Lock()


def _module_from(name: str, path: Path, extra_syspath: Optional[Path] = None) -> ModuleType:
    """Import a module by file path, under a private name."""
    cached = sys.modules.get(name)
    if cached is not None:
        return cached

    with _IMPORT_LOCK:
        cached = sys.modules.get(name)
        if cached is not None:
            return cached

        added = False
        if extra_syspath is not None and str(extra_syspath) not in sys.path:
            sys.path.insert(0, str(extra_syspath))
            added = True
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"could not load {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
        finally:
            if added:
                sys.path.remove(str(extra_syspath))


def _agents_orchestrator() -> ModuleType:
    agents_dir = BACKEND / "agents"
    return _module_from("_gazelens_orchestrator", agents_dir / "orchestrator.py", agents_dir)


def _report_generator() -> ModuleType:
    reports_dir = BACKEND / "reports"
    return _module_from("_gazelens_report_generator",
                        reports_dir / "report_generator.py", reports_dir)


def _heatmap() -> ModuleType:
    reports_dir = BACKEND / "reports"
    return _module_from("_gazelens_heatmap", reports_dir / "heatmap_stub.py", reports_dir)


# ----------------------------------------------------------------------
# gaze stream storage
#
# JSONL rather than a table: it is append-only bulk timeseries (30Hz for
# minutes), nothing ever queries a single point, and appending a batch is one
# write with no transaction. See db.py.


def gaze_path_for(data_dir: Path, session_id: str) -> Path:
    return Path(data_dir) / f"{session_id}_gaze.jsonl"


def append_gaze(path: Path, points: List[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for p in points:
            fh.write(json.dumps(p, separators=(",", ":")) + "\n")
    return len(points)


def read_gaze(path: Path) -> List[dict]:
    if not Path(path).exists():
        return []
    out: List[dict] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # One torn line (a crash mid-append) shouldn't discard a whole
                # participant's session. Skip it; the count mismatch shows up
                # in the report's diagnostics.
                continue
    return out


# ----------------------------------------------------------------------
# calibration + gaze model -- called, never reached into


def calibration_summary(calibration_session_id: Optional[str]) -> Optional[dict]:
    """Quality of the referenced calibration session, or None."""
    if not calibration_session_id:
        return None
    try:
        from calibration import get_store
        from calibration.storage import SessionNotFound

        try:
            session = get_store().get(calibration_session_id)
        except SessionNotFound:
            return None
        return {
            "calibration_session_id": session.session_id,
            "pattern": session.pattern,
            "status": session.status,
            **session.quality(),
        }
    except ImportError:      # pragma: no cover - calibration is present
        return None


def estimate_gaze_frame(calibration_session_id: str, frame_b64: str,
                         timestamp: Optional[float] = None) -> dict:
    """One webcam frame -> one on-screen GazePoint, for the live session loop.

    ADDED DURING FRONTEND INTEGRATION -- this composition didn't exist as a
    callable unit before. backend/calibration/routes.py already goes
    frame -> cv.get_pipeline().process_encoded() -> pupil positions, and
    backend/gaze_estimation/routes.py's /estimate endpoints take pupil
    coordinates, not frames, "because for a real live session the two are
    better composed in-process" (see that module's routes.py docstring and
    estimator.LiveGazeEstimator.estimate_frame_result, which this calls).
    Nothing previously exposed that in-process composition over HTTP, which a
    browser-based live session needs -- browser JS cannot run the mediapipe +
    YOLO pupil detector itself. This is that composition, kept in pipeline.py
    because pipeline.py is where cross-module calls already live.

    Returns a GazePoint dict (timestamp, x, y, x_px, y_px, valid, in_bounds,
    confidence, note). Raises FileNotFoundError if calibration_session_id has
    no trained gaze model -- the caller (session_routes) turns that into 404.
    """
    import cv
    from gaze_estimation.estimator import get_estimator

    frame_result = cv.get_pipeline().process_encoded(frame_b64, timestamp=timestamp)
    estimator = get_estimator(calibration_session_id)
    point = estimator.estimate_frame_result(frame_result)
    return point.to_dict()


def train_gaze_model(calibration_session_id: str) -> Tuple[bool, Optional[dict], str]:
    """Fit this session's gaze model. Returns (ok, metrics, message)."""
    try:
        from gaze_estimation import train_session
    except ImportError as exc:      # pragma: no cover
        return False, None, f"gaze_estimation unavailable: {exc}"

    try:
        result = train_session(calibration_session_id)
    except Exception as exc:        # noqa: BLE001 -- surfaced to the caller
        return False, None, f"{type(exc).__name__}: {exc}"

    return True, result.metrics, (
        f"trained ({result.selection['chosen']['feature_set']} "
        f"deg{result.selection['chosen']['degree']}), held-out median "
        f"{result.metrics['median_error_px']:.0f}px"
    )


# ----------------------------------------------------------------------
# the analysis chain


def to_document_space(
    gaze_points: List[dict],
    capture_meta: Optional[dict],
) -> Tuple[List[dict], int]:
    """Translate viewport-relative gaze into document space.

    Gaze arrives normalised to the VIEWPORT -- that is what the eye tracker can
    know. A document-scope layout (backend/render, long scrollable pages) is
    normalised to the WHOLE page. Both have to describe the same coordinate
    system or nothing lines up, so:

        doc_y_norm = (y_norm * viewport_h + scroll_y) / document_h

    Returns (points, translated_count). Points with no scroll offset are
    treated as scroll_y=0, which is correct for a participant who never
    scrolled and is the only assumption available for a client that doesn't
    report it -- the count lets the caller warn when that assumption was
    load-bearing.

    A no-op unless the layout is document-scope, so test-UI sessions and
    single-screen pages are untouched.
    """
    meta = capture_meta or {}
    if meta.get("scope") != "document":
        return list(gaze_points), 0

    viewport = meta.get("viewport") or []
    document = meta.get("document_size") or []
    if len(viewport) != 2 or len(document) != 2 or not all(document):
        return list(gaze_points), 0

    vw, vh = float(viewport[0]), float(viewport[1])
    dw, dh = float(document[0]), float(document[1])

    translated: List[dict] = []
    scrolled = 0
    for p in gaze_points:
        sx = float(p.get("scroll_x") or 0.0)
        sy = float(p.get("scroll_y") or 0.0)
        if sy or sx:
            scrolled += 1
        q = dict(p)
        q["x"] = min(max((float(p["x"]) * vw + sx) / dw, 0.0), 1.0)
        q["y"] = min(max((float(p["y"]) * vh + sy) / dh, 0.0), 1.0)
        translated.append(q)
    return translated, scrolled


def build_metrics(gaze_points: List[dict], layout: dict, ui_page: str, session_id: str):
    """Gaze stream + element layout -> SessionMetrics (+ diagnostics)."""
    from attribution import analyze_session, build_ui_config, gaze_samples_from_dicts

    ui_config = build_ui_config(ui_page=ui_page, elements=layout)
    samples = gaze_samples_from_dicts(gaze_points)
    return analyze_session(samples, ui_config, session_id=session_id), ui_config


def run_agents(metrics) -> dict:
    """SessionMetrics -> the agent chain's verdict, verbatim."""
    return _agents_orchestrator().run_pipeline(metrics)


def render_report(
    pipeline_result: dict,
    metrics,
    ui_config,
    output_dir: Path,
    session_id: str,
) -> Dict[str, Optional[str]]:
    """Heatmap + HTML + PDF. Never fatal.

    A report that can't be rendered must not lose the analysis: the metrics
    and the agents' findings are already computed and stored by the caller,
    and they are the scientific output. The PDF is a presentation of them.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Optional[str]] = {
        "heatmap_path": None, "scanpath_path": None, "html_path": None,
        "pdf_path": None, "pdf_backend": None, "render_error": None,
    }

    try:
        heatmap_path = output_dir / f"{session_id}_heatmap.png"
        _heatmap().generate_attention_figure(
            metrics, ui_config.layout_for_heatmap(), str(heatmap_path)
        )
        out["heatmap_path"] = str(heatmap_path)
    except Exception as exc:        # noqa: BLE001
        out["render_error"] = f"heatmap: {type(exc).__name__}: {exc}"

    try:
        scanpath_path = output_dir / f"{session_id}_scanpath.png"
        _heatmap().generate_scanpath_figure(
            metrics, ui_config.layout_for_heatmap(), str(scanpath_path)
        )
        out["scanpath_path"] = str(scanpath_path)
    except Exception as exc:        # noqa: BLE001
        prev = out["render_error"]
        msg = f"scanpath: {type(exc).__name__}: {exc}"
        out["render_error"] = f"{prev}; {msg}" if prev else msg

    try:
        result = _report_generator().generate_report(
            pipeline_result,
            ui_page=metrics.ui_page,
            output_dir=str(output_dir),
            heatmap_path=out["heatmap_path"],
            scanpath_path=out["scanpath_path"],
        )
        out["html_path"] = result.get("html_path")
        out["pdf_path"] = result.get("pdf_path")
        out["pdf_backend"] = result.get("pdf_backend")
        if result.get("pdf_error"):
            # The HTML report exists; only the PDF rendering failed. Recorded
            # so it shows on the report, not raised.
            out["render_error"] = f"pdf: {result['pdf_error'].splitlines()[0]}"
    except Exception as exc:        # noqa: BLE001
        prev = out["render_error"]
        msg = f"report: {type(exc).__name__}: {exc}"
        out["render_error"] = f"{prev}; {msg}" if prev else msg

    return out


# ----------------------------------------------------------------------
# TODO(render): backend/render


def capture_page(
    target_url: str,
    screenshot_path: Optional[Path] = None,
    viewport: Tuple[int, int] = (1280, 720),
    timeout_ms: int = 20_000,
) -> dict:
    """Screenshot + auto element detection for an arbitrary URL.

    Calls backend/render. Never raises: a page that won't load is a real and
    recoverable outcome, and the session falls back to a placeholder layout
    rather than failing to be created at all. The caller decides what to do
    with `ok`.

    The detected labels are heuristics over tags and class names, not design
    intent -- `low_confidence_fraction` says how much of the page was guessed,
    and backend/api surfaces it on the report.
    """
    try:
        from render import RenderUnavailable, capture_page as _capture
    except ImportError as exc:      # pragma: no cover
        return {"ok": False, "reason": f"backend/render unavailable: {exc}",
                "layout": {}, "target_url": target_url}

    try:
        result = _capture(
            target_url,
            viewport=viewport,
            screenshot_path=screenshot_path,
            timeout_ms=timeout_ms,
        )
    except RenderUnavailable as exc:
        return {"ok": False, "reason": f"Chromium unavailable: {exc}",
                "layout": {}, "target_url": target_url}
    except Exception as exc:        # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}",
                "layout": {}, "target_url": target_url}

    if not result.layout:
        return {"ok": False,
                "reason": "no attributable elements were detected on the page",
                "layout": {}, "target_url": target_url,
                "screenshot_path": result.screenshot_path}

    return {
        "ok": True,
        "target_url": target_url,
        "final_url": result.final_url,
        "title": result.title,
        "layout": result.layout,
        "screenshot_path": result.screenshot_path,
        "detected": result.detected,
        "kept": result.kept,
        "low_confidence_fraction": result.low_confidence_fraction,
        "classification": result.classification,
        "warnings": result.warnings,
        # Load-bearing for to_document_space: without all three, gaze cannot
        # be translated into the layout's coordinate system.
        "scope": result.scope,
        "viewport": list(result.viewport),
        "document_size": list(result.document_size),
        "page_screens": result.page_screens,
    }


# ----------------------------------------------------------------------


def analyse_session(
    session_id: str,
    gaze_points: List[dict],
    layout: dict,
    ui_page: str,
    output_dir: Path,
    capture_meta: Optional[dict] = None,
) -> dict:
    """The whole chain in one call. Returns everything the caller stores.

    Raises only if the ANALYSIS fails (no gaze, unusable layout). Rendering
    failures come back in the result dict, because losing the PDF is not
    losing the session.
    """
    # Put gaze and boxes in the same coordinate system before anything else.
    gaze_points, scrolled = to_document_space(gaze_points, capture_meta)

    report, ui_config = build_metrics(gaze_points, layout, ui_page, session_id)
    pipeline_result = run_agents(report.metrics)
    rendered = render_report(
        pipeline_result, report.metrics, ui_config, output_dir, session_id
    )

    from dataclasses import asdict

    result = {
        "metrics": asdict(report.metrics),
        "pipeline_result": pipeline_result,
        "diagnostics": report.to_dict()["diagnostics"],
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        **rendered,
    }
    if (capture_meta or {}).get("scope") == "document":
        result["scroll_translated_points"] = scrolled
        if scrolled == 0 and gaze_points:
            # The layout spans a scrollable page but every gaze point claimed
            # scroll_y=0. Either the participant genuinely never scrolled, or
            # the client isn't reporting the offset -- in which case every
            # point was attributed to the first screen and anything below it
            # looks ignored.
            result["scroll_warning"] = (
                "layout covers the full scrollable page, but no gaze point "
                "carried a scroll offset. If the participant did scroll, the "
                "client is not sending scroll_y and everything below the fold "
                "will read as unlooked-at."
            )
    return result


__all__ = [
    "gaze_path_for",
    "append_gaze",
    "read_gaze",
    "calibration_summary",
    "estimate_gaze_frame",
    "train_gaze_model",
    "build_metrics",
    "run_agents",
    "render_report",
    "capture_page",
    "analyse_session",
]
