"""
test_gaze_estimation.py

Run with: python3 test_gaze_estimation.py   (from inside backend/gaze_estimation)

The full path in one run, no webcam and no real participant:

    synthetic calibration session
      -> backend/calibration's own objects  (proves schema compatibility)
      -> feature extraction
      -> model selection + fit
      -> held-out accuracy (leave-one-point-out)
      -> persistence
      -> live per-frame inference
      -> the HTTP endpoints

Same shape as backend/agents/test_agents.py: flat script, check() counter,
non-zero exit on failure.

Route handlers are called directly via asyncio.run rather than through
fastapi.testclient, which needs httpx -- not a dependency, and the handlers
are the unit under test anyway. Same choice as backend/calibration's suite.
"""

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

# backend/ on the path so this runs directly, the way test_agents.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                               # noqa: E402

from calibration.storage import CalibrationStore, set_store      # noqa: E402

from gaze_estimation import evaluation, routes                   # noqa: E402
from gaze_estimation.estimator import (                          # noqa: E402
    LiveGazeEstimator,
    clear_cache,
    gaze_stream,
    get_estimator,
    set_model_dir,
)
from gaze_estimation.features import (                           # noqa: E402
    InsufficientCalibrationData,
    build_dataset,
)
from gaze_estimation.model import GazeModel, max_degree_for, n_terms   # noqa: E402
from gaze_estimation.schemas import (                            # noqa: E402
    EstimateBatchRequest,
    EstimateRequest,
    FrameInput,
    PupilInput,
    TrainRequest,
)
from gaze_estimation.synthetic import (                          # noqa: E402
    GOOD_SESSION,
    NOISY_SESSION,
    PRISTINE_SESSION,
    GazeGeometry,
    generate_calibration_session,
    generate_training_rows,
    synthetic_gaze_stream,
)
from gaze_estimation.training import (                           # noqa: E402
    load_model,
    train_from_rows,
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
    from fastapi import HTTPException

    try:
        run(coro)
    except HTTPException as exc:
        check(f"{label} -> {status_code}", exc.status_code == status_code)
        return
    check(f"{label} -> {status_code}", False)


# ----------------------------------------------------------------------
# isolation: temp dirs for both calibration sessions and trained models

cal_dir = Path(tempfile.mkdtemp(prefix="gazelens_ge_cal_"))
model_dir = Path(tempfile.mkdtemp(prefix="gazelens_ge_models_"))
set_store(CalibrationStore(data_dir=cal_dir))
set_model_dir(model_dir)

# routes.py resolves the model directory through training.MODEL_DIR, so point
# that at the temp dir too rather than writing into the repo during tests.
import gaze_estimation.training as training_mod                  # noqa: E402

training_mod.MODEL_DIR = model_dir

SCREEN_W, SCREEN_H = 1920, 1080
DIAGONAL = (SCREEN_W ** 2 + SCREEN_H ** 2) ** 0.5

try:
    # ------------------------------------------------------------------
    print("synthetic data -- must be backend/calibration's real objects")
    session = generate_calibration_session(pattern=16, samples_per_point=15,
                                           profile=GOOD_SESSION, seed=1)
    check("builds a real CalibrationSession", type(session).__name__ == "CalibrationSession")
    check("session id looks calibration-issued", session.session_id.startswith("cal_"))
    check("all 16 points covered", len(session.covered_points()) == 16)
    check("calibration's own quality check passes it", session.quality()["usable"] is True)
    check("blinks were recorded as rejections", session.rejected_frames > 0)

    rows = session.training_rows()
    check("training rows produced", len(rows) > 150)
    check("rows carry the target", "target_x" in rows[0] and "target_y" in rows[0])
    check("rows carry eye-normalised pupils", "left_x_eye" in rows[0])
    check("rows carry screen size", rows[0]["screen_width"] == 1920)
    check("some rows are one-eyed (blink-adjacent)",
          any(r["eyes_detected"] == 1 for r in rows))

    print("\nthe CSV export path works too (a session handed over as a file)")
    store = CalibrationStore(data_dir=cal_dir)
    paths = store.complete(session)
    from gaze_estimation.training import load_rows_from_csv

    csv_rows = load_rows_from_csv(paths["csv"])
    check("CSV round-trips to the same row count", len(csv_rows) == len(rows))
    check("CSV empty cells survive as usable None",
          build_dataset(csv_rows).n_samples == build_dataset(rows).n_samples)

    # ------------------------------------------------------------------
    print("\nfeatures -- eye-normalised coords, missing eyes handled")
    ds_mean = build_dataset(rows, feature_set="mean_eye")
    ds_both = build_dataset(rows, feature_set="both_eyes")
    datasets_by_feature_set = {"mean_eye": ds_mean, "both_eyes": ds_both}
    check("mean_eye is 2 features", ds_mean.X.shape[1] == 2)
    check("both_eyes is 4 features", ds_both.X.shape[1] == 4)
    check("mean_eye keeps one-eyed rows, both_eyes drops them",
          ds_mean.n_samples > ds_both.n_samples)

    # GOOD_SESSION barely moves the head (head_drift=0.010, spread over the
    # whole sitting) -- both_eyes_head should refuse it rather than fit
    # noise on a near-constant column. See MIN_HEAD_FEATURE_STD.
    try:
        build_dataset(rows, feature_set="both_eyes_head")
        check("both_eyes_head refuses a session with barely any head movement", False)
    except InsufficientCalibrationData:
        check("both_eyes_head refuses a session with barely any head movement", True)
    check("effective sample size is points, not rows", ds_mean.n_points == 16)
    check("rows far outnumber points (why point-wise CV matters)",
          ds_mean.n_samples > 10 * ds_mean.n_points)
    check("targets are normalised", float(ds_mean.y.max()) <= 1.0)

    print("\nfeatures -- a missing eye must not become 0.0")
    one_eyed = [{
        "target_x": 0.5, "target_y": 0.5, "point_index": 0, "confidence": 0.9,
        "screen_width": 1920, "screen_height": 1080,
        "left_x_eye": 0.6, "left_y_eye": 0.4,
        "right_x_eye": "", "right_y_eye": "",       # csv-style missing
    }]
    from gaze_estimation.features import FEATURE_SETS

    feats = FEATURE_SETS["mean_eye"](one_eyed[0])
    check("mean_eye falls back to the eye it has", feats == [0.6, 0.4])
    check("both_eyes refuses rather than inventing an eye",
          FEATURE_SETS["both_eyes"](one_eyed[0]) is None)

    print("\nfeatures -- thin sessions are refused, not silently fitted")
    try:
        build_dataset([dict(r) for r in rows if r["point_index"] < 3])
        check("under-4-point session raises", False)
    except InsufficientCalibrationData:
        check("under-4-point session raises", True)

    # ------------------------------------------------------------------
    print("\nmodel capacity -- parameters must stay under the point count")
    check("mean_eye deg2 is 6 params", n_terms(2, 2) == 6)
    check("both_eyes deg2 is 15 params", n_terms(4, 2) == 15)
    check("9 points caps mean_eye at degree 2", max_degree_for("mean_eye", 9) == 2)
    check("16 points allows mean_eye degree 3", max_degree_for("mean_eye", 16) == 3)
    check("9 points caps both_eyes at degree 1", max_degree_for("both_eyes", 9) == 1)
    check("no candidate ever has params >= points",
          all(n_terms(2, d) <= 16 - 2 for d in range(1, max_degree_for("mean_eye", 16) + 1)))

    # ------------------------------------------------------------------
    print("\nTHE honest-metric check: point-wise CV vs row-wise CV")
    # A random row split puts near-identical frames of the same fixation in
    # both train and test, so the model is scored on points it has already
    # seen. That flatters it exactly when it matters: when the model has
    # enough capacity to memorise individual point positions.
    #
    # Demonstrated on the configuration the capacity cap exists to forbid --
    # degree 3 (10 parameters) on a 9-point session. Both figures are
    # FRAME-level, so this is a like-for-like comparison; comparing a
    # frame-level number against a point-averaged one would confound
    # leakage with the averaging of detector jitter.
    rows9 = generate_training_rows(pattern=9, profile=GOOD_SESSION, seed=4)
    ds9 = build_dataset(rows9, feature_set="mean_eye")
    over_degree = 3
    check("this configuration is above the capacity cap (so selection can't pick it)",
          n_terms(2, over_degree) > max_degree_for("mean_eye", ds9.n_points))

    rng = np.random.default_rng(0)
    order = rng.permutation(ds9.n_samples)
    cut = int(0.8 * ds9.n_samples)
    tr, te = order[:cut], order[cut:]
    leaky = GazeModel.fit(ds9.X[tr], ds9.y[tr], "mean_eye", over_degree, 1e-6,
                          SCREEN_W, SCREEN_H)
    leaky_px = evaluation.error_metrics(
        leaky.predict(ds9.X[te]), ds9.y[te], SCREEN_W, SCREEN_H)["median_error_px"]

    honest9 = evaluation.cross_validate(ds9, over_degree, 1e-6)
    honest_px = honest9["per_frame_median_error_px"]

    print(f"        row-wise 80/20 split : {leaky_px:6.1f}px  (leaks -- points seen in training)")
    print(f"        leave-one-point-out  : {honest_px:6.1f}px  (honest -- point never seen)")
    check("row-wise splitting really does report a smaller error",
          leaky_px < honest_px)
    check("and the gap is large enough to mislead", honest_px > 1.5 * leaky_px)

    honest = evaluation.cross_validate(ds_mean, 2, 1e-4)
    check("held-out folds equal the point count", honest["folds"] == 16)
    check("validation method is labelled", honest["validation"] == "leave_one_point_out")

    print("\nper-frame error is reported and is worse than per-point")
    check("per-frame error present", "per_frame_median_error_px" in honest)
    check("per-frame error exceeds point-averaged error",
          honest["per_frame_median_error_px"] > honest["median_error_px"])

    # ------------------------------------------------------------------
    print("\ntraining -- a clean session")
    result = train_from_rows(rows, session_id=session.session_id,
                             participant_id=session.participant_id,
                             model_dir=model_dir)
    m = result.metrics
    print(f"        chosen: {result.selection['chosen']}")
    print(f"        held-out median {m['median_error_px']:.1f}px "
          f"({m['median_error_pct_diagonal']:.2f}% of diagonal), "
          f"per-frame {m['per_frame_median_error_px']:.1f}px, "
          f"fit in {result.trained_in_ms:.0f}ms")

    check("trains in well under a second", result.trained_in_ms < 1000)
    check("held-out error is under 2% of the screen diagonal",
          m["median_error_px"] < 0.02 * DIAGONAL)
    check("held-out error is not zero (that would mean leakage)",
          m["median_error_px"] > 0)
    check("held-out error >= training error, now they're comparable",
          m["median_error_px"] >= result.training_metrics["median_error_px"])
    check("per-point breakdown reported", len(m["per_point_error_px"]) == 16)
    check("worst point identified", "worst_point" in m)
    check("model persisted", result.model_path and result.model_path.exists())
    check("selection leaderboard kept for the paper",
          len(result.selection["leaderboard"]) > 1)

    print("\ntraining -- degrees of visual angle only when geometry is supplied")
    check("no degrees without viewing distance", "median_error_deg" not in m)
    check("absence is explained, not silent", "degrees_unavailable" in m)

    with_geometry = train_from_rows(rows, session_id="", persist=False,
                                    viewing_distance_cm=60, screen_diagonal_in=15.6)
    gm = with_geometry.metrics
    check("degrees reported when supplied", "median_error_deg" in gm)
    check("degrees are a plausible webcam-gaze figure (0-5 deg)",
          0 < gm["median_error_deg"] < 5)
    print(f"        with 60cm / 15.6in: {gm['median_error_deg']:.2f} degrees")

    print("\ntraining -- model selection responds to the data")
    # A 9-point grid has only 3 distinct columns, so the generator's
    # curvature term is indistinguishable from linear there; 16 points
    # resolve it. Selection should notice the difference by itself.
    nine = train_from_rows(generate_training_rows(pattern=9, profile=PRISTINE_SESSION,
                                                  seed=2),
                           session_id="", persist=False)
    sixteen = train_from_rows(generate_training_rows(pattern=16, profile=PRISTINE_SESSION,
                                                     seed=2),
                              session_id="", persist=False)
    check("9-point noiseless session selects a low degree",
          nine.selection["chosen"]["degree"] <= 2)
    check("16-point noiseless session can select a higher degree",
          sixteen.selection["chosen"]["degree"] >= nine.selection["chosen"]["degree"])
    check("noiseless data fits essentially exactly",
          nine.metrics["median_error_px"] < 5)

    print("\ntraining -- a bad session is flagged, not hidden")
    bad = train_from_rows(
        generate_training_rows(pattern=9, profile=NOISY_SESSION, seed=3),
        session_id="", persist=False)
    check("noisy session has larger held-out error",
          bad.metrics["median_error_px"] > m["median_error_px"])
    check("noisy session raises warnings", len(bad.warnings) > 0)
    print(f"        noisy session: {bad.metrics['median_error_px']:.1f}px, "
          f"{len(bad.warnings)} warning(s)")

    # ------------------------------------------------------------------
    print("\npersistence -- calibrate once, not per gaze estimate")
    reloaded = load_model(session.session_id, model_dir)
    check("model reloads from disk", isinstance(reloaded, GazeModel))
    check("coefficients survive the round trip",
          np.allclose(reloaded.coef, result.model.coef))
    check("held-out metrics travel with the model",
          reloaded.metrics["median_error_px"] == m["median_error_px"])
    reload_X = datasets_by_feature_set[reloaded.feature_set].X[:5]
    check("predictions are identical after reload",
          np.allclose(reloaded.predict(reload_X), result.model.predict(reload_X)))

    print("\npersistence -- a stale model format is refused, not misread")
    stale = result.model.to_dict()
    stale["format_version"] = 99
    try:
        GazeModel.from_dict(stale)
        check("unknown model format raises", False)
    except ValueError:
        check("unknown model format raises", True)

    # ------------------------------------------------------------------
    print("\nlive inference -- accuracy on a fresh gaze stream")
    estimator = get_estimator(session.session_id)
    stream = synthetic_gaze_stream(geometry=GazeGeometry(), samples_per_stop=10)
    # Whatever feature_set model selection picked for `session` above --
    # possibly both_eyes_head, which needs this and ignores it otherwise.
    HEAD_PROXY = stream[0]["head_proxy"]

    errors = []
    for frame in stream:
        point = estimator.estimate(left=frame["left"], right=frame["right"],
                                   timestamp=frame["timestamp"],
                                   head_proxy=frame["head_proxy"])
        check_ok = point.valid
        if not check_ok:
            continue
        dx = (point.x - frame["true_x"]) * SCREEN_W
        dy = (point.y - frame["true_y"]) * SCREEN_H
        errors.append((dx ** 2 + dy ** 2) ** 0.5)

    live_median = float(np.median(errors))
    print(f"        live median error over {len(errors)} frames: {live_median:.1f}px")
    check("every stream frame produced a gaze point", len(errors) == len(stream))
    check("live error is in the same ballpark as held-out per-frame error",
          live_median < 3 * m["per_frame_median_error_px"])
    check("live error is under 5% of the diagonal", live_median < 0.05 * DIAGONAL)

    print("\nlive inference -- latency")
    sample = stream[0]
    t0 = time.perf_counter()
    for _ in range(2000):
        estimator.estimate(left=sample["left"], right=sample["right"], timestamp=0.0,
                           head_proxy=sample["head_proxy"])
    per_call_us = (time.perf_counter() - t0) / 2000 * 1e6
    print(f"        {per_call_us:.0f}us per estimate")
    check("per-frame inference is well under a 30fps budget (33ms)",
          per_call_us < 33_000)

    print("\nlive inference -- misses stay in the stream")
    blank = estimator.estimate(left=None, right=None, timestamp=1.0)
    check("no pupil gives an invalid point, not an exception", blank.valid is False)
    check("invalid point is labelled", blank.note == "no_pupil")
    check("invalid point still carries its timestamp", blank.timestamp == 1.0)

    print("\nlive inference -- off-screen predictions are flagged, not disguised")
    far = estimator.estimate(left=(0.0, 0.0), right=(0.0, 0.0), timestamp=2.0,
                             head_proxy=HEAD_PROXY)
    check("extreme pupil position still returns a point", far.valid is True)
    check("coordinates are clamped to the screen", 0.0 <= far.x <= 1.0)
    check("but out-of-bounds is reported",
          far.in_bounds is False and far.note == "off_screen")

    print("\nlive inference -- pixel coords, cv duck typing, streaming")
    p = estimator.estimate(left=(0.52, 0.49), right=(0.50, 0.50), timestamp=3.0,
                           head_proxy=HEAD_PROXY)
    check("pixel coords match normalised x screen size",
          abs(p.x_px - p.x * SCREEN_W) < 1e-6)
    check("estimator states its own error bar", estimator.median_error_px == m["median_error_px"])

    class FakeFrameResult:
        """Shaped like a cv.FrameResult, without importing cv."""
        class _P:
            def __init__(self, x, y):
                self.x_eye, self.y_eye = x, y

        left = _P(0.52, 0.49)
        right = _P(0.50, 0.50)
        timestamp = 4.0
        mean_confidence = 0.9
        head_proxy = HEAD_PROXY

    duck = estimator.estimate_frame_result(FakeFrameResult())
    check("cv.FrameResult shape works by duck typing", duck.valid is True)
    check("confidence carried through from the detector", duck.confidence == 0.9)

    streamed = list(gaze_stream(estimator, [
        {"left": (0.5, 0.5), "right": (0.5, 0.5), "timestamp": 5.0, "head_proxy": HEAD_PROXY},
        {"left": None, "right": None, "timestamp": 5.03},
    ]))
    check("gaze_stream yields a point per frame, gaps included", len(streamed) == 2)
    check("the gap is preserved as an invalid point", streamed[1].valid is False)

    print("\nlive inference -- smoothing is off by default")
    raw_est = LiveGazeEstimator(reloaded, smoothing=0.0)
    smooth_est = LiveGazeEstimator(reloaded, smoothing=0.8)
    for e in (raw_est, smooth_est):
        e.estimate(left=(0.3, 0.3), right=(0.3, 0.3), timestamp=0.0, head_proxy=HEAD_PROXY)
    raw_jump = raw_est.estimate(left=(0.7, 0.7), right=(0.7, 0.7), timestamp=0.1, head_proxy=HEAD_PROXY)
    smooth_jump = smooth_est.estimate(left=(0.7, 0.7), right=(0.7, 0.7), timestamp=0.1, head_proxy=HEAD_PROXY)
    check("smoothing lags a saccade (which is why it defaults off)",
          smooth_jump.x < raw_jump.x)

    # ------------------------------------------------------------------
    print("\nboth_eyes_head -- selected and accurate when the head actually moves")
    # A session with real head movement (unlike GOOD_SESSION above, which
    # both_eyes_head correctly refuses) -- otherwise identical profile, so
    # this isolates head_drift as the one thing that changes.
    from gaze_estimation.synthetic import SessionProfile
    HEAD_MOVING_SESSION = SessionProfile(head_drift=0.08)
    head_session = generate_calibration_session(
        pattern=16, samples_per_point=15, profile=HEAD_MOVING_SESSION, seed=1
    )
    head_rows = head_session.training_rows()
    head_ds = build_dataset(head_rows, feature_set="both_eyes_head")
    # Same two columns build_dataset's own guard checks (see features.py) --
    # interocular_norm and roll_norm aren't held to this bar; see that
    # function's comment for why.
    check("head movement clears the minimum-spread bar",
          bool((head_ds.X[:, 5:7].std(axis=0) >= 0.01).all()))

    head_result = train_from_rows(head_rows, session_id=head_session.session_id,
                                  participant_id=head_session.participant_id,
                                  model_dir=model_dir, feature_set="both_eyes_head")
    check("trains without error on a head-moving session",
          head_result.model.feature_set == "both_eyes_head")
    check("held-out error is still sane (not the earlier low-variance blowup)",
          head_result.metrics["median_error_px"] < 0.05 * DIAGONAL)

    head_estimator = LiveGazeEstimator(head_result.model)
    # head_drift=0.08 matched between calibration and this stream -- same
    # relationship generate_calibration_session used, at the session's
    # midpoint (progress~=0.5) rather than either endpoint.
    head_stream = synthetic_gaze_stream(geometry=GazeGeometry(), samples_per_stop=10,
                                        head_drift=0.04)
    head_errors = []
    for frame in head_stream:
        point = head_estimator.estimate(left=frame["left"], right=frame["right"],
                                        timestamp=frame["timestamp"],
                                        head_proxy=frame["head_proxy"])
        if point.valid:
            dx = (point.x - frame["true_x"]) * SCREEN_W
            dy = (point.y - frame["true_y"]) * SCREEN_H
            head_errors.append((dx ** 2 + dy ** 2) ** 0.5)
    head_live_median = float(np.median(head_errors)) if head_errors else float("nan")
    print(f"        both_eyes_head live median error: {head_live_median:.1f}px "
          f"over {len(head_errors)}/{len(head_stream)} frames")
    # Looser bound than the pupil-only live-accuracy check above (5% of
    # diagonal) on purpose: at 16 points, 8 features is 9 fit parameters
    # against a budget of 14 (max_degree_for's n_points-2), close enough to
    # the limit that this feature set is measurably less data-efficient
    # than both_eyes/mean_eye, even with the low-variance guard satisfied.
    # That's a real, worth-reporting property of the feature, not a bug in
    # it -- and it's exactly why train_session leaves selection to LOPO
    # cross-validation rather than always preferring the richer feature
    # set: a session where both_eyes_head doesn't actually generalise
    # better simply won't have it chosen. This test forces the override to
    # exercise the code path at all.
    check("both_eyes_head live accuracy is sane for a 9-parameter/16-point fit",
          head_live_median < 0.20 * DIAGONAL)

    # Confirms head_proxy is load-bearing, not decorative: a both_eyes_head
    # model has no fallback for a missing head reading -- features.py's
    # _both_eyes_head returns None without it, same as a missing pupil.
    no_proxy_point = head_estimator.estimate(
        left=head_stream[0]["left"], right=head_stream[0]["right"],
        timestamp=head_stream[0]["timestamp"],
    )
    check("a both_eyes_head model without head_proxy is invalid, not silently wrong",
          no_proxy_point.valid is False
          and no_proxy_point.note == "insufficient_pupils_for_feature_set")

    # ------------------------------------------------------------------
    print("\nAPI -- train from a stored calibration session")
    clear_cache()
    api_session = generate_calibration_session(pattern=16, samples_per_point=12,
                                               participant_id="api_p01", seed=5)
    store.save(api_session)
    sid = api_session.session_id

    resp = run(routes.train(sid, TrainRequest(viewing_distance_cm=60,
                                              screen_diagonal_in=15.6)))
    check("train returns the session id", resp.session_id == sid)
    check("held-out metrics are the leave-one-point-out ones",
          resp.metrics.validation == "leave_one_point_out")
    check("training metrics labelled as not held out",
          resp.training_metrics.validation == "training_fit_not_held_out")
    check("degrees present when geometry supplied", resp.metrics.median_error_deg is not None)
    check("usable for attribution", resp.usable_for_attribution is True)
    check("model path returned", resp.model_path is not None)
    check("n_points reported", resp.n_points == 16)

    print("\nAPI -- validation and error paths")
    expect_http("training an unknown session", routes.train("cal_nope", TrainRequest()), 404)
    expect_http("estimating with no trained model",
                routes.estimate("cal_nope", EstimateRequest(left=PupilInput(x=0.5, y=0.5))), 404)
    expect_http("fetching an unknown model", routes.get_model("cal_nope"), 404)
    expect_http("deleting an unknown model", routes.delete_trained_model("cal_nope"), 404)

    try:
        TrainRequest(viewing_distance_cm=60)      # missing screen_diagonal_in
        check("half the visual-angle geometry is rejected", False)
    except Exception:
        check("half the visual-angle geometry is rejected", True)

    try:
        EstimateRequest()                          # no eyes at all
        check("estimate with no eyes is rejected", False)
    except Exception:
        check("estimate with no eyes is rejected", True)

    print("\nAPI -- live inference endpoints")
    est_resp = run(routes.estimate(sid, EstimateRequest(
        left=PupilInput(x=0.52, y=0.49), right=PupilInput(x=0.50, y=0.50),
        timestamp=100.0)))
    check("single estimate returns a gaze point", est_resp.gaze.valid is True)
    check("estimate carries the model's error bar",
          est_resp.model_median_error_px is not None)
    check("gaze is on screen", 0.0 <= est_resp.gaze.x <= 1.0)

    batch = run(routes.estimate_batch(sid, EstimateBatchRequest(frames=[
        FrameInput(left=PupilInput(x=0.52, y=0.49), right=PupilInput(x=0.50, y=0.50),
                   timestamp=101.0),
        FrameInput(timestamp=101.03),                    # a blink
        FrameInput(left=PupilInput(x=0.48, y=0.51), timestamp=101.06),
    ])))
    check("batch returns one point per frame", len(batch.gaze) == 3)
    check("blink counted as invalid", batch.invalid_count == 1)
    check("valid frames counted", batch.valid_count == 2)
    check("the blink kept its position in the stream", batch.gaze[1].valid is False)

    print("\nAPI -- retraining must not serve a stale cached model")
    before = run(routes.estimate(sid, EstimateRequest(
        left=PupilInput(x=0.30, y=0.30), timestamp=1.0))).gaze
    run(routes.train(sid, TrainRequest(feature_set="mean_eye", degree=1)))
    after = run(routes.estimate(sid, EstimateRequest(
        left=PupilInput(x=0.30, y=0.30), timestamp=1.0))).gaze
    check("retrained model actually replaces the cached one",
          (before.x, before.y) != (after.x, after.y))
    stored = run(routes.get_model(sid))
    check("override is recorded as not auto-selected",
          "override" in stored.selection.selection_criterion)
    check("a stored model still reports its held-out error",
          stored.metrics.median_error_px > 0)
    check("a stored model reports training_metrics as null, not a copy of "
          "the held-out ones", stored.training_metrics is None)

    print("\nAPI -- listing and deletion")
    listed = run(routes.list_trained_models())
    check("trained models listed", any(x.session_id == sid for x in listed))
    run(routes.delete_trained_model(sid))
    check("deleted model is gone", not (model_dir / f"{sid}.json").exists())
    expect_http("estimating after deletion",
                routes.estimate(sid, EstimateRequest(left=PupilInput(x=0.5, y=0.5))), 404)

finally:
    clear_cache()
    set_model_dir(None)
    set_store(None)
    shutil.rmtree(cal_dir, ignore_errors=True)
    shutil.rmtree(model_dir, ignore_errors=True)


print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
