# GazeLens
### *Built on the GazeUX-Agent framework — a webcam-based, multi-agent framework for gaze-driven UI/UX evaluation*

GazeLens turns an ordinary laptop webcam into a low-cost usability-testing tool. It tracks where someone actually looks while using a web page (or any live URL), maps that attention to specific UI elements, and runs it through a chain of evidence-grounded AI agents that produce a UX report a designer can act on — not a vague "make it better," but "the checkout button got 2% of total gaze time against a 5% threshold, here's the fix, here's the confidence score, here's why the system believes it."

---

## Why this exists

Proper eye-tracking hardware is expensive, and even when you have gaze data, someone still has to manually work out *why* a design failed. GazeLens closes that gap with three concrete contributions:

1. **A benchmarked, swappable pupil detector** — comparing YOLOv8, SSD300, and Faster R-CNN on the same dataset, evaluated on precision, recall, mAP@0.5, and inference speed — not just accuracy.
2. **Gaze-to-UI-element attribution** — converting raw gaze coordinates into per-element metrics (dwell time, time-to-first-fixation, revisit count, scanpath), not just a heatmap.
3. **A traceable multi-agent reasoning layer** — Behavior → UX Evaluation → Recommendation → Critic/Verifier, where every claim must cite a real metric, and a dedicated verifier agent rejects anything it can't independently re-derive from raw data.

---

## Detector benchmark results

All three trained and evaluated on the same dataset (130,856 images). Full table in `runs/eval/final_comparison.csv`.

| Model | Precision | Recall | mAP@0.5 | FPS |
|---|---|---|---|---|
| **YOLOv8n** | 0.972 | **0.944** | 0.972 | **625** |
| Faster R-CNN | 0.926 | 0.938 | 0.954 | 23.3 |
| SSD300 | **0.991** | 0.869 | **0.975** | 127.1 |

**Chosen for the live pipeline: YOLOv8n.** SSD edges it slightly on precision/mAP, but has meaningfully lower recall — for a continuous webcam gaze stream, a missed detection creates a gap in the data, which matters more than an occasional imprecise box. YOLO matches SSD's accuracy almost exactly while catching more real detections and running ~5–27x faster, which is decisive for a real-time constraint.

**⚠️ Known limitation — these numbers are measured on training data.** `configs/lpw.yaml` points `train` and `val` at the same folder, so the table above reports memorisation, not generalisation.

A subject-wise split now exists (`scripts/make_lpw_split.py` → `configs/lpw_subject_split.yaml`): 16 train / 3 val / 3 test subjects, sharing no frames. Splitting by *subject* rather than by frame matters — LPW is 22 subjects × 3 videos, so a random frame split puts near-duplicate consecutive frames on both sides.

`scripts/evaluate_split_gap.py` evaluates one model both ways and reports the difference. **Re-run it against `pupil_yolo_final.pt` and replace the table before publication** — and note that model saw all 22 subjects, so an honest held-out number needs a retrain on the split config. See [OPEN_ITEMS.md](OPEN_ITEMS.md) §4.

---

## Architecture

