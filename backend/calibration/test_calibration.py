"""
test_calibration.py

Run with: python3 test_calibration.py   (from inside backend/calibration)

Drives the calibration endpoints end to end with synthetic frames -- no
webcam, no models/*.pt, no mediapipe. Same shape as backend/agents/
test_agents.py: flat script, check() counter, non-zero exit on failure.

Two deliberate choices:

  * The route handlers are called directly (via asyncio.run) rather than
    through fastapi.testclient. TestClient needs httpx, which isn't in
    requirements.txt -- and the handlers are the actual unit under test, so
    the extra dependency would buy only Starlette's routing.

  * cv.StubPipeline moves its fake pupils WITH the target. A stub returning
    constants would let target/pupil mis-pairing pass silently, and that
    pairing is the one thing this module has to get right -- everything
    downstream trains on it.
"""

import asyncio
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

# backend/ on the path so this runs directly, the way test_agents.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv                                                        # noqa: E402
from cv.testing import StubPipeline                              # noqa: E402

from calibration import points as points_mod                     # noqa: E402
from calibration import routes                                   # noqa: E402
from calibration.schemas import (                                # noqa: E402
    StartCalibrationRequest,
    SubmitSamplesRequest,
)
from calibration.session import CalibrationSession               # noqa: E402
from calibration.storage import (                                # noqa: E402
    CalibrationStore,
    get_store,
    set_store,
)

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


def run(coro):
    return asyncio.run(coro)


def expect_http(label, coro, status_code):
    """Assert a route raises HTTPException with a given status."""
    from fastapi import HTTPException

    try:
        run(coro)
    except HTTPException as exc:
        check(f"{label} -> {status_code}", exc.status_code == status_code)
        return
    check(f"{label} -> {status_code}", False)


# ----------------------------------------------------------------------
# isolate: temp storage dir + stub detector, so nothing here touches
# calibration_data/ or needs a camera

tmp_dir = Path(tempfile.mkdtemp(prefix="gazelens_cal_test_"))
set_store(CalibrationStore(data_dir=tmp_dir))

stub = StubPipeline()
cv.set_pipeline(stub)

FRAME = "synthetic-frame-placeholder"   # StubPipeline doesn't decode by default


