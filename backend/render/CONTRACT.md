# Render contract

Screenshot an arbitrary URL and detect its elements, so a live page can be
studied the same way a hand-authored test UI is.

```python
from render import capture_page
result = capture_page("https://example.com")
result.layout   # element_id -> {bbox, importance, type}
```

`layout` is exactly the format `attribution.build_ui_config` accepts and
`reports/heatmap_stub.py` renders, so nothing downstream can tell a URL
session from a test-UI session.

---

## 1. Coordinates

Normalised to the **viewport**, top-left origin, y down — the same convention
as gaze, which is also viewport-relative.

Boxes are **clipped** to the viewport before normalising. A half-off-screen
element would otherwise get a box extending past 1.0, and every gaze point in
that phantom region would be attributed to it.

Elements entirely outside the viewport are **dropped**, not stored with
negative coordinates. Gaze can only land on what is on screen; a box at
y=-300 would silently never be hit while still appearing in the report as an
element that received no attention — which reads as a UX finding rather than
a capture artefact.

**This is a real limitation for long pages.** Only the first viewport is
attributable. `below_fold_dropped` counts what was lost. Scroll-aware capture
(stitching layouts across scroll positions, and tracking scroll offset in the
gaze stream) is the fix, and it is not built.

## 2. Filtering

| Filter | Threshold | Why |
|---|---|---|
| too small | < 0.15% of viewport | Gaze estimation carries ~40px of error; a 12×12 icon cannot be attributed to with any confidence |
| too large | > 60% of viewport | Page wrappers and full-width containers are not things a person looks *at* |
| off-screen | outside viewport | see above |
| cap | 40 elements, largest first | keeps the elements a participant is most likely to actually look at |

Each is counted on the result, so a page that came back with three elements
can be explained rather than guessed at.

## 3. **Classification is heuristic. This is the part to be careful with.**

`backend/agents` branches on the exact strings `CTA` / `text` / `image` /
`nav` / `non-interactive` and `high` / `medium` / `low`. A misclassification
does not produce a slightly-off report — it **silently exempts an element from
the rule that would have flagged it**, or invents a finding about something
that was never meant to be interactive.

A hand-authored `test_uis/` config is labelled by a human who knows the design
intent. Nothing here can know that. These are rules over tag names, ARIA
roles, class-name fragments and geometry:

| Signal | Confidence |
|---|---|
| `<button>`, `input[type=submit]` → CTA | 0.95 |
| `<nav>`, `<img>`, `<h1>`, `role=` → nav/image/text | 0.85–0.9 |
| `<a class="btn">` → CTA | 0.60 |
| `<a>` with no signal → text | 0.50 |
| `<div class="cta">`, `onclick` → CTA | 0.40–0.45 |
| anything else → non-interactive | 0.30 |

The default is the **inert** label, matching `api/layouts.py`: a wrong "CTA"
invents poor-visibility findings for every unlabelled box, whereas a wrong
"non-interactive" needs 5+ fixations before it says anything at all.

Every element records `confidence` and `classified_by` (the reason), and the
capture reports **`low_confidence_fraction`** — the share of kept elements
whose type was guessed rather than read off a tag. Measured on real pages:
~50% for example.com, ~80% for a content-heavy site. `backend/api` surfaces
this on the report as *"element types were auto-detected, not authored by a
designer; N% were inferred…"*.

**Read that number before quoting a URL-mode report.** At 80%, four in five
element labels the agents reasoned over were inferred from class names and
geometry.

## 4. Element ids

Prefers the author's own `id`, then `aria-label`, then `name`, then tag+text.
Those describe the element the way the team already talks about it, which is
what a UX report should say.

Text-derived ids are cut to the first four words / 32 characters **at a word
boundary** — they are printed verbatim in the report and on the heatmap, and
a 60-character id built from a footer's entire link list is unique and
unreadable.

## 5. Threading

Playwright's sync API refuses to run inside an asyncio event loop, and this is
called from FastAPI request handlers. `capture_page` detects a running loop
and hands the work to a worker thread — same fix, same reason as
`reports/pdf_backends.py`.

## 6. SSRF

`POST /api/render/capture` fetches a caller-supplied URL from the server.
Loopback, private, link-local and reserved addresses are refused.

**That check is a guardrail, not a security boundary** — DNS can still resolve
a public name to a private address (rebinding), and the check happens before
Chromium does its own resolution. Keep this endpoint behind auth and off the
public internet.

## 7. How `backend/api` uses it

`mode="url"` sessions call `capture_page` inline at session creation. On
success the detected layout becomes the session's layout and
`layout_is_placeholder` stays `False`. On failure — timeout, consent wall, a
canvas-only page — the session **falls back** to `layouts.PLACEHOLDER_URL_LAYOUT`
and is flagged, rather than refusing to create the session at all: a network
hiccup should not stop a participant who is already sitting down.

Both outcomes are visible on the report:

- captured → *"element types were auto-detected… N% inferred"*
- fallback → *"Element boxes are a PLACEHOLDER… (reason)"*
