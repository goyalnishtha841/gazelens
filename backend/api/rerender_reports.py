"""
rerender_reports.py

Re-run the analysis for sessions that already have a report, so they pick up
changes to the report visuals or the PDF template without being recorded
again. The stored gaze stream is the input; nothing is re-captured.

Run from backend/:

    python -m api.rerender_reports              # every finished session
    python -m api.rerender_reports ses_abc123   # just these
"""

import sys
from pathlib import Path

from . import pipeline
from .db import DATA_DIR, SessionLocal
from .models import Session as SessionModel


def rerender(session_ids=None) -> int:
    db = SessionLocal()
    done = 0
    try:
        query = db.query(SessionModel)
        if session_ids:
            query = query.filter(SessionModel.id.in_(session_ids))
        for session in query.all():
            report = session.report
            if report is None or not session.gaze_path or not Path(session.gaze_path).exists():
                continue
            result = pipeline.analyse_session(
                session_id=session.id,
                gaze_points=pipeline.read_gaze(Path(session.gaze_path)),
                layout=session.element_layout or {},
                ui_page=session.ui_page or "unknown_page",
                output_dir=Path(DATA_DIR) / session.id,
                capture_meta=session.capture_meta,
                calibration_session_id=session.calibration_session_id,
            )
            report.pipeline_result = result["pipeline_result"]
            report.metrics = result["metrics"]
            report.html_path = result["html_path"]
            report.pdf_path = result["pdf_path"]
            report.heatmap_path = result["heatmap_path"]
            report.scanpath_path = result["scanpath_path"]
            report.pdf_backend = result["pdf_backend"]
            db.commit()
            done += 1
            print(f"{session.id}: re-rendered" + (f" ({result['render_error']})" if result.get("render_error") else ""))
    finally:
        db.close()
    return done


if __name__ == "__main__":
    n = rerender(sys.argv[1:] or None)
    print(f"{n} report(s) re-rendered")