```
backend/
├── agents/            ✅ built + tested — behavior analysis, heuristic evaluation,
│                          recommendation generation, critic/verification
├── reports/            ✅ built + tested — HTML/PDF report generation from agent output
├── api/                 ✅ built + tested — FastAPI: JWT auth, session lifecycle,
│                          SQLite/SQLAlchemy, and the orchestration that runs
│                          the whole pipeline (see its CONTRACT.md)
├── render/              ✅ built + tested — arbitrary-URL screenshot + auto element
│                          detection (Playwright/Chromium). Labels are heuristics,
│                          not design intent — see its CONTRACT.md
├── cv/                  ✅ built + tested — MediaPipe eye landmarking -> YOLOv8n pupil
│                          localisation, CPU-only, frame-in/coords-out
├── calibration/         ✅ built + tested — 9/16-point data collection endpoint,
│                          persists training-ready rows (see calibration/CONTRACT.md)
├── gaze_estimation/     ✅ built + tested — per-session pupil → screen regression,
│                          leave-one-point-out accuracy (see its CONTRACT.md)
├── attribution/         ✅ built + tested — gaze → UI element metrics
│                          (dwell/TTFF/fixations/scanpath), feeds the agent chain
└── db/                  ✅ built + tested — folded into api/ (models.py, db.py):
                           users, sessions, reports on SQLite/SQLAlchemy

frontend/                 ✅ built — React app: landing, sign-in/up, calibration UI, live
                              session UI (fixed test pages + arbitrary URL mode), dashboard,
                              report view. Session/report data currently mocked
                              (frontend/src/api/client.js) pending backend/api session endpoints.

configs/, dataset/, evaluation/, LPW/, models/, scripts/, training/
                          ✅ detector training + evaluation complete for all 3 models
test_uis/                 ⏳ open — the 5 real test UI pages (currently placeholders in Live Session)
```

> **📋 Open items with concrete next steps: [OPEN_ITEMS.md](OPEN_ITEMS.md)** —
> the real detector weights, first-participant validation, the frontend
> contract, and the train==val benchmark split.
>
> **⚠️ `frontend/` is still not in this repo.** It has never been pushed to
> `origin/main`, so a fresh clone gets the whole backend and no frontend at
> all. The one consequence you will hit: **`frontend/src/api/client.js`
> doesn't exist**, so the session API's request/response shapes were defined
> server-side rather than matched to the client. See
> `backend/api/CONTRACT.md` for exactly what to check when it lands — the
> provisional parts are confined to `schemas.py` and the route prefixes.
>
> `backend/api/` and `backend/render/` were both described as built but never
> pushed; both have now been written here. `scripts/generate_api_client.py`
> emits a reference client + OpenAPI spec to diff the real `client.js`
> against.

**Pipeline, end to end:**

```
Webcam → Face/Eye Landmarking → Pupil Detection (YOLOv8n) → Gaze Estimation
       → Gaze-to-UI Attribution → Metrics + Heatmap
       → Agent Chain (Behavior → Evaluation → Recommendation → Critic)
       → PDF/HTML Report + Dashboard
```

---

## Current status

| Module | Status | Notes |
|---|---|---|
| Pupil detection (YOLO / SSD / Faster R-CNN) | ✅ Done | Trained + evaluated, all 3, full benchmark table above |
| Live webcam integration | ✅ Done | `backend/cv/` — wraps `models/pupil_yolo_final.pt`, the winning detector |
| Calibration | ✅ Done | `backend/calibration/` — endpoint + storage. **Not yet reconciled with `Calibration.jsx`**, which isn't in this repo (see below) |
| Gaze estimation | ✅ Done | `backend/gaze_estimation/` — per-session polynomial ridge, degree auto-selected by leave-one-point-out CV. Validated on synthetic sessions only; no real participant data exists yet |
| UI attribution + metrics | ✅ Done | `backend/attribution/` — gaze + bboxes → `SessionMetrics`, piped end-to-end into the agent chain in its test suite |
| Heatmap rendering | ⏳ Open | `reports/heatmap_stub.py` still a stub; `attribution` now supplies the real layout + dwell data it needs |
| Agent chain (behavior/evaluation/recommendation/critic) | ✅ Done | Fully tested against mock session data |
| Report generation | ✅ Done | Generates PDF/HTML reports, tested against multiple scenarios |
| Arbitrary-URL rendering | ✅ Done | `backend/render/` — Chromium screenshot + DOM element detection. Element **types are inferred**, not authored; every capture reports `low_confidence_fraction` and reports say so |
| Session/report API endpoints | ✅ Done | `backend/api/` — full lifecycle, ownership-scoped. **Not yet reconciled with `client.js`**, which isn't in this repo |
| Auth (signup/login) | ✅ Done | Built in this task — bcrypt + JWT + SQLite. The earlier claim that it existed was never backed by pushed code |
| Frontend (all screens) | ✅ Done | Landing, auth, calibration, live session, dashboard, report |
| 5 real test UI pages | ⏳ Open | Currently placeholder blocks in Live Session |

