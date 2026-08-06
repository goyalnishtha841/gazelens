# Attribution contracts

The link between raw gaze and the agent chain. Two inputs, one output.

```
gaze stream + element bounding boxes  ->  attribution  ->  SessionMetrics  ->  agents
```

This module imports nothing from `backend/cv`, `backend/calibration`, or
`backend/gaze_estimation`. It takes coordinates and rectangles; where they
came from is not its business. That independence is what let it be built and
tested before those modules produced anything real, the same way
`backend/agents` was built against `mock_sessions.py`.

---

## 1. Input — gaze

```python
GazeSample(timestamp, x, y, valid=True, confidence=1.0)
```

`x`, `y` normalised `[0,1]`, top-left origin, y down. This matches the
`GazePoint` that `backend/gaze_estimation` emits field for field, but is
declared independently — copy the values across, don't import.

`valid=False` points (blinks, dropouts) **must be kept in the stream**, not
filtered out before calling. They're excluded from every metric, but their
presence is what distinguishes "the tracker blinked" from "the user was
looking somewhere else", and a silently removed gap makes the gaze either
side of it look continuous.

Samples are sorted by timestamp on ingest, so arrival order doesn't matter.

## 2. Input — elements

Two accepted forms, both normalised to the same internal box:

| Form | Source |
|---|---|
| `(x, y, w, h)` normalised | `backend/reports/heatmap_stub.py`, hand-authored `test_uis/` configs |
| `{"x", "y", "width", "height"}` in CSS px + `viewport` | Playwright's `boundingBox()`, i.e. what `backend/render` most likely emits |

`backend/render` has **never been pushed to this repo**, so the second form is
inferred from the Playwright API, not read off its code. If it turns out to
emit something else, `geometry.parse_bbox` is the only function that needs to
change.

A pixel-valued box passed *without* a viewport is rejected rather than
accepted — it would normalise to a rectangle far off the page, never be hit,
and produce a plausible-looking all-zeros report.

Each element also carries `importance` (`high`/`medium`/`low`) and `type`
(`CTA`/`text`/`image`/`nav`/`non-interactive`). These come from the UI config,
never from gaze, and `backend/agents/rules.py` branches on these exact
strings — an element with the wrong type is silently exempt from the rules
most likely to flag it, so both vocabularies are validated on ingest.
Unlabelled elements default to `medium`/`non-interactive`, chosen because it
is the inert combination; defaulting to `CTA` would invent poor-visibility
findings for every unlabelled box on the page.

## 3. Output

`backend/agents`' own `SessionMetrics` class — loaded from
`backend/agents/schemas.py` by explicit file path (see `agents_schema.py`),
not redeclared. So `isinstance(report.metrics, SessionMetrics)` holds for the
agents' class, `orchestrator.run_pipeline(report.metrics)` accepts it
directly, and a field added to that schema surfaces here as a `TypeError` at
construction instead of a silently missing key.

```python
report = analyze_session(samples, ui_config, session_id)
orchestrator.run_pipeline(report.metrics)
```

`AttributionReport` wraps it with diagnostics that `SessionMetrics` has no
field for — background time, tracked percentage, bridged samples, overlapping
elements, warnings. `SessionMetrics` is a fixed contract owned by
`backend/agents` and must not grow, so they live alongside rather than inside.

`ui_config.layout_for_heatmap()` returns the exact `element_id -> (x,y,w,h)`
mapping `backend/reports/heatmap_stub.py` consumes, so the report layer needs
no conversion step.

---

## 4. The decisions that aren't obvious

### Out-of-bounds gaze counts toward `total_gaze_time`, not toward any element

Read off the mock data rather than chosen: in 3 of 4 sessions in
`mock_sessions.py` the dwell times sum to *less* than `total_gaze_time`
(`clean_session`: 14.2 vs 20.0). `SessionMetrics.dwell_pct` divides by
`total_gaze_time`, so whitespace time belongs in that denominator.

Background is deliberately **not** an entry in `dwell_time`, because
`agent1._most_attended` is `max(dwell_time)` and whitespace would frequently
win it. It's reported as `diagnostics.background_time` instead.

Blinks are excluded from `total_gaze_time` entirely — time the tracker was
blind is not time the user spent looking.

### Elements never fixated are omitted from `ttff`

This is the one place the output is deliberately incomplete, and it's forced
by how `backend/agents` reads it:

- `0.0` would make an element nobody looked at the winner of
  `agent1._first_noticed`, which is `min(ttff, key=ttff.get)`.
