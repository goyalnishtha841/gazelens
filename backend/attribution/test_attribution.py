"""
test_attribution.py

Run with: python3 test_attribution.py   (from inside backend/attribution)

Hand-written fake gaze stream + hand-written bounding boxes -> metrics ->
straight into backend/agents/orchestrator.py, in one run. No webcam, no
calibration session, no trained gaze model, no imports from backend/cv,
backend/calibration or backend/gaze_estimation.

Same shape as backend/agents/test_agents.py: flat script, check() counter,
non-zero exit on failure.

The scripted streams state their own ground truth ("look at the product image
for 2 seconds, then the checkout button"), so these are assertions about known
inputs rather than assertions that the code agrees with itself.
"""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

# backend/ on the path so this runs directly, the way test_agents.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from attribution import routes                                   # noqa: E402
from attribution.agents_schema import SessionMetrics             # noqa: E402
from attribution.elements import ElementConfigError, build_ui_config  # noqa: E402
from attribution.engine import analyze_session, gaze_samples_from_dicts  # noqa: E402
from attribution.fixations import (                              # noqa: E402
    GazeSample,
    attribute,
    detect_fixations,
    smooth_positions,
)
from attribution.geometry import (                               # noqa: E402
    BBoxFormatError,
    hit_test,
    overlapping_pairs,
    parse_bbox,
)
from attribution.schemas import AnalyzeRequest                   # noqa: E402
from attribution import synthetic as syn                         # noqa: E402

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


def run(coro):
    return asyncio.run(coro)


def expect_http(label, coro, status_code):
    from fastapi import HTTPException

    try:
        run(coro)
    except HTTPException as exc:
        check(f"{label} -> {status_code}", exc.status_code == status_code)
        return
    check(f"{label} -> {status_code}", False)


# ----------------------------------------------------------------------
print("geometry -- both accepted bbox formats normalise identically")
normalised = parse_bbox((0.5, 0.25, 0.25, 0.5))
pixels = parse_bbox({"x": 960, "y": 270, "width": 480, "height": 540},
                    viewport=(1920, 1080))
check("heatmap_stub tuple form parses", normalised.as_tuple() == (0.5, 0.25, 0.25, 0.5))
check("Playwright pixel form normalises to the same box",
      abs(pixels.x - normalised.x) < 1e-9 and abs(pixels.h - normalised.h) < 1e-9)
