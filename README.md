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

**Known limitation:** `configs/lpw.yaml` currently points `train` and `val` at the same folder — these numbers are measured on data the models already trained on, not a genuine held-out test set. Treat them as optimistic until a proper split exists.

---

## Architecture

```
backend/
├── agents/            ✅ built + tested — behavior analysis, heuristic evaluation,
│                          recommendation generation, critic/verification
├── reports/            ✅ built + tested — HTML/PDF report generation from agent output
├── api/                 ✅ built + tested — FastAPI: auth (signup/login/JWT), health check
├── render/              ✅ built + tested — arbitrary-URL screenshot + auto element detection
│                          (Playwright/Chromium), feeds Live Session's "Any URL" mode
├── cv/                  ⏳ open — wraps the trained YOLO detector for live inference
├── calibration/         ⏳ open — 9/16-point calibration data collection endpoint
├── gaze_estimation/     ⏳ open — pupil position → screen coordinate regression
└── db/                  ⏳ open — session/participant data model (auth's User model exists)

frontend/                 ✅ built — React app: landing, sign-in/up, calibration UI, live
                              session UI (fixed test pages + arbitrary URL mode), dashboard,
                              report view. Session/report data currently mocked
                              (frontend/src/api/client.js) pending backend/api session endpoints.

configs/, dataset/, evaluation/, LPW/, models/, scripts/, training/
                          ✅ detector training + evaluation complete for all 3 models
test_uis/                 ⏳ open — the 5 real test UI pages (currently placeholders in Live Session)
```

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
| Live webcam integration | ⏳ Open | Wraps `models/pupil_yolo_final.pt` — the winning detector |
| Calibration | ⏳ Open | Frontend UI exists (`Calibration.jsx`); needs a real backend endpoint |
| Gaze estimation | ⏳ Open | Depends on calibration data |
| UI attribution + metrics + heatmap | ⏳ Open | The link between raw gaze and the agents — schema already defined |
| Agent chain (behavior/evaluation/recommendation/critic) | ✅ Done | Fully tested against mock session data |
| Report generation | ✅ Done | Generates PDF/HTML reports, tested against multiple scenarios |
| Auth (signup/login) | ✅ Done | Real hashed passwords + JWT, SQLite |
| Arbitrary-URL rendering | ✅ Done | Screenshot + auto element detection via headless browser |
| Session/report API endpoints | ⏳ Open | Currently mocked in the frontend |
| Frontend (all screens) | ✅ Done | Landing, auth, calibration, live session, dashboard, report |
| 5 real test UI pages | ⏳ Open | Currently placeholder blocks in Live Session |

The agent and report layers were deliberately built against **hand-authored mock session data** so they could be developed and tested in parallel with the CV/gaze pipeline. Swapping mock data for real session output requires no changes to the agents or report code — only the data source changes.

---

## Getting started

### Requirements
- Python 3.10+
- Node.js + npm
- A CUDA GPU is only needed for *retraining* the detectors — everything else (including inference) runs fine on CPU.

### Backend
```bash
git clone <repo-url>
cd eye-gaze-lpw
pip install -r requirements.txt
playwright install chromium   # required for backend/render -- not optional, separate from the pip package
cd backend/api
uvicorn main:app --reload --port 8000
```

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

### Generate a sample UX report
```bash
cd backend/reports
python3 report_generator.py
# outputs to backend/reports/generated/
```

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

1. Wire `models/pupil_yolo_final.pt` into a live webcam loop (`backend/cv/`).
2. Build the calibration data-collection endpoint (`backend/calibration/`) behind the existing frontend UI.
3. Train the gaze regression model from calibration data (`backend/gaze_estimation/`).
4. Build the UI attribution + metrics engine (`backend/attribution/`) — can be built now against a hand-written fake gaze stream, independent of steps 1–3.
5. Build the 5 real test UI pages with bounding-box configs (`test_uis/`).
6. Wire real session/report endpoints into `backend/api/`, replacing the frontend's current mocks.
7. Run the participant pilot study; finalize experiments for the paper.

---

## Publication target

Best fit: **ETTAC 2026** (Second International Workshop on Eye Tracking Techniques, Applications and Challenges), held with **ICPR 2026** in Lyon, August 21 2026. Scope directly covers gaze detection, gaze-based HCI, eye tracking + AI/LLMs, and usability inspection.

---

## License

*(add license here)*
