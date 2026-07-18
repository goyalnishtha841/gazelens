# GazeLens
### *Built on the GazeUX-Agent framework — a webcam-based, multi-agent framework for gaze-driven UI/UX evaluation*

GazeLens turns an ordinary laptop webcam into a low-cost usability-testing tool. It tracks where someone actually looks while using a web page, maps that attention to specific UI elements, and runs it through a chain of evidence-grounded AI agents that produce a UX report a designer can act on — not a vague "make it better," but "the checkout button got 2% of total gaze time against a 5% threshold, here's the fix, here's the confidence score."

---

## Why this exists

Proper eye-tracking hardware is expensive, and even when you have gaze data, someone still has to manually work out *why* a design failed. GazeLens closes that gap with three concrete contributions:

1. **A benchmarked, swappable pupil detector** — comparing YOLO, SSD, and Faster R-CNN on real (imperfect) webcam conditions: lighting, glasses, head movement — evaluated on speed and robustness, not just accuracy.
2. **Gaze-to-UI-element attribution** — converting raw gaze coordinates into per-element metrics (dwell time, time-to-first-fixation, revisit count, scanpath), not just a heatmap.
3. **A traceable multi-agent reasoning layer** — Behavior → UX Evaluation → Recommendation → Critic/Verifier, where every claim must cite a real metric, and a dedicated verifier agent rejects anything it can't independently re-derive from raw data.

---

## Architecture

```
backend/
├── agents/            ✅ built + tested — behavior analysis, heuristic evaluation,
│                          recommendation generation, critic/verification
├── reports/            ✅ built + tested — HTML/PDF report generation from agent output
├── cv/                 ⏳ pending — wraps the trained detectors for live inference
├── calibration/        ⏳ pending — 9/16-point calibration flow
├── gaze_estimation/    ⏳ pending — pupil position → screen coordinate regression
├── api/                ⏳ pending — FastAPI layer tying everything together
└── db/                 ⏳ pending — session/participant/metrics storage

frontend/                ⏳ not started — React app (calibration screen, live session, dashboard)

configs/, dataset/, evaluation/, LPW/, models/, scripts/, training/
                          🟡 in progress — pupil detector training/benchmark on the LPW dataset
```

**Pipeline, end to end:**

```
Webcam → Face/Eye Landmarking → Pupil Detection → Gaze Estimation
       → Gaze-to-UI Attribution → Metrics + Heatmap
       → Agent Chain (Behavior → Evaluation → Recommendation → Critic)
       → PDF/HTML Report + Dashboard
```

---

## Current status

| Module | Status | Notes |
|---|---|---|
| Pupil detection (YOLO / SSD / Faster R-CNN) | 🟡 Mostly done | Trained + benchmarked on LPW; one model's results still pending |
| Live webcam integration | ⏳ Not started | Blocked on picking the winning detector from the benchmark |
| Calibration | ⏳ Not started | |
| Gaze estimation | ⏳ Not started | Depends on calibration |
| UI attribution + metrics + heatmap | ⏳ Not started | |
| Agent chain (behavior/evaluation/recommendation/critic) | ✅ Done | Fully tested against mock session data — see `backend/agents/test_agents.py` |
| Report generation | ✅ Done | Generates a one-page HTML/PDF report; tested against 3 mock scenarios |
| Frontend | ⏳ Not started | |
| FastAPI backend / API layer | ⏳ Not started | |

The agent and report layers were deliberately built against **hand-authored mock session data** (`backend/agents/mock_sessions.py`) so they could be developed and tested in parallel with the CV/gaze pipeline. Swapping mock data for real session output from the gaze pipeline requires no changes to the agents or report code — only the data source changes.

---

## Dataset setup
This repo doesn't include the LPW dataset or trained weights (too large for git).
Download from [Drive link] and place under `LPW/` and `dataset/` at the repo root
before running training/evaluation scripts.

## Getting started

### Requirements
- Python 3.10+
- `wkhtmltopdf` (system binary, used for PDF export — `apt install wkhtmltopdf` / `brew install wkhtmltopdf`)

### Install
```bash
git clone https://github.com/eva-singh/eye-gaze-lpw.git
cd eye-gaze-lpw
pip install -r requirements.txt
```

### Run the agent chain against mock data
```bash
cd backend/agents
python3 test_agents.py      # runs the full test suite
python3 orchestrator.py     # runs all 3 mock sessions, prints JSON output
```

### Generate a sample UX report
```bash
cd backend/reports
python3 report_generator.py
# outputs PDFs to backend/reports/generated/
```

---

## Roadmap

1. Finalize the detector benchmark (mAP / FPS / robustness) and pick the production detector.
2. Wire the winning detector into a live webcam loop via MediaPipe face/eye landmarking.
3. Build the calibration flow, then the gaze regression model.
4. Build UI attribution, metrics, and real heatmap rendering (replacing the current placeholder).
5. Wire the full pipeline into a FastAPI backend and React frontend.
6. Run the participant pilot study and finalize experiments for the paper.

---

## Publication target

Best fit: **ETTAC 2026** (Second International Workshop on Eye Tracking Techniques, Applications and Challenges), held with **ICPR 2026** in Lyon, August 21 2026. Scope directly covers gaze detection, gaze-based HCI, eye tracking + AI/LLMs, and usability inspection.

---

## License

*(add license here)*