# Open items

What's still open, ordered by what blocks the paper and the demo. Each item says
what it blocks and the exact steps to close it. Product and engineering work beyond
these is in the README's [Roadmap](README.md#roadmap).

*Last reviewed: October 2026.*

---

## 1. Multi-participant pilot study

**Blocks:** every accuracy claim in the paper.

The ~65 px median gaze error in the README is measured on **one participant**
(4 calibrations, 20 held-out accuracy-check dots, one 1694×840 laptop screen).
That proves the pipeline works on a real face. It doesn't show how it varies
across people, glasses, lighting and laptops.

**To close it:** 10–20 participants, a mix of glasses / no glasses, lighting and
screen sizes. For each one:

1. **Calibrate.** 16 dots, then the 5-dot accuracy check. Note the verdict and the
   median error the app shows. If it's refused (over 15% of the screen diagonal),
   fix the lighting or seating and redo it; record how many tries it took.
2. **Run one sample page for ~60 s**, telling the participant to look at a few
   named elements at known moments. That gives ground truth for attribution.
3. **Finish and open the report.** Check that the heatmap matches what the
   participant says they looked at, and note the report's tracked % and the share
   of gaze that hit no element (a high share means boxes and page don't line up).
4. After the cohort, run `python scripts/evaluate_gaze_sessions.py` to score every
   saved calibration on its own accuracy-check dots.

Numbers that should be re-derived from the cohort rather than from one person:

| Setting | Where | Current basis |
|---|---|---|
| Fixation dispersion threshold | `backend/attribution/fixations.py` | one participant's error |
| Quality-gate thresholds | `backend/agents/quality_gate.py` | one participant's error |
| Cursor stabiliser radius | `frontend-new/src/lib/gazeStabilizer.js` | replay of 4 calibrations |

Calibration recordings are participant data: they stay out of git
(`backend/calibration/calibration_data/` is gitignored) and need consent.

---

## 2. Hosting

**Blocks:** anyone using GazeLens without running it on their own machine.

The deploy config is done: API image (`backend/Dockerfile`), Vercel config
(`frontend-new/vercel.json`), CI building the image, and [DEPLOY.md](DEPLOY.md).
What's missing is a host. The API needs ~1.5–2 GB RAM (MediaPipe + headless
Chromium), and the free options tried don't provide it:

- **Hugging Face Spaces (free CPU):** the deploy workflow pushes the code fine, but
  the team account's free CPU quota is 0, so the Space never starts.
- **Render free tier:** 512 MB RAM and no persistent disk.

**To close it:** pick one of
- a paid host: Render with [`render.yaml`](render.yaml) (persistent disk), or
  Hugging Face PRO for the existing Space;
- for demos only: run the API on a laptop and expose it over HTTPS with a free
  Cloudflare tunnel. Not set up yet; Vite would also need to allow the tunnel's
  host name (`server.allowedHosts`).

---

## 3. Detector benchmark: Faster R-CNN and SSD still on training data

**Blocks:** the three-way detector comparison in the paper.

`configs/lpw.yaml` originally pointed train and val at the same folder, so the
first benchmark numbers were measured on data the models had seen. A
subject-disjoint split now exists (`scripts/make_lpw_split.py`,
`configs/lpw_subject_split.yaml`: 16 train / 3 val / 3 test subjects), and
**YOLOv8n has been retrained and re-evaluated on it**, including per-condition
results (README, *Pupil detector benchmark*).

**Still open:** retrain Faster R-CNN and SSD on the same split and evaluate them
held-out (`python evaluation/evaluate.py --model frcnn|ssd ...`, then
`python evaluation/compare_models.py`). Until then the README's table puts an
honest YOLO number next to two inflated ones, and says so.

This is research-only: the live pipeline uses MediaPipe iris landmarks, not a
pupil detector.

---

## 4. Detector weights for the ablation — `models/pupil_yolo_final.pt`

**Blocks:** only the iris-vs-detector ablation (`FIXATION_PUPIL_SOURCE=fused|yolo`)
and re-running the YOLO benchmark. Live gaze does **not** need it.

The file is gitignored and kept in the team Drive. To use it, copy it into
`models/`; `backend/cv` picks it up automatically (order: explicit argument →
`$FIXATION_PUPIL_WEIGHTS` → `pupil_yolo_final.pt` → smoke-test stand-in).
`GET /health` then reports `weights_present: true`.

Never report numbers from `models/pupil_smoketest.pt`: it was trained on drawn
ellipses, and `PupilDetector.is_smoketest` flags it.

---

## 5. Smaller things

- **Database migrations.** There is no Alembic. New nullable columns are added on
  startup by `backend/api/db.py` (`_add_missing_columns`), which is enough for now.
  Add Alembic the first time a change needs a backfill or a non-nullable column,
  which will likely be during the pilot.
- **Signing key.** Without `GAZELENS_SECRET_KEY`, a key is generated into
  `backend/api/.secret_key` (gitignored) so logins survive restarts. Anything
  deployed must set the variable (the API refuses to start in production without
  it).
- **URL capture is a guardrail, not a boundary.** It now requires login, and
  private/loopback addresses are refused for the URL, every redirect hop and every
  subresource. DNS tricks can still get around checks like this, so keep the API
  off networks with sensitive internal services.

---

## Closed

- **Frontend pushed.** `frontend-new/` is the app; the old `frontend/` prototype was removed.
- **The 5 test pages.** `test_uis/` has all five pages, each with its element boxes
  in `elements.json` next to its HTML; `backend/api/layouts.py` loads them.
- **Lint.** `ruff check backend/ scripts/ --select F,E9,B,A` is clean and runs in CI.
- **First real participant.** Calibrated and measured (the README's accuracy table).
- **Unprotected API routes.** Calibration, gaze-model, attribution and render routes
  now require login and are owner-scoped.
- **Reports stuck on "Building your report".** Interrupted analyses are marked
  failed and can be retried; WeasyPrint runs in a separate process so it can't
  crash the API.
