# Open items

Everything here needs something I cannot do from a terminal: a file that lives
in Drive, a human sitting in front of a webcam, or a decision that belongs to
the team. Each has the exact steps to close it.

Ordered by what blocks the paper.

---

## 1. The real detector weights — `models/pupil_yolo_final.pt`

**Blocks:** every accuracy number in the README's benchmark table, and any
real gaze measurement.

The file is gitignored and kept in Drive. Nothing in the repo can fetch it,
and the Google Drive connector is not authorised in this environment (and a
non-interactive session cannot run an OAuth flow).

**To close it, either:**

1. **Authorise Drive** — claude.ai → Settings → Connectors → Google Drive.
   Once connected, I can pull the file into `models/` directly.
2. **Copy it manually** — drop `pupil_yolo_final.pt` into `models/`. Nothing
   else changes: `backend/cv` resolves weights in the order
   *explicit argument → `$GAZELENS_PUPIL_WEIGHTS` → `pupil_yolo_final.pt` →
   smoke-test stand-in*, so it is picked up automatically.

**Verify it took:**
```bash
curl -s localhost:8000/health          # weights_present: true
cd backend/cv && python3 test_cv.py    # prints "using pupil_yolo_final.pt (real LPW detector)"
```

Until then the pipeline runs on `models/pupil_smoketest.pt`, trained on drawn
ellipses by `scripts/make_smoketest_detector.py`. **Nothing from it belongs in
the paper** — `PupilDetector.is_smoketest` flags when it's in use.

---

## 2. No real participant has ever used this

**Blocks:** every claim in the paper.

Everything is validated against synthetic data: synthetic calibration
sessions, scripted gaze streams, hand-written HTML fixtures. That proves the
plumbing is correct and proves **nothing** about accuracy on a real face.

**No webcam is reachable from this machine** — OpenCV finds no capture device
on indices 0–2 (`VIDEOIO(DSHOW): backend is generally available but can't be
used to capture by index`). So this cannot be closed here at all, by me or by
a script: it needs a camera and a person. Run the checklist below on a laptop
with a working webcam.

The specific numbers that are currently model-derived and need real
measurement:

| Claim | Current basis | How to measure it for real |
|---|---|---|
| ~40px gaze error | synthetic calibration, `gaze_estimation` LOPO CV | Run §3 below; read `median_error_px` from a real session |
| dispersion threshold 0.06 | derived from that 40px figure | Re-derive once real error is known; `attribution/fixations.py` |
| fixations ≈ 0.3s | I-DT on synthetic streams | Compare against the participant's real fixation durations |
| detector precision/recall | LPW, train == val | Needs a real held-out split — see §4 |

### First-participant checklist

```bash
cd backend && python -m api.init_db --demo-user
uvicorn api.main:app --port 8000
```

1. **Calibrate** — 16 points. Check `quality.usable` is `true` and
   `detection_rate` > 0.8 before continuing. If not, fix the lighting and
   redo; a bad calibration poisons everything downstream.
2. **Train** — `POST /api/sessions/{id}/calibration`. Record
   `median_error_px` and `per_frame_median_error_px`. **This is the number
   the paper needs.** If it is far from 40px, retune the dispersion threshold.
3. **Record** — one fixed test page, ~60s, participant told where to look at
   known moments. That gives ground truth to check attribution against.
4. **Finalise and read the report.** Check `tracked_pct` (how much of the
   session had usable gaze) and `background_pct` (gaze that hit no element).
   A high `background_pct` means the bounding boxes don't match what was on
   screen.
5. **Sanity-check by eye**: does the heatmap put attention where the
   participant said they were looking?

Run this with **one** person before recruiting a cohort. Everything above is
plumbing verification; step 2's number is the first real result this project
has produced.

---

## 3. `frontend/` has never been pushed

**Blocks:** nothing on the backend; blocks anyone actually using the system.

`frontend/src/api/client.js` was the stated source of truth for the session
API contract, so that contract was defined server-side instead.

**To close it:**
```bash
python scripts/generate_api_client.py
# writes frontend/src/api/openapi.json + client.generated.js
```
Then **diff `client.generated.js` against the real `client.js`**. That diff is
the actual list of mismatches — it cannot be produced by describing the API in
prose. Everything provisional is confined to `backend/api/schemas.py` and the
router prefixes; see `backend/api/CONTRACT.md` for the field-by-field notes.

The generator never overwrites `client.js`.

---

## 4. The detector benchmark is measured on training data

**Status: the split now exists and the inflation has been measured.**
See §4b for what still needs the real weights.

`configs/lpw.yaml` pointed `train` and `val` at the same folder, so every
figure in the README's table was measured on data the models had seen.

**Done:**
```bash
python scripts/make_lpw_split.py            # subject-wise split
python scripts/evaluate_split_gap.py        # measures the inflation
```

LPW is 22 subjects × 3 videos. A random *frame* split would barely help —
consecutive frames are near-duplicates, so it puts frame 500 in train and 501
in val. `make_lpw_split.py` splits by **subject** (16 train / 3 val / 3 test,
disjoint, verified), which is the only split that answers the question the
paper asks. `configs/lpw.yaml` now carries a warning; quote
`configs/lpw_subject_split.yaml`.

`evaluate_split_gap.py` evaluates one set of weights twice — on its own
training data and on held-out subjects — so the gap is attributable to the
split alone, not to a different model or image size.

### 4b. Re-running it for the *published* model

The measurement above used a reference model trained here on CPU, because
`pupil_yolo_final.pt` is not on this machine (§1). Once those weights exist:

```bash
python scripts/evaluate_split_gap.py --weights models/pupil_yolo_final.pt --split test
```

That produces the number for the paper. Note the published model was trained
on **all 22 subjects**, so subjects 3/18/21 are in its training data — the
held-out column will only be honest after a retrain on
`configs/lpw_subject_split.yaml`. Until then, treat 4b as the plan, not the
result.

---

## 5. `test_uis/` — the 5 real test pages

**Blocks:** the pilot study protocol.

Interim layouts live in `backend/api/layouts.py` (3 pages, geometry from
`reports/heatmap_stub.DEMO_LAYOUTS`). They describe pages that don't exist.

**To close it:** build the pages, and put each one's element config *next to
its HTML* so the boxes and the markup can't drift apart. `layouts.layout_for()`
is the only function that changes.

---

## 6. Smaller things

**~~`heatmap_stub.py` lint~~** — fixed. `zip(..., strict=True)`; the repo now
lints clean end to end (`ruff check backend/ scripts/ --select F,E9,B,A`).

**Alembic** — there are no migrations. The schema changes by editing
`models.py` and recreating the database. Add Alembic **the moment the study
has collected participant data worth migrating rather than regenerating** —
that will be during the pilot, not after it.

**`GAZELENS_SECRET_KEY`** — a key is auto-generated into
`backend/api/.secret_key` (gitignored) so tokens survive restarts. For
anything deployed beyond a study laptop, set the environment variable
explicitly and delete that file.

**SSRF on `/api/render/capture`** — private and loopback addresses are
refused, but that is a guardrail, not a boundary (DNS rebinding defeats it).
Keep the API off the public internet.
