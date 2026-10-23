"""
e2e_check.py

End-to-end check of the whole app over real HTTP.

    python scripts/e2e_check.py            # API only
    python scripts/e2e_check.py --web      # also start the Vite app and check it proxies the API
    python scripts/e2e_check.py --offline  # skip the checks that need the internet

It starts its OWN API (and web app) on free ports, with a throwaway database and
data folders in a temp directory, so it never touches real accounts or
participant data. Everything is shut down at the end. Exit code 0 = all checks
passed.

WHAT IT COVERS
--------------
  * accounts: sign-up, login, duplicates, weak passwords, bad tokens
  * every protected route refuses anonymous callers (401)
  * a real face photo through MediaPipe via the calibration API
  * full flow on a sample page: calibration -> trained gaze model -> gaze
    stream -> analysis -> report (must flag the element nobody looked at) ->
    heatmap, eye path, PDF
  * full flow on live websites captured by headless Chromium
  * one live webcam frame -> gaze point
  * another user can't see, download or delete your data
  * URL capture refuses loopback / private / cloud-metadata addresses
  * crash recovery: a report stuck past the timeout is marked failed and can
    be retried; a restart mid-analysis marks it "interrupted"
  * failed-login lockout (429)

WHAT IT DOESN'T
---------------
There is no webcam in an automated run, so the calibration's eye features are
synthetic -- the same generator the unit tests use -- written through the
server's own storage layer. Everything after that (training, accuracy gate,
gaze, analysis, report, PDF) runs through the real HTTP API. The live-frame
check uses MediaPipe's public sample portrait, so it proves the CV path runs,
not that the gaze position is right. Real accuracy needs a person; see
OPEN_ITEMS.md section 1.

Needs the server install (requirements-dev.txt), `playwright install chromium`
and models/face_landmarker.task (fetched automatically if missing). --web also
needs `npm install` in frontend-new.
"""

import argparse
import base64
import json
import os
import random
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

PORTRAIT_URL = "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"
MAX_LOGIN_FAILURES = 3

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    return bool(ok)


def section(title):
    print(f"\n== {title}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url, seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


class Stack:
    """The API (and optionally the web app) on throwaway data."""

    def __init__(self, tmp: Path, with_web: bool):
        self.tmp = tmp
        self.data = tmp / "data"
        self.api_port = free_port()
        self.web_port = free_port() if with_web else None
        self.api = None
        self.web = None
        self.env = dict(
            os.environ,
            FIXATION_DATABASE_URL=f"sqlite:///{(self.data / 'e2e.db').as_posix()}",
            FIXATION_DATA_DIR=str(self.data / "sessions"),
            GAZELENS_CALIBRATION_DIR=str(self.data / "calibration"),
            GAZELENS_GAZE_MODEL_DIR=str(self.data / "models"),
            GAZELENS_SECRET_KEY="e2e-only-key-not-for-deployment-0123456789abcdef",
            GAZELENS_LOGIN_MAX_FAILURES=str(MAX_LOGIN_FAILURES),
            GAZELENS_LLM="off",
            PYTHONUNBUFFERED="1",
        )

    @property
    def api_url(self):
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def web_url(self):
        return f"http://localhost:{self.web_port}"

    @property
    def db(self):
        return self.data / "e2e.db"

    def start_api(self):
        self.data.mkdir(parents=True, exist_ok=True)
        log = open(self.tmp / "api.log", "ab")
        self.api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(self.api_port)],
            cwd=BACKEND, env=self.env, stdout=log, stderr=subprocess.STDOUT,
        )
        if not wait_for(self.api_url + "/health"):
            raise SystemExit(f"API didn't start; see {self.tmp / 'api.log'}")

    def stop_api(self):
        if self.api and self.api.poll() is None:
            self.api.terminate()
            try:
                self.api.wait(15)
            except subprocess.TimeoutExpired:
                self.api.kill()

    def start_web(self):
        web_dir = REPO / "frontend-new"
        if not (web_dir / "node_modules").exists():
            raise SystemExit("--web needs `npm install` in frontend-new first")
        log = open(self.tmp / "web.log", "ab")
        self.web = subprocess.Popen(
            ["npx", "vite", "--port", str(self.web_port), "--strictPort"],
            cwd=web_dir, env=dict(os.environ, VITE_PROXY_TARGET=self.api_url),
            stdout=log, stderr=subprocess.STDOUT,
        )
        if not wait_for(self.web_url + "/"):
            raise SystemExit(f"web app didn't start; see {self.tmp / 'web.log'}")

    def stop(self):
        self.stop_api()
        if self.web and self.web.poll() is None:
            self.web.terminate()
            try:
                self.web.wait(15)
            except subprocess.TimeoutExpired:
                self.web.kill()