The agent and report layers were deliberately built against **hand-authored mock session data** so they could be developed and tested in parallel with the CV/gaze pipeline. Swapping mock data for real session output requires no changes to the agents or report code — only the data source changes.

---

## Getting started

### Requirements
- **Python 3.12 specifically** — pinned in `.python-version`. Not 3.13/3.14: mediapipe has no wheels for those, and without mediapipe there is no face landmarking and so no live gaze. Everything except live capture works on newer versions, which makes this easy to get wrong quietly.
- Node.js + npm
- A CUDA GPU is only needed for *retraining* the detectors — everything else (including inference) runs fine on CPU.

### Backend
```bash
git clone <repo-url>
cd gazelens

py -3.12 -m venv .venv                  # Windows;  python3.12 -m venv .venv elsewhere
.venv/Scripts/activate                  #           source .venv/bin/activate

# CPU-only torch — skips the ~2.5GB CUDA build we never use for inference
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install -r requirements.txt

python scripts/fetch_face_landmarker.py # models/face_landmarker.task, needed by backend/cv
playwright install chromium             # backend/render + the report PDF fallback

# Optional: JWT signing key. If unset, one is generated and saved to
# backend/api/.secret_key (gitignored) so tokens survive restarts. Set the
# variable explicitly for anything deployed.
# export GAZELENS_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))")

cd backend
python -m api.init_db --demo-user       # create the SQLite schema
uvicorn api.main:app --reload --port 8000
```

> The run command is `cd backend && uvicorn api.main:app`, **not**
> `cd backend/api && uvicorn main:app`. `backend/api` is a package now, and has
> to be: several backend packages define a `schemas.py`, and running from
> inside the directory puts `api/schemas.py` where it can shadow
> `attribution`'s or `gaze_estimation`'s.

To reproduce an exact environment (pilot study, paper numbers) use
`pip install -r requirements.lock.txt` instead of `requirements.txt`.

**Model assets are gitignored and fetched separately:**

| Asset | How |
|---|---|
| `models/face_landmarker.task` | `python scripts/fetch_face_landmarker.py` |
| `models/pupil_yolo_final.pt` | Copy from Drive — **the** trained YOLOv8n detector, the one behind the benchmark table above |
| `models/pupil_smoketest.pt` | `python scripts/make_smoketest_detector.py` — optional stand-in, see below |

Without them the API still starts and every test suite still passes (all are
loaded lazily); only live capture is unavailable. `GET /health` reports
`cv_available` so you can tell which state you're in.

**If you don't have Drive access**, `scripts/make_smoketest_detector.py` trains a
small pupil detector on synthetic drawn eyes in about a minute on CPU, so the
live pipeline can be run and tested end to end. `backend/cv` picks weights in
this order — real detector, `$GAZELENS_PUPIL_WEIGHTS`, smoke-test stand-in —
so dropping `pupil_yolo_final.pt` into `models/` silently upgrades everything.

> ⚠️ **The smoke-test model is not a measurement instrument.** It was trained on
> ellipses, not eyes. `PupilDetector.is_smoketest` flags when it's in use.
> Never report numbers from it — the benchmark table comes from
> `pupil_yolo_final.pt` and nothing else.

**Known Windows setup wrinkles**
- `pip check` reports *"ultralytics requires opencv-python, which is not installed"*. Expected — mediapipe needs `opencv-contrib-python`, which is a strict superset and satisfies both. Installing `opencv-python` alongside it writes two versions into the same `cv2/` directory and breaks the import. Leave it as is.
- `weasyprint` needs native GTK libraries pip cannot install. **This no longer blocks PDF reports**: `backend/reports/pdf_backends.py` falls back to headless Chromium, which the project already installs for `backend/render`. Install the [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer) only if you want WeasyPrint's exact rendering.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Open the printed URL (usually `http://localhost:5173`).

