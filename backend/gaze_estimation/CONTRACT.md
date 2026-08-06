# Gaze estimation contracts

Two directions. Upstream: what this module reads from `backend/calibration`.
Downstream: the gaze stream `backend/attribution` will consume.

---

## 1. Upstream — reading calibration data

No translation layer. This module calls `backend/calibration`'s own objects:

```python
from calibration import get_store
rows = get_store().get(session_id).training_rows()
```

The `cal_<id>.csv` export works identically via `training.load_rows_from_csv`
— CSV empty strings are handled as the `None`s they represent.

Every assumption about that format lives in **`features.py` and nowhere
else**. If calibration's schema changes, that is the only file to update.

### Which columns are used, and why

| Used as features | |
|---|---|
| `left_x_eye`, `left_y_eye`, `right_x_eye`, `right_y_eye` | Pupil centre **within its own eye box**. |

`*_x_frame`/`*_y_frame` are deliberately **not** features. They encode where
the pupil sits in the whole webcam frame, so they move when the participant
shifts in their chair without moving their eyes. Regressing on them would
learn "head position → screen position" and collapse the moment the head
moves. They're carried through as diagnostics only.

`target_x`, `target_y` are the regression target. `point_index` is the
grouping used for cross-validation — see below, it matters more than it
looks. `confidence`, `eyes_detected`, `screen_width`, `screen_height` are
used for filtering and for converting error into pixels.

### Known gap in the upstream format

`backend/calibration` records screen size in **pixels only**. Degrees of
visual angle need physical screen size and viewing distance, so they cannot
be derived from a stored session. Rather than assume a viewing distance,
they're reported only when the caller supplies `viewing_distance_cm` and
`screen_diagonal_in` on the train request; otherwise the response carries a
`degrees_unavailable` note explaining the omission.

**If the pilot study wants visual angle recorded per participant**, that's a
change to `backend/calibration`'s `StartCalibrationRequest` — flagged, not
made here.

---

## 2. Accuracy — how the reported number is produced

### Effective sample size is 9 or 16, not ~240

Calibration stores ~15 frames per target, but those frames differ only by
detector noise: the participant fixated one target throughout. So a
16-point session has ~240 rows and **16 independent observations**.

Everything follows from that:

- **Model capacity is budgeted against point count.** `max_degree_for` caps
  parameters at `n_points - 2`, so a 9-point session cannot select a model
  that would interpolate its own targets. This is why a 9-point session gets
  a lower ceiling than a 16-point one, automatically.
- **Cross-validation holds out points, never rows.** A random 80/20 row split
  puts near-identical frames of the same fixation in train and test, scoring
  the model on points it has already seen.

That second point is not theoretical. The test suite measures it, on the
configuration the capacity cap exists to forbid (degree 3 on 9 points):

```
row-wise 80/20 split :  27.8px   (leaks -- points seen in training)
leave-one-point-out  :  59.0px   (honest -- point never seen)
```

A 2.1× understatement. Note the effect is *small* on a well-spread 16-point
session with a low-degree model — holding one point out barely changes the
fit — so a row-wise split doesn't always mislead. It misleads exactly when
the model is overfitting, which is the one case validation exists to catch.

### Two error figures, both reported

| Field | Meaning |
|---|---|
| `median_error_px` | Held-out error with each fixation averaged over its frames. The **mapping's** accuracy. Comparable to calibration figures in the literature. |
| `per_frame_median_error_px` | Held-out error on individual frames, detector jitter included. What **one live gaze estimate** actually delivers. Always larger. |

Quote the first for the mapping, the second for anything reasoning about
single frames. Reporting only the first would overstate live performance by
roughly √(frames per point).

Also reported: `mean_error_px`, `p95_error_px`, `max_error_px`, per-axis
error, `median_error_pct_diagonal`, a `per_point_error_px` breakdown, and
`worst_point` — so a single bad calibration target can be identified and
re-presented rather than quietly dragging the session down.

`training_metrics` is the fit error on the training data, aggregated per
point so it's directly comparable to the held-out figure. It exists **only**
to expose the overfitting gap. Never quote it alone.

### Model selection

Ridge-regularised polynomial regression, fit in closed form. Feature set
(`mean_eye` 2D / `both_eyes` 4D), degree (1–3) and ridge strength are chosen
per session by leave-one-point-out CV, ties breaking towards the simpler
model. The `selection.leaderboard` records what the alternatives scored, so
"degree 2 was enough" is a measured result rather than an assumption.

An MLP was not used: at 9–16 independent observations it would have more
parameters than data, and brings seeds, learning rates and stopping criteria
that all need defending. If a session ever selects the maximum degree *and*
still shows large held-out error, that is the evidence that would justify
more capacity.

---

## 3. Downstream — the gaze stream for `backend/attribution`

`backend/agents/schemas.py` defines `SessionMetrics`, which is entirely
*post*-attribution (per-element dwell time, TTFF, fixation and revisit
counts, scanpath). It says nothing about raw gaze — so the stream shape was
undefined and is defined here.

```python
from gaze_estimation import get_estimator
est = get_estimator(session_id)          # loads once, cached
point = est.estimate_frame_result(frame_result)   # a cv.FrameResult
```

### `GazePoint`

| Field | |
|---|---|
| `timestamp` | Seconds, from the capture frame. Attribution's clock. |
| `x`, `y` | Normalised `[0,1]` screen coordinates. |
| `x_px`, `y_px` | The same point in pixels, for heatmaps and bbox tests. |
| `valid` | `False` when no pupil was available this frame. |
| `in_bounds` | `False` when the raw prediction fell off-screen before clamping. |
| `confidence` | Carried through from the detector. |
| `note` | `""`, `"no_pupil"`, `"off_screen"`, `"insufficient_pupils_for_feature_set"`. |

### Three things attribution should know

**Invalid points are in the stream, not removed.** A blink is emitted as
`valid=False` rather than skipped. Silently dropping it would make the gaze
before and after the gap look continuous, inflating dwell time on whatever
element was being looked at either side.

**`in_bounds=False` is not the same as a fixation at the screen edge.**
Coordinates are clamped to `[0,1]`, so an off-screen prediction lands on the
border — where real UI elements live. Filter on `in_bounds` before
attributing, or the model will credit the nav bar with every glance away
from the monitor.

**The stream is raw.** No fixation detection, no smoothing (the estimator's
EMA defaults to off), no dwell aggregation, no element mapping. Those are
attribution's decisions, and making any of them here would mean attribution
could never change its mind. Smoothing in particular shortens saccades and
stretches fixations — exactly the signal attribution measures.

`estimator.median_error_px` carries the model's held-out accuracy alongside
every estimate, so attribution can state its own error bar without going
back to the training run. A gaze error of ~40px against a 120px button is a
very different confidence claim from the same error against a 40px icon.

### Testing attribution before real sessions exist

`synthetic.synthetic_gaze_stream()` produces frames with a known `true_x`/
`true_y`, so attribution can be built and tested against a gaze stream with
ground truth — same pattern as `agents/mock_sessions.py` and `cv`'s
`StubPipeline`.