def ensure_face_model():
    if not (REPO / "models" / "face_landmarker.task").exists():
        print("models/face_landmarker.task missing -- fetching it")
        subprocess.run([sys.executable, str(REPO / "scripts" / "fetch_face_landmarker.py")], check=True)


def portrait_b64(tmp: Path, offline: bool):
    if offline:
        return None
    dest = tmp / "portrait.jpg"
    try:
        urllib.request.urlretrieve(PORTRAIT_URL, dest)
        return base64.b64encode(dest.read_bytes()).decode()
    except OSError as exc:
        print(f"  (couldn't download the sample portrait: {exc}; skipping the real-face checks)")
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    ap.add_argument("--web", action="store_true", help="also start the web app and check its API proxy")
    ap.add_argument("--offline", action="store_true", help="skip checks that need the internet")
    ap.add_argument("--keep", action="store_true", help="keep the temp folder (logs, DB, reports)")
    args = ap.parse_args()

    ensure_face_model()
    tmp = Path(tempfile.mkdtemp(prefix="gazelens_e2e_"))
    stack = Stack(tmp, args.web)
    try:
        stack.start_api()
        if args.web:
            stack.start_web()
        run_checks(stack, portrait_b64(tmp, args.offline), args)
    finally:
        stack.stop()
        if args.keep:
            print(f"\nkept: {tmp}")
        else:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(ok for _, ok, _ in results)
    print(f"\n{'=' * 50}\nE2E: {passed}/{len(results)} checks passed")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name} {detail}")
    return 0 if passed == len(results) else 1