- `inf` fires a bogus `delayed_discovery` reading *"Time to first fixation
  was infs"*, and breaks the `json.dumps` in `orchestrator.__main__` —
  `Infinity` is not valid JSON.

Omission leaves every agent rule correct, and nothing is lost: the element is
still in `dwell_time` at `0.0`, which is what drives `poor_visibility` and
`ignored_important_elements`. **So `ttff`'s key set can legitimately be
smaller than `dwell_time`'s.** That is not a bug.

### Three different things, deliberately

| Metric | Built from | Meaning |
|---|---|---|
| `dwell_time` | per-sample attribution | time gaze was inside the box, *including* sweeping across it |
| `fixation_count` | I-DT fixations, assigned by centroid | times gaze *stopped* on it |
| `revisit_count` | visits containing ≥1 fixation, minus one | times gaze *returned* to it |

Keeping them separate is what makes `fixation_count` and `revisit_count`
independent measurements rather than the same number twice. Mock data could
not settle this — its numbers aren't derivable from its own scanpaths
(`scattered_session`'s `email_field` appears once in the scanpath but has
`revisit_count: 1`), because it was hand-authored.

A visit needs at least one fixation to count. Elements lying between two
others collect gaze every time the eye travels past — on the form page,
`name_field` sits directly between `promo_banner` and `email_field` — and
counting those transits produced more revisits than fixations, which is
incoherent. Passing over is not returning to.

### Fixation detection, and the threshold that matters

I-DT (Salvucci & Goldberg): min duration **100ms**, dispersion threshold
**0.06** normalised (~115px), applied to gaze smoothed with a **5-sample
moving average**.

The threshold is the load-bearing constant and it is easy to get badly wrong.
An earlier draft set it to 0.03 by comparing against `gaze_estimation`'s
~40px per-frame error. That is the wrong quantity: I-DT dispersion is
`(x-range + y-range)` across every sample in the fixation, so it scales with
the **range** of the noise — roughly 4–5σ per axis, summed over two axes, so
~8σ for a short fixation. At σ=40px that's ~340px, larger than most UI
elements, and no usable threshold exists on the raw stream. It failed
outright on realistic input: one fixation for an entire session, elements
with no TTFF, and `revisit_count` exceeding `fixation_count`.

Smoothing cuts σ by √5 to ~18px, bringing 8σ to ~145px and making ~115px
workable. Smoothing happens **here** rather than upstream because
`backend/gaze_estimation` deliberately leaves its stream raw and documents
that the decision belongs to whoever measures fixations — smoothing shortens
saccades and stretches fixations, which is exactly what this module measures.

A 115px threshold could in principle merge fixations on two adjacent
elements. It can't, because fixation growth also stops at an element
boundary: a fixation on element A and one on element B are by definition
different fixations. That constraint is what makes the exact threshold
non-critical rather than a knife edge.

### Noise tolerance has two stages

Smoothing absorbs the smallest excursions before labelling ever sees them.
Label-bridging catches what's left: a run of samples labelled otherwise,
shorter than **150ms** and bracketed by the *same* element on both sides, is
relabelled to it. Two guards stop it inventing attention — the same element
must sit on both sides (so it can never create a visit that didn't happen),
and a bridged *background* run must also be spatially within 0.01 of the box,
so a genuine glance away and back stays two visits.

Measured behaviour: a 100ms blink mid-visit is bridged; a 267ms one is not. A
brief flicker onto a nested child element doesn't split the parent visit.

### Overlapping boxes: smallest wins

Automatic element detection nests constantly — a button inside a card inside
a section — and a point inside the button is inside all three. Smallest-wins
picks the most specific element, which is the one a UX finding should name.
`priority` overrides this for genuine ties or hand-authored z-order. Ties
break on `element_id` so a report never changes wording between identical
runs. Overlaps are reported in diagnostics: heavy overlap usually means the
detector emitted containers alongside their children.

Box edges are half-open (`x <= px < x+w`), so adjacent elements sharing an
edge never both match.

---

## 5. Testing without any of the upstream modules

`synthetic.py` scripts gaze explicitly — `[("product_image", 2.0),
("checkout_button", 0.4)]` — so tests assert against known truth rather than
against whatever the code produced. Layout geometry is reused from
`heatmap_stub.DEMO_LAYOUTS` and labels from `mock_sessions.py`, so a
synthetic session is directly comparable to the mock data the agents were
built against.

`REALISTIC_NOISE = 0.021` is `gaze_estimation`'s measured ~40px per-frame
error. Use it — a scenario that only works at zero noise proves nothing.
