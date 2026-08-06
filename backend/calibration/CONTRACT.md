# Calibration data contract

Two contracts live here. The HTTP one is provisional; the storage one is the
important one.

---

## 1. HTTP contract (provisional — needs reconciling with the frontend)

`frontend/Calibration.jsx` and `frontend/src/api/client.js` are **not in this
repo**. The README lists the frontend as built, but it has never been pushed
to `origin/main`, so there was nothing to read the real request/response
shape off. This contract was therefore defined server-side.

**All of it is confined to `schemas.py` and `routes.py`.** Renaming fields to
match the real client is an edit to those two files and nothing else —
`session.py`, `storage.py`, `points.py`, and all of `backend/cv` are
untouched by it.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/calibration/patterns` | The 9- and 16-point grids |
| `POST` | `/api/calibration/sessions` | Start a session |
| `POST` | `/api/calibration/sessions/{id}/samples` | Submit frames for one target |
| `POST` | `/api/calibration/sessions/{id}/complete` | Finish + write the training export |
| `GET` | `/api/calibration/sessions/{id}` | Progress + quality |
| `GET` | `/api/calibration/sessions` | List sessions |
| `DELETE` | `/api/calibration/sessions/{id}` | Discard a session |

### Flow

```
POST /sessions
  { participant_id, pattern: 16, screen_width, screen_height, samples_per_point }
  -> { session_id, points: [{index, x, y} x16], ... }

  for each point the UI presents:
     POST /sessions/{id}/samples
       { point_index, frames: ["data:image/jpeg;base64,..." x N] }
       -> { accepted, rejected, samples_for_point, point_complete,
            points_remaining, session_complete, last_reading }

POST /sessions/{id}/complete
  -> { ready_for_regression, training_csv, quality, ... }
```

### Points that need confirming against the real client

- **Pattern.** Defaults to 16; 9 is supported. If `Calibration.jsx` presents
  a different count, add it to `PATTERNS` in `points.py` — one line.
- **Point order.** Server grid is row-major, inset 8% from each edge. The
  client is *not* required to follow it: every sample carries its
  `point_index`, so pairing is by index, never by arrival order. If the
  client lays targets out differently, it can send `target_x`/`target_y`
  and the server records `target_source: "client"`.
- **Batching.** Frames are posted as a burst per target, not one per request.
  If the client streams frame-at-a-time instead, send `frames: [oneFrame]` —
  it already works, just chattier.
- **Frame encoding.** Raw base64 or a full `data:image/...;base64,` URL;
  `canvas.toDataURL()` output can be posted as-is.
- **Auth.** No auth dependency is attached — `backend/api`'s JWT code isn't
  in the repo. When it is, add it once at the router level:

  ```python
  app.include_router(calibration_router, dependencies=[Depends(current_user)])
  ```

  `participant_id` is currently client-supplied; it should come from the JWT
  subject once auth exists.

---

## 2. Storage contract — what `backend/gaze_estimation` consumes

**This is the stable one. Build against it.**

On completion, each session writes two files to
`backend/calibration/calibration_data/`:

| File | Contents |
|---|---|
| `cal_<id>.json` | Full session: points, every sample, quality report |
| `cal_<id>.csv` | Flat training rows — **this is the handoff** |

One CSV row per captured frame. Column order is fixed by
`TRAINING_ROW_COLUMNS` in `session.py`.

### Features

| Column | Meaning |
|---|---|
| `left_x_eye`, `left_y_eye`, `right_x_eye`, `right_y_eye` | Pupil centre **within its eye box**, `[0,1]`. **Use these.** Invariant to where the head sits in the frame, so they survive the participant shifting in their chair. |
| `left_x_frame`, `left_y_frame`, `right_x_frame`, `right_y_frame` | Pupil centre in the full frame, `[0,1]`. Kept for diagnostics and head-movement analysis. |
| `interocular_norm`, `eye_mid_x`, `eye_mid_y`, `roll_norm` | Coarse head-position proxy. Not 6-DoF pose. Use to condition on, or to reject samples where the head moved between calibration and the live session. |

Eye columns are `None`/empty when that eye wasn't found in that frame —
one-eyed samples are kept rather than dropped, because whether to use them
is the regression's decision, not calibration's. Filter on `eyes_detected`.

### Target

`target_x`, `target_y` — normalised `[0,1]` viewport coordinates. **This is
what you regress onto.** Not pixels: `screen_width`/`screen_height` ride
along on every row, so a model can be trained across participants on
different monitors.

### Context / filtering

`session_id`, `participant_id`, `point_index`, `confidence`,
`eyes_detected` (0–2), `screen_width`, `screen_height`, `frame_width`,
`frame_height`, `timestamp`.

### Before training on a session

Check `quality.usable` in the JSON (or `ready_for_regression` in the
completion response). It is `False` when point coverage is under 75% or
pupils were found in under half the submitted frames. Poor sessions are
**saved, not refused** — a participant's time is expensive — so the flag is
what stops you training on junk.

`rejected_frames` in the JSON counts frames that yielded no pupil. A high
count against a low `detection_rate` means bad lighting or a bad camera
angle, not a bad model.

### Reading it

```python
import pandas as pd
df = pd.read_csv("backend/calibration/calibration_data/cal_<id>.csv")
X = df[["left_x_eye", "left_y_eye", "right_x_eye", "right_y_eye"]]
y = df[["target_x", "target_y"]]
```

Nothing else needs joining. That's the point.