try:
    print("points -- grid geometry")
    grid9 = points_mod.generate_points(9)
    grid16 = points_mod.generate_points(16)
    check("9-point grid has 9 points", len(grid9) == 9)
    check("16-point grid has 16 points", len(grid16) == 16)
    check("indices are 0..n-1 in order", [p.index for p in grid16] == list(range(16)))
    check("all coords normalised to [0,1]",
          all(0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0 for p in grid16))
    check("edges are inset, not at 0/1",
          min(p.x for p in grid16) > 0.0 and max(p.x for p in grid16) < 1.0)
    check("grid is row-major (first row shares a y)",
          grid9[0].y == grid9[1].y == grid9[2].y)
    check("centre point of a 9-grid is centred", abs(grid9[4].x - 0.5) < 1e-6)

    try:
        points_mod.generate_points(12)
        check("unsupported pattern raises ValueError", False)
    except ValueError:
        check("unsupported pattern raises ValueError", True)

    try:
        points_mod.point_at(9, 99)
        check("out-of-range point_index raises IndexError", False)
    except IndexError:
        check("out-of-range point_index raises IndexError", True)

    # ------------------------------------------------------------------
    print("\nPOST /sessions -- starting a calibration")
    start = run(routes.start_calibration(StartCalibrationRequest(
        participant_id="p001",
        pattern=16,
        screen_width=1920,
        screen_height=1080,
        samples_per_point=5,
    )))
    session_id = start.session_id
    check("session id issued", session_id.startswith("cal_"))
    check("full point sequence returned", len(start.points) == 16)
    check("status is in_progress", start.status == "in_progress")
    check("session persisted immediately", (tmp_dir / f"{session_id}.json").exists())

    print("\nGET /patterns -- client and server share one grid")
    patterns = run(routes.list_patterns())
    check("both patterns offered", set(patterns.patterns) == {9, 16})
    check("pattern grid matches points.py",
          [p.model_dump() for p in patterns.patterns[16]]
          == [{"index": p.index, "x": p.x, "y": p.y} for p in grid16])

    # ------------------------------------------------------------------
    print("\nPOST /samples -- one target's worth of frames")
    target = grid16[0]
    stub.aim_at(target.x, target.y)
    resp = run(routes.submit_samples(session_id, SubmitSamplesRequest(
        point_index=0, frames=[FRAME] * 5,
    )))
    check("all 5 frames accepted", resp.accepted == 5)
    check("nothing rejected", resp.rejected == 0)
    check("server grid supplied the target", resp.target_source == "server_grid")
    check("target matches points.py", abs(resp.target_x - target.x) < 1e-9)
    check("point reported complete", resp.point_complete is True)
    check("session not complete yet", resp.session_complete is False)
    check("15 points still remaining", len(resp.points_remaining) == 15)
    check("preview reading returned for both eyes",
          resp.last_reading is not None and set(resp.last_reading) == {"left", "right"})

    print("\nPOST /samples -- blinks are counted, not silently dropped")
    stub.fail_next = 3
    stub.aim_at(grid16[1].x, grid16[1].y)
    blinked = run(routes.submit_samples(session_id, SubmitSamplesRequest(
        point_index=1, frames=[FRAME] * 5,
    )))
    check("3 misses rejected", blinked.rejected == 3)
    check("2 hits accepted", blinked.accepted == 2)
    check("miss reason surfaced", "no_pupil_detected" in blinked.note)
    check("point not complete on 2/5", blinked.point_complete is False)

    print("\nPOST /samples -- client may override the target")
    stub.aim_at(0.42, 0.77)
    override = run(routes.submit_samples(session_id, SubmitSamplesRequest(
        point_index=2, frames=[FRAME] * 5, target_x=0.42, target_y=0.77,
    )))
    check("client target used", override.target_source == "client")
    check("client x stored", abs(override.target_x - 0.42) < 1e-9)

    print("\nPOST /samples -- bad input is rejected")
    expect_http("point_index past the grid",
                routes.submit_samples(session_id, SubmitSamplesRequest(
                    point_index=99, frames=[FRAME])), 422)
    expect_http("half a target override",
                routes.submit_samples(session_id, SubmitSamplesRequest(
                    point_index=3, frames=[FRAME], target_x=0.5)), 422)
    expect_http("unknown session",
                routes.submit_samples("cal_doesnotexist", SubmitSamplesRequest(
                    point_index=0, frames=[FRAME])), 404)
    expect_http("path traversal in session id",
                routes.get_session("../../etc/passwd"), 404)

    print("\nGET /sessions/{id} -- progress and quality")
    st = run(routes.get_session(session_id))
    check("every point has a count, including zeros", len(st.sample_counts) == 16)
    check("point 0 has 5 samples", st.sample_counts[0] == 5)
    check("point 1 has 2 samples", st.sample_counts[1] == 2)
    check("untouched point reports 0", st.sample_counts[15] == 0)
    check("rejected frames recorded", st.quality.rejected_frames == 3)
    check("session not usable at 3/16 coverage", st.quality.usable is False)
    check("reason given for unusable", len(st.quality.reasons) > 0)
    check("is_complete False", st.is_complete is False)

    # ------------------------------------------------------------------
    print("\nfull run -- every point, then complete")
    full = run(routes.start_calibration(StartCalibrationRequest(
        participant_id="p002", pattern=9,
        screen_width=1440, screen_height=900, samples_per_point=6,
    )))
    full_id = full.session_id
    for p in points_mod.generate_points(9):
        stub.aim_at(p.x, p.y)
        r = run(routes.submit_samples(full_id, SubmitSamplesRequest(
            point_index=p.index, frames=[FRAME] * 6,
        )))
    check("session reports complete after last point", r.session_complete is True)
    check("no points remaining", r.points_remaining == [])

    done = run(routes.complete_calibration(full_id))
    check("status is complete", done.status == "complete")
    check("54 samples stored (9 points x 6)", done.total_samples == 54)
    check("quality is usable", done.quality.usable is True)
    check("full coverage", done.quality.point_coverage == 1.0)
    check("100% detection rate", done.quality.detection_rate == 1.0)
    check("both eyes on every sample", done.quality.both_eyes_rate == 1.0)
    check("ready for regression", done.ready_for_regression is True)
    check("row count matches sample count", done.training_row_count == 54)

    print("\ncompleted session is closed for writes")
    expect_http("submitting to a complete session",
                routes.submit_samples(full_id, SubmitSamplesRequest(
                    point_index=0, frames=[FRAME])), 409)

    # ------------------------------------------------------------------
    print("\nthe handoff to backend/gaze_estimation -- the CSV export")
    csv_path = Path(done.training_csv)
    check("training CSV written", csv_path.exists())

    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    check("one CSV row per sample", len(rows) == 54)

    required = {
        "left_x_eye", "left_y_eye", "right_x_eye", "right_y_eye",
        "target_x", "target_y", "session_id", "participant_id",
        "point_index", "screen_width", "screen_height", "confidence",
    }
    check("all regression columns present", required <= set(rows[0]))
    check("no empty feature cells",
          all(r["left_x_eye"] and r["target_x"] for r in rows))
    check("every calibration point appears in the export",
          {int(r["point_index"]) for r in rows} == set(range(9)))
    check("screen size travels with every row",
          all(r["screen_width"] == "1440" for r in rows))

    print("\nthe pairing is real, not coincidental")
    # The stub drives pupil position from the target, so if targets and
    # pupils were paired by arrival order instead of point_index, this
    # monotonic relationship would break.
    by_point = {}
    for r in rows:
        by_point.setdefault(int(r["point_index"]), []).append(r)
    leftmost = by_point[0][0]     # top-left target
    rightmost = by_point[2][0]    # top-right target
    check("target x differs between corners",
          float(rightmost["target_x"]) > float(leftmost["target_x"]))
    check("pupil x tracks target x",
          float(rightmost["left_x_eye"]) > float(leftmost["left_x_eye"]))
    check("pupil y tracks target y",
          float(by_point[6][0]["left_y_eye"]) > float(by_point[0][0]["left_y_eye"]))

    # ------------------------------------------------------------------
    print("\npersistence -- a restart must not lose the participant's work")
    original_rows = get_store().get(full_id).training_rows()
    fresh = CalibrationStore(data_dir=tmp_dir)     # cold, empty memory cache
    reloaded = fresh.get(full_id)
    check("session reloaded from disk", isinstance(reloaded, CalibrationSession))
    check("all samples survived", len(reloaded.samples) == 54)
    check("participant preserved", reloaded.participant_id == "p002")
    check("screen size preserved", reloaded.screen_width == 1440)
    check("training rows regenerate identically after a reload",
          reloaded.training_rows() == original_rows)

    raw = json.loads((tmp_dir / f"{full_id}.json").read_text(encoding="utf-8"))
    check("stored JSON is hand-readable (points included)", len(raw["points"]) == 9)
    check("stored JSON carries quality", raw["quality"]["usable"] is True)

    print("\nquality thresholds")
    sparse = CalibrationSession.create("p003", pattern=9, screen_width=800, screen_height=600)
    check("empty session is not usable", sparse.quality()["usable"] is False)
    check("MIN_SAMPLES_PER_POINT enforced in coverage",
          sparse.covered_points() == [])
    check("all 9 points listed as remaining", len(sparse.points_remaining()) == 9)

    print("\nGET /sessions and DELETE")
    listing = run(routes.list_sessions())
    check("both sessions listed", len({s.session_id for s in listing}) == 2)
    run(routes.delete_session(full_id))
    check("deleted session's JSON is gone", not (tmp_dir / f"{full_id}.json").exists())
    check("deleted session's CSV is gone", not csv_path.exists())
    expect_http("deleting a session twice", routes.delete_session(full_id), 404)

finally:
    cv.set_pipeline(None)
    set_store(None)
    shutil.rmtree(tmp_dir, ignore_errors=True)


print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