### Run the agent chain against mock data
```bash
cd backend/agents
python3 test_agents.py      # test suite
python3 orchestrator.py     # runs mock sessions, prints JSON
```

### Run the CV + calibration + gaze tests
None of these need a webcam, `models/*.pt`, or mediapipe — the detector is stubbed
and gaze estimation trains on synthetic calibration sessions.
```bash
cd backend/cv              && python3 test_cv.py
cd backend/calibration     && python3 test_calibration.py
cd backend/gaze_estimation && python3 test_gaze_estimation.py
cd backend/attribution     && python3 test_attribution.py   # also pipes into the agent chain
cd backend/api             && python3 test_api.py           # full session lifecycle, throwaway DB
cd backend/render          && python3 test_render.py        # captures a local HTML fixture, no network
```

### Check live pupil detection against your own webcam
Needs the full install above, plus `face_landmarker.task` and *some* pupil
weights (`pupil_yolo_final.pt` from Drive, or the smoke-test stand-in).
```bash
cd backend/cv
python3 webcam_demo.py            # press q to quit
python3 webcam_demo.py --headless # no window, prints FPS + detection rate
```

### Generate a sample UX report
```bash
cd backend/reports
python3 report_generator.py
# outputs to backend/reports/generated/  (HTML + PDF + heatmap PNG)
```
PDF rendering tries WeasyPrint, then headless Chromium. The returned dict
carries `pdf_backend` so you know which produced the file. HTML is always
written first, so a machine with neither backend still gets a readable report.

### Run the detector benchmark
```bash
python evaluation/evaluate.py --model frcnn --weights runs/frcnn/frcnn_final.pth
python evaluation/evaluate.py --model ssd   --weights runs/ssd/ssd_final.pth
yolo val model=models/pupil_yolo_final.pt data=configs/lpw.yaml
python evaluation/compare_models.py   # consolidates all 3 into runs/eval/final_comparison.csv
```

---

## Contributing

```bash
git checkout -b <yourname>/<feature>   # e.g. sarah/calibration
# ... do the work, commit normally ...
git push -u origin <yourname>/<feature>
```
Open a PR into `main` rather than pushing directly — most open modules above are independent of each other, so conflicts should be rare, but PRs keep the history reviewable.

---

## Roadmap

1. ~~Wire `models/pupil_yolo_final.pt` into a live webcam loop (`backend/cv/`).~~ ✅
2. ~~Build the calibration data-collection endpoint (`backend/calibration/`).~~ ✅ — still needs its request/response field names reconciled with `Calibration.jsx` once the frontend is pushed; see `backend/calibration/CONTRACT.md`.
3. ~~Train the gaze regression model from calibration data (`backend/gaze_estimation/`).~~ ✅ — accuracy verified against synthetic sessions; needs re-checking against a real participant once one exists.
4. ~~Build the UI attribution + metrics engine (`backend/attribution/`).~~ ✅ — verified end-to-end into the agent chain against hand-scripted gaze; see `backend/attribution/CONTRACT.md`.
5. Build the 5 real test UI pages with bounding-box configs (`test_uis/`).
6. ~~Wire real session/report endpoints into `backend/api/`.~~ ✅ — the full pipeline now runs end to end through the API; see `backend/api/CONTRACT.md`.
7. Run the participant pilot study; finalize experiments for the paper.

---

## Publication target

Best fit: **ETTAC 2026** (Second International Workshop on Eye Tracking Techniques, Applications and Challenges), held with **ICPR 2026** in Lyon, August 21 2026. Scope directly covers gaze detection, gaze-based HCI, eye tracking + AI/LLMs, and usability inspection.

---

## License

*(add license here)*