def run_checks(stack: Stack, frame_b64, args):
    from calibration.storage import CalibrationStore
    from gaze_estimation.synthetic import generate_calibration_session

    c = httpx.Client(base_url=stack.api_url, timeout=180)
    rnd = random.Random(7)

    # ------------------------------------------------------------ health
    section("health")
    h = c.get("/health").json()
    check("API healthy", h.get("status") == "ok")
    check("eye tracking available (MediaPipe model loaded)", h.get("cv_available") is True)
    if args.web:
        w = httpx.get(stack.web_url + "/", timeout=30)
        check("web app serves the app shell", w.status_code == 200 and 'id="root"' in w.text)
        wp = httpx.get(stack.web_url + "/health", timeout=30)
        check("web app proxies /health to the API", wp.status_code == 200 and wp.json().get("status") == "ok")
        wl = httpx.post(stack.web_url + "/api/auth/login", timeout=30,
                        json={"email": "nobody@example.com", "password": "wrong-pass-1"})
        check("web app proxies /api to the API", wl.status_code == 401)

    # ------------------------------------------------------------ accounts
    section("accounts and login")
    r = c.post("/api/auth/signup", json={"email": "alice@example.com", "full_name": "Alice", "password": "Garden-Lamp-41"})
    check("sign up", r.status_code == 201, r.text[:200])
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("duplicate sign-up refused (409)",
          c.post("/api/auth/signup", json={"email": "ALICE@example.com", "full_name": "Alice", "password": "Garden-Lamp-41"}).status_code == 409)
    check("short password refused (422)",
          c.post("/api/auth/signup", json={"email": "carol@example.com", "full_name": "Carol", "password": "short"}).status_code == 422)
    check("login works",
          c.post("/api/auth/login", json={"email": "alice@example.com", "password": "Garden-Lamp-41"}).status_code == 200)
    me = c.get("/api/auth/me", headers=A).json()
    check("/me returns the user", me.get("email") == "alice@example.com")
    check("garbage token refused (401)", c.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401)
    r = c.post("/api/auth/signup", json={"email": "bob@example.com", "full_name": "Bob", "password": "River-Stone-82"})
    B = {"Authorization": f"Bearer {r.json()['access_token']}"}

    section("routes refuse anonymous callers")
    for method, path, body in [
        ("GET", "/api/sessions", None),
        ("POST", "/api/sessions", {"mode": "test_ui", "ui_page": "form_page"}),
        ("GET", "/api/calibration/sessions", None),
        ("POST", "/api/calibration/sessions", {"participant_id": "p", "screen_width": 100, "screen_height": 100}),
        ("GET", "/api/gaze/models", None),
        ("POST", "/api/render/capture", {"url": "https://example.com"}),
        ("POST", "/api/attribution/analyze", {}),
    ]:
        code = c.request(method, path, json=body).status_code
        check(f"{method} {path} without login -> 401", code == 401, f"got {code}")

    # ------------------------------------------------------------ real face
    if frame_b64:
        section("real face through MediaPipe over HTTP")
        r = c.post("/api/calibration/sessions", headers=A,
                   json={"participant_id": "e2e-face", "pattern": 9, "screen_width": 1694,
                         "screen_height": 840, "samples_per_point": 3})
        check("start calibration", r.status_code == 201, r.text[:200])
        real_cal = r.json()["session_id"]
        r = c.post(f"/api/calibration/sessions/{real_cal}/samples", headers=A,
                   json={"point_index": 0, "frames": [frame_b64] * 3})
        body = r.json() if r.status_code == 200 else {}
        check("calibration frames accepted", r.status_code == 200, r.text[:300])
        check("MediaPipe found the face and eyes in the photo", body.get("accepted", 0) > 0, str(body)[:300])
        check("bob can't read alice's calibration (404)",
              c.get(f"/api/calibration/sessions/{real_cal}", headers=B).status_code == 404)
        check("bob's calibration list doesn't show it",
              all(s.get("session_id") != real_cal for s in c.get("/api/calibration/sessions", headers=B).json()))

    # ------------------------------------------------------------ helpers
    store = CalibrationStore(data_dir=stack.data / "calibration")

    def seed_calibration(seed):
        """No webcam here: synthetic eye features, as the unit tests use."""
        s = generate_calibration_session(pattern=16, samples_per_point=12, participant_id="e2e", seed=seed)
        s.owner_id = me["id"]
        store.save(s)
        return s.session_id

    def fixation_stream(boxes, secs_each=2.0, hz=30):
        """Gaze dwelling inside each box in turn, with webcam-like jitter."""
        pts, t = [], 1000.0
        for (x, y, w, hh) in boxes:
            for _ in range(int(secs_each * hz)):
                pts.append({"timestamp": round(t, 3),
                            "x": min(1, max(0, x + w / 2 + rnd.gauss(0, w * 0.12))),
                            "y": min(1, max(0, y + hh / 2 + rnd.gauss(0, hh * 0.12))),
                            "valid": True, "confidence": 0.9, "scroll_x": 0, "scroll_y": 0})
                t += 1 / hz
        return pts

    def layout_of(sid):
        con = sqlite3.connect(stack.db)
        try:
            return json.loads(con.execute("select element_layout from sessions where id=?", (sid,)).fetchone()[0])
        finally:
            con.close()

    def page_layout(name):
        return json.loads((REPO / "test_uis" / name / "elements.json").read_text())

    def wait_report(sid, seconds=240):
        t0 = time.time()
        while time.time() - t0 < seconds:
            rr = c.get(f"/api/sessions/{sid}/report", headers=A)
            if rr.status_code == 200:
                return rr.json(), round(time.time() - t0, 1)
            if rr.status_code != 202:
                return None, f"{rr.status_code} {rr.text[:200]}"
            time.sleep(1.0)
        return None, "timed out"

    def run_flow(label, create_body, gaze_for, expect_issues=True):
        section(label)
        r = c.post("/api/sessions", headers=A, json=create_body)
        if not check("create session", r.status_code == 201, r.text[:300]):
            return None, None
        sid = r.json()["id"]
        check("layout comes from the real page (not a placeholder)",
              r.json().get("layout_is_placeholder") is False, str(r.json())[:200])
        r = c.post(f"/api/sessions/{sid}/calibration", headers=A,
                   json={"calibration_session_id": seed_calibration(rnd.randint(1, 10_000))})
        link = r.json() if r.status_code == 200 else {}
        check("linking a calibration trains a real gaze model", link.get("gaze_model_trained") is True, r.text[:300])
        check("training reports held-out error",
              (link.get("gaze_model_metrics") or {}).get("median_error_px", 0) > 0)
        pts = gaze_for(sid)
        r = c.post(f"/api/sessions/{sid}/gaze", headers=A, json={"gaze": pts})
        check(f"gaze stream accepted ({len(pts)} points)",
              r.status_code in (200, 201) and r.json().get("accepted") == len(pts), r.text[:200])
        r = c.post(f"/api/sessions/{sid}/finalize", headers=A)
        check("finalize starts the analysis", r.status_code in (200, 202), r.text[:200])
        rep, secs = wait_report(sid)
        if not check(f"report finished ({secs}s)", rep is not None, str(secs)):
            return sid, None
        pr = rep["pipeline_result"]
        check("session marked complete", c.get(f"/api/sessions/{sid}", headers=A).json()["status"] == "complete")
        check("per-element metrics computed", bool(rep.get("metrics")))
        check("behaviour summary and quality gate present",
              bool(pr.get("behavior_summary")) and pr.get("quality") is not None)
        issues, kept = pr.get("issues") or [], pr.get("recommendations_kept") or []
        if expect_issues:
            check(f"issues found ({len(issues)}) with fixes kept by the critic ({len(kept)})",
                  len(issues) > 0 and len(kept) > 0)
        else:
            check(f"even attention -> no forced findings ({len(issues)} issues)", len(issues) == 0)
        for kind in ("heatmap", "scanpath"):
            img = c.get(f"/api/sessions/{sid}/{kind}", headers=A)
            check(f"{kind} image served", img.status_code == 200 and img.content[:4] == b"\x89PNG")
        pdf = c.get(f"/api/sessions/{sid}/pdf", headers=A)
        check(f"PDF served ({len(pdf.content) // 1024} KB, {rep.get('pdf_backend')})",
              pdf.status_code == 200 and pdf.content[:5] == b"%PDF-")
        check("bob can't open alice's report (404)", c.get(f"/api/sessions/{sid}/report", headers=B).status_code == 404)
        check("bob can't download alice's PDF (404)", c.get(f"/api/sessions/{sid}/pdf", headers=B).status_code == 404)
        return sid, rep

    # ------------------------------------------------------------ sample page
    form = page_layout("form_page")
    sid, rep = run_flow("full flow: sample page (form; the Submit button is never looked at)",
                        {"mode": "test_ui", "ui_page": "form_page", "label": "e2e form"},
                        lambda sid: fixation_stream([v["bbox"] for k, v in form.items() if k != "submit_button"] * 2))
    if rep:
        flagged = {i.get("element_id") for i in rep["pipeline_result"].get("issues", [])}
        check("report flags the ignored Submit button", "submit_button" in flagged, str(flagged))

    # ------------------------------------------------------------ uploaded screenshot
    # A tall 1200x2400 image shown in a 1200x675 window, as the web app does.
    # "Reviews" is only visible after scrolling, so it collects gaze only if
    # the scroll offset is mapped onto the image; "Buy now" is never looked at.
    import base64 as _b64
    import io as _io
    import struct as _struct

    from PIL import Image as _Image, ImageDraw as _Draw

    IMG_W, IMG_H, VIEW_H = 1200, 2400, 675
    drawn = [
        {"label": "Hero photo", "type": "image", "importance": "medium", "bbox": [0.05, 0.06, 0.45, 0.15]},
        {"label": "Buy now", "type": "CTA", "importance": "high", "bbox": [0.55, 0.10, 0.30, 0.05]},
        {"label": "Product details", "type": "text", "importance": "medium", "bbox": [0.05, 0.40, 0.90, 0.10]},
        {"label": "Reviews", "type": "text", "importance": "medium", "bbox": [0.05, 0.75, 0.90, 0.10]},
    ]
    shot = _Image.new("RGB", (IMG_W, IMG_H), (244, 244, 244))
    pen = _Draw.Draw(shot)
    for b in drawn:
        x, y, w, h = b["bbox"]
        pen.rectangle([x * IMG_W, y * IMG_H, (x + w) * IMG_W, (y + h) * IMG_H], fill=(170, 180, 200))
    buf = _io.BytesIO()
    shot.save(buf, format="JPEG")
    shot_b64 = "data:image/jpeg;base64," + _b64.b64encode(buf.getvalue()).decode()

    def scrolled_gaze(sid):
        """Look at each box except Buy now, scrolling so each is mid-window."""
        pts, t = [], 2000.0
        for b in drawn:
            if b["label"] == "Buy now":
                continue
            x, y, w, h = b["bbox"]
            cy_px = (y + h / 2) * IMG_H
            scroll = min(max(cy_px - VIEW_H / 2, 0), IMG_H - VIEW_H)
            for _ in range(int(2.5 * 30)):
                py = cy_px + rnd.gauss(0, h * IMG_H * 0.12)
                pts.append({"timestamp": round(t, 3),
                            "x": min(1, max(0, x + w / 2 + rnd.gauss(0, w * 0.12))),
                            "y": min(1, max(0, (py - scroll) / VIEW_H)),
                            "valid": True, "confidence": 0.9, "scroll_x": 0, "scroll_y": scroll})
                t += 1 / 30
        return pts

    sid, rep = run_flow("full flow: uploaded screenshot with hand-drawn boxes (tall, scrolled)",
                        {"mode": "image", "label": "e2e checkout mock-up",
                         "image_base64": shot_b64, "elements": drawn},
                        scrolled_gaze)
    if rep:
        flagged = {i.get("element_id") for i in rep["pipeline_result"].get("issues", [])}
        check("report flags the ignored Buy now button", "buy_now" in flagged, str(flagged))
        dwell = (rep.get("metrics") or {}).get("dwell_time") or {}
        check(f"below-the-fold Reviews got gaze via scroll mapping ({dwell.get('reviews', 0):.1f}s)",
              dwell.get("reviews", 0) > 1.0, str(dwell))
        labels = rep["pipeline_result"].get("element_labels") or {}
        check("report uses the names drawn on the image",
              labels.get("buy_now") == "Buy now" and labels.get("reviews") == "Reviews", str(labels))
        check("report says the boxes were drawn by the tester",
              any("drawn by the tester" in w for w in rep.get("warnings") or []), str(rep.get("warnings")))
        heat = c.get(f"/api/sessions/{sid}/heatmap", headers=A).content
        hw, hh = _struct.unpack(">II", heat[16:24])
        check(f"heatmap drawn over the tall uploaded image ({hw}x{hh})", hh > 1.5 * hw)
        listed = [s for s in c.get("/api/sessions", headers=A).json().get("sessions", []) if s["id"] == sid]
        check("dashboard lists it under its own name",
              bool(listed) and listed[0].get("label") == "e2e checkout mock-up" and listed[0].get("mode") == "image")
    check("a non-image upload is refused (422)",
          c.post("/api/sessions", headers=A, json={"mode": "image", "elements": drawn,
                 "image_base64": _b64.b64encode(b"not an image").decode()}).status_code == 422)
    check("an upload with no boxes is refused (422)",
          c.post("/api/sessions", headers=A, json={"mode": "image", "image_base64": shot_b64}).status_code == 422)
    r = c.post("/api/render/detect-image", headers=A, json={"image_base64": shot_b64})
    found_boxes = r.json().get("elements", []) if r.status_code == 200 else []
    check(f"automatic detection suggests boxes for the upload ({len(found_boxes)})",
          r.status_code == 200 and len(found_boxes) >= 3
          and all(e["type"] in ("CTA", "text", "image", "nav", "non-interactive") for e in found_boxes),
          r.text[:200])
    check("automatic detection needs login (401)",
          c.post("/api/render/detect-image", json={"image_base64": shot_b64}).status_code == 401)
    check("upload needs login (401)",
          c.post("/api/sessions", json={"mode": "image", "image_base64": shot_b64, "elements": drawn}).status_code == 401)

    # ------------------------------------------------------------ live websites
    if not args.offline:
        def look_at_all(sid):
            layout = layout_of(sid)
            check(f"Chromium captured the page and detected elements ({len(layout)})", len(layout) > 0)
            return fixation_stream([v["bbox"] for v in layout.values()][:4], secs_each=2.5)

        run_flow("full flow: live website (https://example.com), even attention",
                 {"mode": "url", "target_url": "https://example.com", "label": "e2e example.com"},
                 look_at_all, expect_issues=False)

        def skip_key_elements(sid):
            layout = layout_of(sid)
            check(f"Chromium captured the page and detected elements ({len(layout)})", len(layout) >= 5)
            high = {k for k, v in layout.items() if v.get("importance") == "high"}
            return fixation_stream([v["bbox"] for k, v in layout.items() if k not in high][:3], secs_each=3)

        run_flow("full flow: richer live website (https://www.wikipedia.org), key elements skipped",
                 {"mode": "url", "target_url": "https://www.wikipedia.org", "label": "e2e wikipedia"},
                 skip_key_elements)

    # ------------------------------------------------------------ URL safety
    section("URL capture safety")
    for bad in (f"http://127.0.0.1:{stack.api_port}/health", f"http://localhost:{stack.api_port}/docs",
                "http://169.254.169.254/latest/meta-data"):
        code = c.post("/api/render/capture", headers=A, json={"url": bad}).status_code
        check(f"capture of {bad} refused", code in (400, 403, 422), f"got {code}")

    # ------------------------------------------------------------ live frame
    r = c.post("/api/sessions", headers=A, json={"mode": "test_ui", "ui_page": "article_page"})
    sid_live = r.json()["id"]
    c.post(f"/api/sessions/{sid_live}/calibration", headers=A, json={"calibration_session_id": seed_calibration(3)})
    if frame_b64:
        section("live webcam frame over HTTP")
        r = c.post(f"/api/sessions/{sid_live}/gaze/frame", headers=A,
                   json={"frame": frame_b64, "timestamp": 1.0,
                         "stage": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}, "scroll_y": 0})
        pt = (r.json() or {}).get("gaze", {}) if r.status_code == 200 else {}
        check("frame -> gaze point", r.status_code == 200 and "x" in pt and "y" in pt, r.text[:300])
        check("frame stored in the session's gaze stream",
              c.get(f"/api/sessions/{sid_live}", headers=A).json().get("gaze_point_count", 0) >= 1)

    # ------------------------------------------------------------ recovery: timeout
    section("crash recovery: stuck past the timeout")

    def prepared_session(page):
        r = c.post("/api/sessions", headers=A, json={"mode": "test_ui", "ui_page": page})
        sid = r.json()["id"]
        c.post(f"/api/sessions/{sid}/calibration", headers=A,
               json={"calibration_session_id": seed_calibration(rnd.randint(1, 10_000))})
        c.post(f"/api/sessions/{sid}/gaze", headers=A,
               json={"gaze": fixation_stream([v["bbox"] for v in page_layout(page).values()])})
        return sid

    def mark_processing(sid, started):
        con = sqlite3.connect(stack.db)
        ts = started.strftime("%Y-%m-%d %H:%M:%S.%f")
        con.execute("update sessions set status='processing', processing_started_at=?, started_at=? where id=?",
                    (ts, ts, sid))
        con.commit()
        con.close()

    sid_t = prepared_session("login_page")
    mark_processing(sid_t, datetime.now(timezone.utc) - timedelta(hours=1))   # a worker that died an hour ago
    s = c.get(f"/api/sessions/{sid_t}", headers=A).json()
    check("stale 'processing' session reported as failed", s["status"] == "failed", str(s)[:200])
    check("with a 'please retry' message", "please retry" in (s.get("error") or ""), s.get("error"))
    check("retry accepted", c.post(f"/api/sessions/{sid_t}/finalize", headers=A).status_code in (200, 202))
    rep, secs = wait_report(sid_t)
    check("retry produces a complete report", rep is not None, str(secs))

    # ------------------------------------------------------------ recovery: restart
    section("crash recovery: server restarted mid-analysis")
    sid_r = prepared_session("dashboard_page")
    mark_processing(sid_r, datetime.now(timezone.utc))
    stack.stop_api()
    stack.start_api()        # also clears the in-memory login limiter
    s = c.get(f"/api/sessions/{sid_r}", headers=A).json()
    check("after a restart the session is failed, not stuck", s["status"] == "failed", str(s)[:200])
    check("with an 'interrupted, please retry' message", "interrupted" in (s.get("error") or ""), s.get("error"))
    check("logins survive the restart (same signing key)", c.get("/api/auth/me", headers=A).status_code == 200)

    # ------------------------------------------------------------ dashboard + delete
    section("dashboard data and delete")
    lst = c.get("/api/sessions", headers=A).json()
    check("alice sees her sessions", lst.get("total", 0) >= 4, str(lst)[:200])
    check("bob sees none of them", c.get("/api/sessions", headers=B).json().get("total") == 0)
    check("bob can't delete alice's session (404)", c.delete(f"/api/sessions/{sid_live}", headers=B).status_code == 404)
    check("alice deletes a session", c.delete(f"/api/sessions/{sid_live}", headers=A).status_code in (200, 204))
    check("deleted session is gone (404)", c.get(f"/api/sessions/{sid_live}", headers=A).status_code == 404)

    # ------------------------------------------------------------ lockout (last: blocks this client)
    section("login rate limiting")
    codes = [c.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-pass-1"}).status_code
             for _ in range(MAX_LOGIN_FAILURES)]
    check("wrong passwords -> 401", codes == [401] * MAX_LOGIN_FAILURES, str(codes))
    blocked = c.post("/api/auth/login", json={"email": "alice@example.com", "password": "Garden-Lamp-41"})
    check("then 429 with Retry-After, even with the right password",
          blocked.status_code == 429 and blocked.headers.get("retry-after"))


if __name__ == "__main__":
    sys.exit(main())