check("w/h dict spelling also accepted",
      parse_bbox({"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}).w == 0.2)

try:
    parse_bbox({"x": 960, "y": 270, "width": 480, "height": 540})   # no viewport
    check("pixel bbox without a viewport is rejected, not silently misread", False)
except BBoxFormatError:
    check("pixel bbox without a viewport is rejected, not silently misread", True)

try:
    parse_bbox((0.1, 0.1, 0.2))
    check("malformed tuple rejected", False)
except BBoxFormatError:
    check("malformed tuple rejected", True)

print("\ngeometry -- hit testing and overlap")
boxes = build_ui_config("nested_page", syn.NESTED_PAGE).boxes
check("point in the nested button resolves to the BUTTON, not the card",
      hit_test(boxes, 0.25, 0.44) == "buy_button")
check("point in the card but outside the button resolves to the card",
      hit_test(boxes, 0.15, 0.15) == "product_card")
check("point outside everything is background", hit_test(boxes, 0.99, 0.99) is None)
check("nesting is reported as an overlap",
      ("buy_button", "product_card") in
      [tuple(sorted(p)) for p in overlapping_pairs(boxes)])
check("explicit priority overrides smallest-wins",
      hit_test(boxes, 0.25, 0.44, priority=["product_card"]) == "product_card")

edge_boxes = build_ui_config("edges", {
    "top": (0.0, 0.0, 1.0, 0.5), "bottom": (0.0, 0.5, 1.0, 0.5),
}).boxes
check("a point on the shared edge belongs to exactly one box",
      hit_test(edge_boxes, 0.5, 0.5) == "bottom")

print("\nelements -- the agents' vocabularies are enforced")
for bad in ({"a": {"bbox": (0, 0, 1, 1), "importance": "critical"}},
            {"a": {"bbox": (0, 0, 1, 1), "type": "button"}},
            {"a": (0.1, 0.1, 0.0, 0.5)}):
    try:
        build_ui_config("p", bad)
        check(f"rejects {bad}", False)
    except ElementConfigError:
        check("invalid importance/type/zero-area rejected", True)

check("bare bbox defaults to an inert type",
      build_ui_config("p", {"a": (0, 0, 0.5, 0.5)}).type_map()["a"] == "non-interactive")

# ----------------------------------------------------------------------
print("\nfixation detection -- smoothing and thresholds")
still = [GazeSample(1000 + i * (1 / 30), 0.5, 0.5) for i in range(30)]
check("a steady 1s gaze is one fixation, not thirty",
      len(detect_fixations(still)) == 1)
check("a 60ms glance is below the 100ms floor",
      detect_fixations([GazeSample(1000 + i * (1 / 30), 0.5, 0.5) for i in range(2)]) == [])

sweep = [GazeSample(1000 + i * (1 / 30), 0.02 + i * 0.03, 0.5) for i in range(30)]
check("a continuous sweep across the page is not a fixation",
      len(detect_fixations(sweep)) == 0)

noisy_still = syn.scripted_session(
    syn.ecommerce_config(), [("product_image", 1.0)], noise=syn.REALISTIC_NOISE, seed=3)
raw = [(s.x, s.y) for s in noisy_still]
smoothed = smooth_positions(noisy_still)
spread = lambda pts: max(p[0] for p in pts) - min(p[0] for p in pts)      # noqa: E731
check("smoothing reduces the spread of a stationary gaze",
      spread(smoothed) < spread(raw))
check("at realistic gaze error, RAW input yields no usable fixation",
      len(detect_fixations(noisy_still)) == 0)
check("the same gaze, smoothed, yields a fixation",
      len(detect_fixations(noisy_still, positions=smoothed)) >= 1)

print("\nfixation detection -- element boundaries end a fixation")
two_elements = syn.scripted_session(
    syn.ecommerce_config(),
    [("product_title", 0.5), ("checkout_button", 0.5)], noise=0.001, seed=1)
cfg = syn.ecommerce_config()
pos = smooth_positions(two_elements)
labels = [hit_test(cfg.boxes, x, y) for x, y in pos]
unconstrained = detect_fixations(two_elements, positions=pos)
constrained = detect_fixations(two_elements, positions=pos, labels=labels)
check("boundary constraint splits gaze that crossed two elements",
      len(constrained) >= len(unconstrained))
check("no fixation spans two different elements",
      all(len({labels[i] for i, s in enumerate(two_elements)
               if f.start <= s.timestamp <= f.end and labels[i] is not None}) <= 1
          for f in constrained))

print("\nnoise tolerance -- a brief excursion doesn't split a visit")
cfg = syn.ecommerce_config()
cx, cy = cfg.boxes["checkout_button"].center
stream = []
t = 1000.0
for _ in range(60):
    stream.append(GazeSample(t, cx, cy)); t += 1 / 30
for _ in range(2):                        # ~67ms just outside the box
    stream.append(GazeSample(t, cx, cy - 0.06)); t += 1 / 30
for _ in range(60):
    stream.append(GazeSample(t, cx, cy)); t += 1 / 30
trace = attribute(stream, cfg.boxes)
check("a 67ms excursion still yields one continuous visit",
      len([v for v in trace.visits if v.element_id == "checkout_button"]) == 1)


def _visits_and_bridges(mid_samples, boxes, elem):
    """Build 2s-either-side-of-`mid_samples` and report visits + bridges."""
    built = []
    t = 1000.0
    ex, ey = boxes[elem].center
    for _ in range(60):
        built.append(GazeSample(t, ex, ey)); t += 1 / 30
    for mk in mid_samples:
        built.append(mk(t)); t += 1 / 30
    for _ in range(60):
        built.append(GazeSample(t, ex, ey)); t += 1 / 30
    tr = attribute(built, boxes)
    return len([v for v in tr.visits if v.element_id == elem]), tr.bridged_samples


# Two mechanisms preserve a visit and they kick in at different scales:
# smoothing absorbs the smallest excursions before labelling ever sees them,
# and label-bridging catches what's left. The 67ms case above is handled
# entirely by smoothing (bridged == 0), so it can't test bridging -- these can.
blink_visits, blink_bridged = _visits_and_bridges(
    [lambda t: GazeSample(t, cx, cy, valid=False)] * 3, cfg.boxes, "checkout_button")
check("a 100ms blink is bridged into one visit", blink_visits == 1)
check("the blink bridge was recorded, not silent", blink_bridged == 3)

long_blink_visits, _ = _visits_and_bridges(
    [lambda t: GazeSample(t, cx, cy, valid=False)] * 8, cfg.boxes, "checkout_button")
check("a 267ms blink exceeds MAX_GAP and is NOT bridged", long_blink_visits == 2)

ncfg = syn.nested_config()
bx, by = ncfg.boxes["buy_button"].center
flick_visits, flick_bridged = _visits_and_bridges(
    [lambda t: GazeSample(t, bx, by)] * 3, ncfg.boxes, "product_card")
check("a brief flicker onto a nested element doesn't split the parent visit",
      flick_visits == 1)
check("the cross-element bridge was recorded", flick_bridged == 3)

long_away = []
t = 1000.0
for _ in range(60):
    long_away.append(GazeSample(t, cx, cy)); t += 1 / 30
for _ in range(30):                       # 1s genuinely elsewhere
    long_away.append(GazeSample(t, 0.02, 0.97)); t += 1 / 30
for _ in range(60):
    long_away.append(GazeSample(t, cx, cy)); t += 1 / 30
trace2 = attribute(long_away, cfg.boxes)
check("a 1s departure is NOT bridged -- that's two visits",
      len([v for v in trace2.visits if v.element_id == "checkout_button"]) == 2)

# ----------------------------------------------------------------------
print("\nmetrics -- scripted ground truth")
samples, cfg = syn.clean_gaze_session()
report = analyze_session(samples, cfg, session_id="attr_clean_01")
m = report.metrics

check("output IS the agents' SessionMetrics class", isinstance(m, SessionMetrics))
check("total_gaze_time matches the 9.3s script", abs(m.total_gaze_time - 9.3) < 0.2)
check("every configured element appears in dwell_time",
      set(m.dwell_time) == set(cfg.element_ids))
check("every configured element appears in fixation_count",
      set(m.fixation_count) == set(cfg.element_ids))
check("product_image dwell matches its scripted 3.5s",
      abs(m.dwell_time["product_image"] - 3.5) < 0.3)
check("checkout_button TTFF matches its scripted 3.5s onset",
      abs(m.ttff["checkout_button"] - 3.5) < 0.4)
check("product_image is first noticed (TTFF ~0)", m.ttff["product_image"] < 0.3)
check("scanpath follows the scripted order",
      m.scanpath[0] == "product_image" and m.scanpath[-1] == "nav_bar")
check("checkout_button revisited once (scripted twice)",
      m.revisit_count["checkout_button"] == 1)
check("revisit never exceeds fixations - 1",
      all(m.revisit_count[e] <= max(0, m.fixation_count[e] - 1) for e in m.dwell_time))
check("dwell_pct sums to <= 100%",
      sum(m.dwell_pct(e) for e in m.dwell_time) <= 100.5)
check("metadata carried through from the UI config",
      m.element_type["checkout_button"] == "CTA"
      and m.element_importance["checkout_button"] == "high")

print("\nmetrics -- background gaze")
bg_samples = syn.scripted_session(cfg, [("product_image", 1.0), (None, 2.0),
                                        ("product_image", 1.0)])
bg = analyze_session(bg_samples, cfg, session_id="attr_bg")
check("background time is counted in total_gaze_time",
      bg.metrics.total_gaze_time > sum(bg.metrics.dwell_time.values()) + 1.0)
check("background is NOT an element in dwell_time",
      set(bg.metrics.dwell_time) == set(cfg.element_ids))
check("background time is reported separately", bg.background_time > 1.5)
check("background can never win most_attended",
      max(bg.metrics.dwell_time, key=bg.metrics.dwell_time.get) == "product_image")

print("\nmetrics -- an element nobody looked at")
partial = syn.scripted_session(cfg, [("product_image", 3.0)])
p = analyze_session(partial, cfg, session_id="attr_partial")
pm = p.metrics
check("unfixated elements are in dwell_time at 0.0",
      pm.dwell_time["checkout_button"] == 0.0)
check("unfixated elements are OMITTED from ttff",
      "checkout_button" not in pm.ttff)
check("...so first_noticed can't be an element nobody saw",
      min(pm.ttff, key=pm.ttff.get) == "product_image")
check("ttff has no infinities (json.dumps would break)",
      all(v == v and abs(v) != float("inf") for v in pm.ttff.values()))
check("metrics are JSON-serialisable", isinstance(json.dumps(asdict(pm)), str))
check("the omission is surfaced as a warning",
      any("never fixated" in w for w in p.warnings))

print("\nmetrics -- degenerate input is handled, not crashed")
empty = analyze_session([], cfg, session_id="attr_empty")
check("empty gaze stream returns a zeroed report", empty.metrics.total_gaze_time == 0.0)
check("empty stream warns rather than raising",
      any("no valid gaze" in w for w in empty.warnings))
check("dwell_pct on a zero-length session is 0, not a ZeroDivisionError",
      empty.metrics.dwell_pct("checkout_button") == 0.0)

all_blind = [GazeSample(1000 + i / 30, 0.5, 0.5, valid=False) for i in range(60)]
blind = analyze_session(all_blind, cfg, session_id="attr_blind")
check("an all-blink session yields no gaze time", blind.metrics.total_gaze_time == 0.0)
check("dropped samples are counted", blind.dropped_invalid == 60)

print("\nmetrics -- survives realistic gaze noise")
noisy_samples, ncfg = syn.noisy_session()
n = analyze_session(noisy_samples, ncfg, session_id="attr_noisy")
nm = n.metrics
check("every element still fixated at realistic noise + blinks",
      all(e in nm.ttff for e in ncfg.element_ids))
check("TTFF stays close to the clean run despite the noise",
      abs(nm.ttff["checkout_button"] - m.ttff["checkout_button"]) < 0.5)
check("dwell ordering is unchanged by noise",
      sorted(nm.dwell_time, key=nm.dwell_time.get)
      == sorted(m.dwell_time, key=m.dwell_time.get))
check("revisit stays coherent under noise",
      all(nm.revisit_count[e] <= max(0, nm.fixation_count[e] - 1) for e in nm.dwell_time))

# ----------------------------------------------------------------------
print("\nEND TO END -- straight into backend/agents/orchestrator.py")
# agents/ uses flat sibling imports and expects to be run from its own
# directory, so it goes on sys.path only here, only for this section.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import orchestrator                                              # noqa: E402

ignored_samples, icfg = syn.ignored_cta_session()
ignored = analyze_session(ignored_samples, icfg, session_id="attr_ignored_cta")
result = orchestrator.run_pipeline(ignored.metrics)

check("orchestrator accepted our metrics unmodified", result["session_id"] == "attr_ignored_cta")
finding_types = {f["finding_type"] for f in result["behavior_summary"]["findings"]}
print(f"        CTA: ttff={ignored.metrics.ttff['checkout_button']:.1f}s, "
      f"dwell={ignored.metrics.dwell_pct('checkout_button'):.1f}% -> {sorted(finding_types)}")
check("a late CTA produces delayed_discovery", "delayed_discovery" in finding_types)
check("a barely-looked-at CTA produces poor_visibility", "poor_visibility" in finding_types)
check("checkout_button flagged as an ignored important element",
      "checkout_button" in result["behavior_summary"]["ignored_important_elements"])
check("agents produced issues", len(result["issues"]) > 0)
check("the full pipeline result is JSON-serialisable",
      isinstance(json.dumps(result), str))

scattered_samples, scfg = syn.scattered_session()
scattered = analyze_session(scattered_samples, scfg, session_id="attr_scattered")
sresult = orchestrator.run_pipeline(scattered.metrics)
stypes = {f["finding_type"] for f in sresult["behavior_summary"]["findings"]}
print(f"        banner: {scattered.metrics.fixation_count['promo_banner']} fixations, "
      f"scanpath len {len(scattered.metrics.scanpath)} -> {sorted(stypes)}")
check("a repeatedly-revisited banner produces layout_confusion",
      "layout_confusion" in stypes)
check("a non-interactive attention magnet produces misleading_affordance",
      "misleading_affordance" in stypes)

clean_result = orchestrator.run_pipeline(m)
check("the clean session raises no CTA findings",
      not {"delayed_discovery", "poor_visibility"}
      & {f["finding_type"] for f in clean_result["behavior_summary"]["findings"]})

print("\nEND TO END -- the layout also feeds reports/heatmap_stub.py")
layout = icfg.layout_for_heatmap()
check("layout is the (x, y, w, h) shape heatmap_stub expects",
      all(isinstance(v, tuple) and len(v) == 4 for v in layout.values()))
check("layout keys match the metrics keys exactly",
      set(layout) == set(ignored.metrics.dwell_time))

# ----------------------------------------------------------------------
print("\nAPI -- /analyze")
api_req = AnalyzeRequest(
    session_id="api_01",
    ui_page="ecommerce_product_page",
    elements={
        "checkout_button": {"bbox": (0.50, 0.38, 0.28, 0.10),
                            "importance": "high", "type": "CTA"},
        "product_image": {"bbox": (0.05, 0.16, 0.40, 0.55),
                          "importance": "medium", "type": "image"},
    },
    gaze=[{"timestamp": s.timestamp, "x": s.x, "y": s.y,
           "valid": s.valid, "confidence": s.confidence} for s in samples],
)
resp = run(routes.analyze(api_req))
check("endpoint returns metrics", resp.metrics.session_id == "api_01")
check("endpoint returns diagnostics", resp.diagnostics.total_fixations > 0)
check("endpoint returns the heatmap layout", "checkout_button" in resp.heatmap_layout)
check("elements not in the config are simply absent",
      "nav_bar" not in resp.metrics.dwell_time)

print("\nAPI -- pixel bounding boxes via viewport")
px_req = AnalyzeRequest(
    session_id="api_px", ui_page="p",
    elements={"hero": {"x": 96, "y": 108, "width": 960, "height": 540,
                       "importance": "high", "type": "CTA"}},
    viewport=(1920, 1080),
    gaze=[{"timestamp": 1000 + i / 30, "x": 0.3, "y": 0.3} for i in range(60)],
)
px_resp = run(routes.analyze(px_req))
check("pixel boxes normalise and receive gaze", px_resp.metrics.dwell_time["hero"] > 1.0)

print("\nAPI -- validation")
expect_http("unknown element in priority",
            routes.analyze(AnalyzeRequest(
                session_id="s", ui_page="p",
                elements={"a": {"bbox": (0, 0, 0.5, 0.5)}},
                priority=["nope"],
                gaze=[{"timestamp": 1.0, "x": 0.1, "y": 0.1}])), 422)

for bad_elements, why in (
    ({"a": {"bbox": (0, 0, 0.5, 0.5), "importance": "critical"}}, "bad importance"),
    ({"a": {"bbox": (0, 0, 0.5, 0.5), "x": 1, "y": 1, "width": 1, "height": 1}}, "both forms"),
):
    try:
        AnalyzeRequest(session_id="s", ui_page="p", elements=bad_elements, gaze=[])
        check(f"rejects {why}", False)
    except Exception:
        check(f"rejects {why}", True)

check("defaults endpoint reports the thresholds in force",
      run(routes.defaults()).dispersion_threshold > 0)

print("\ninput adapters")
converted = gaze_samples_from_dicts([
    {"timestamp": 1.0, "x": 0.5, "y": 0.5},
    {"t": 1.033, "x": 0.5, "y": 0.5, "valid": False},
])
check("dict -> GazeSample accepts 'timestamp' and 't'", len(converted) == 2)
check("validity carried through", converted[1].valid is False)
try:
    gaze_samples_from_dicts([{"x": 0.5, "y": 0.5}])
    check("a sample with no timestamp is rejected", False)
except ValueError:
    check("a sample with no timestamp is rejected", True)

check("out-of-order gaze is sorted, not trusted",
      analyze_session(list(reversed(samples)), cfg, "ooo").metrics.scanpath[0]
      == m.scanpath[0])

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
