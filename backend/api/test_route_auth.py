"""
test_route_auth.py

Run with: python3 test_route_auth.py   (from inside backend/api)

The auth boundary on the module routers, over real HTTP (fastapi.testclient,
from requirements-dev.txt) against the assembled app -- the other suites call
handlers directly, which can't catch a route that never had the dependency
attached in the first place.

    1. Every route under /api/calibration, /api/gaze, /api/attribution and
       /api/render answers 401 without a token, and with a bad one.
    2. Calibration sessions and gaze models are per-user: another user gets
       404 (not 403) on every route, and an empty listing.
    3. Legacy calibrations (written before owner_id existed) are reachable
       only through a /api/sessions session the user already owns, and can't
       be claimed by naming them in a new session.

Same shape as test_api.py: flat script, check() counter, non-zero exit on
failure.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Must be set before api.db is imported -- it reads these at module scope.
_TMP = Path(tempfile.mkdtemp(prefix="fixation_route_auth_test_"))
os.environ["FIXATION_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["FIXATION_DATA_DIR"] = str(_TMP / "data")
os.environ["GAZELENS_LLM"] = "off"
os.environ.setdefault(
    "FIXATION_SECRET_KEY",
    "test-only-key-not-for-deployment-0123456789abcdef",
)

from fastapi.testclient import TestClient                          # noqa: E402

import gaze_estimation.training as ge_training                     # noqa: E402
from api.db import SessionLocal                                    # noqa: E402
from api.main import app                                           # noqa: E402
from api.models import Session as SessionModel                     # noqa: E402
from calibration.storage import CalibrationStore, set_store        # noqa: E402
from gaze_estimation import set_model_dir                          # noqa: E402
from gaze_estimation.synthetic import generate_calibration_session  # noqa: E402

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


cal_dir = _TMP / "calibration"
model_dir = _TMP / "models"
store = CalibrationStore(data_dir=cal_dir)
set_store(store)
set_model_dir(model_dir)
_saved_model_dir = ge_training.MODEL_DIR
ge_training.MODEL_DIR = model_dir

PROTECTED_PREFIXES = ("/api/calibration", "/api/gaze", "/api/attribution", "/api/render")

try:
    with TestClient(app) as client:

        def signup(email):
            r = client.post("/api/auth/signup",
                            json={"email": email, "full_name": "Test User", "password": "Correct-Horse-1"})
            assert r.status_code == 201, r.text
            body = r.json()
            return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]

        alice, alice_id = signup("alice@example.com")
        bob, _ = signup("bob@example.com")

        # --------------------------------------------------------------
        print("401 -- every module route refuses an anonymous caller")
        probed = []
        # From the OpenAPI schema rather than app.routes: newer FastAPI keeps
        # included routers nested, and the schema is the public surface anyway.
        for path, ops in app.openapi()["paths"].items():
            if not path.startswith(PROTECTED_PREFIXES):
                continue
            concrete = re.sub(r"\{[^}]+\}", "cal_000000000000", path)
            for method in sorted(m.upper() for m in ops):
                probed.append((method, path))
                anon = client.request(method, concrete)
                check(f"{method} {path} without a token -> 401", anon.status_code == 401)
                forged = client.request(method, concrete,
                                        headers={"Authorization": "Bearer not.a.jwt"})
                check(f"{method} {path} with a bad token -> 401", forged.status_code == 401)
        # Guard the guard: if the routers stop being mounted (or move), the
        # loop above would pass vacuously.
        for must in ("/api/calibration/sessions", "/api/gaze/models/{session_id}/train",
                     "/api/attribution/analyze", "/api/render/capture"):
            check(f"{must} was probed", any(p == must for _, p in probed))

        # --------------------------------------------------------------
        print("\ncalibration -- sessions belong to whoever started them")
        r = client.post("/api/calibration/sessions", headers=alice, json={
            "participant_id": "p_alice", "pattern": 9,
            "screen_width": 1280, "screen_height": 720,
        })
        check("alice starts a calibration -> 201", r.status_code == 201)
        cal_id = r.json()["session_id"]
        on_disk = json.loads((cal_dir / f"{cal_id}.json").read_text())
        check("owner recorded on disk", on_disk.get("owner_id") == alice_id)

        check("alice reads it -> 200",
              client.get(f"/api/calibration/sessions/{cal_id}", headers=alice).status_code == 200)
        check("bob reads it -> 404",
              client.get(f"/api/calibration/sessions/{cal_id}", headers=bob).status_code == 404)
        check("bob submits samples -> 404",
              client.post(f"/api/calibration/sessions/{cal_id}/samples", headers=bob,
                          json={"point_index": 0, "frames": ["x"]}).status_code == 404)
        check("bob completes it -> 404",
              client.post(f"/api/calibration/sessions/{cal_id}/complete",
                          headers=bob).status_code == 404)
        check("bob deletes it -> 404",
              client.delete(f"/api/calibration/sessions/{cal_id}", headers=bob).status_code == 404)
        check("...and it survived bob's delete", (cal_dir / f"{cal_id}.json").exists())

        alice_list = {s["session_id"] for s in
                      client.get("/api/calibration/sessions", headers=alice).json()}
        bob_list = client.get("/api/calibration/sessions", headers=bob).json()
        check("alice's listing has it", cal_id in alice_list)
        check("bob's listing is empty", bob_list == [])
        check("owner_id isn't leaked in the listing",
              all("owner_id" not in s for s in
                  client.get("/api/calibration/sessions", headers=alice).json()))

        check("bob can't link alice's calibration to his own session",
              client.post("/api/sessions", headers=bob, json={
                  "mode": "test_ui", "ui_page": "form_page",
                  "calibration_session_id": cal_id,
              }).status_code == 404)

        # --------------------------------------------------------------
        print("\ngaze models -- scoped to the calibration's owner")
        trained = generate_calibration_session(pattern=16, samples_per_point=12,
                                               participant_id="p_alice_2", seed=3)
        trained.owner_id = alice_id
        store.save(trained)
        tid = trained.session_id

        check("bob trains on alice's calibration -> 404",
              client.post(f"/api/gaze/models/{tid}/train", headers=bob).status_code == 404)
        check("alice trains -> 200",
              client.post(f"/api/gaze/models/{tid}/train", headers=alice).status_code == 200)
        check("alice reads her model -> 200",
              client.get(f"/api/gaze/models/{tid}", headers=alice).status_code == 200)
        check("bob reads it -> 404",
              client.get(f"/api/gaze/models/{tid}", headers=bob).status_code == 404)
        est = {"left": {"x": 0.5, "y": 0.5}}
        check("bob estimates with it -> 404",
              client.post(f"/api/gaze/models/{tid}/estimate", headers=bob,
                          json=est).status_code == 404)
        check("bob batch-estimates with it -> 404",
              client.post(f"/api/gaze/models/{tid}/estimate/batch", headers=bob,
                          json={"frames": [est]}).status_code == 404)
        check("bob validates against it -> 404",
              client.post(f"/api/gaze/models/{tid}/validate", headers=bob, json={
                  "point_index": 0, "target_x": 0.5, "target_y": 0.5, "frames": ["x"],
              }).status_code == 404)
        check("bob deletes it -> 404",
              client.delete(f"/api/gaze/models/{tid}", headers=bob).status_code == 404)
        check("alice's model list has it",
              any(m["session_id"] == tid for m in
                  client.get("/api/gaze/models", headers=alice).json()))
        check("bob's model list is empty",
              client.get("/api/gaze/models", headers=bob).json() == [])
        check("alice estimates -> 200",
              client.post(f"/api/gaze/models/{tid}/estimate", headers=alice,
                          json=est).status_code == 200)

        # --------------------------------------------------------------
        print("\nlegacy calibrations -- no owner_id on disk")
        legacy = generate_calibration_session(pattern=9, samples_per_point=12,
                                              participant_id="p_legacy", seed=4)
        legacy_dict = legacy.to_dict()
        legacy_dict.pop("owner_id", None)
        cal_dir.mkdir(parents=True, exist_ok=True)
        (cal_dir / f"{legacy.session_id}.json").write_text(json.dumps(legacy_dict))
        lid = legacy.session_id

        check("unlinked legacy calibration is hidden from alice -> 404",
              client.get(f"/api/calibration/sessions/{lid}", headers=alice).status_code == 404)
        check("...and from her listing",
              lid not in {s["session_id"] for s in
                          client.get("/api/calibration/sessions", headers=alice).json()})
        check("alice can't claim it by naming it in a new session -> 404",
              client.post("/api/sessions", headers=alice, json={
                  "mode": "test_ui", "ui_page": "form_page",
                  "calibration_session_id": lid,
              }).status_code == 404)

        # A link made before this change: the session row is the only record
        # of whose calibration it is.
        with SessionLocal() as db:
            db.add(SessionModel(user_id=alice_id, mode="test_ui", ui_page="form_page",
                                status="calibrated", calibration_session_id=lid,
                                element_layout={}))
            db.commit()
        check("legacy calibration linked to alice's session -> 200 for alice",
              client.get(f"/api/calibration/sessions/{lid}", headers=alice).status_code == 200)
        check("...listed for her",
              lid in {s["session_id"] for s in
                      client.get("/api/calibration/sessions", headers=alice).json()})
        check("...still 404 for bob",
              client.get(f"/api/calibration/sessions/{lid}", headers=bob).status_code == 404)
        check("...and its gaze model trains for alice only",
              client.post(f"/api/gaze/models/{lid}/train", headers=bob).status_code == 404
              and client.post(f"/api/gaze/models/{lid}/train",
                              headers=alice).status_code == 200)

finally:
    set_store(None)
    set_model_dir(None)
    ge_training.MODEL_DIR = _saved_model_dir
    shutil.rmtree(_TMP, ignore_errors=True)


print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
