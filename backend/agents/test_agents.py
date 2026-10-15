"""
test_agents.py

Run with: python3 test_agents.py

Checks each agent's logic against the mock sessions, and -- most
importantly -- proves Agent 4 actually rejects a fabricated
recommendation instead of just rubber-stamping everything.
"""

from schemas import Recommendation
import agent1_behavior
import agent2_evaluation
import agent3_recommendation
import agent4_critic
from mock_sessions import clean_session, cluttered_search_session, ignored_cta_session, scattered_session

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


print("Agent 1 -- clean_session should raise no CTA findings")
behavior = agent1_behavior.analyze(clean_session)
check("no delayed_discovery finding", not any(f.finding_type == "delayed_discovery" for f in behavior.findings))
check("no poor_visibility finding", not any(f.finding_type == "poor_visibility" for f in behavior.findings))
check("checkout_button not in ignored list", "checkout_button" not in behavior.ignored_important_elements)

print("\nAgent 1 -- ignored_cta_session should flag both delayed discovery and poor visibility")
behavior2 = agent1_behavior.analyze(ignored_cta_session)
check("delayed_discovery found", any(f.finding_type == "delayed_discovery" for f in behavior2.findings))
check("poor_visibility found", any(f.finding_type == "poor_visibility" for f in behavior2.findings))
check("checkout_button flagged as ignored", "checkout_button" in behavior2.ignored_important_elements)

print("\nAgent 1 -- scattered_session should flag layout_confusion and misleading_affordance")
behavior3 = agent1_behavior.analyze(scattered_session)
check("layout_confusion found", any(f.finding_type == "layout_confusion" for f in behavior3.findings))
check("misleading_affordance found (promo_banner)",
      any(f.finding_type == "misleading_affordance" and f.element_id == "promo_banner" for f in behavior3.findings))

print("\nAgent 1 -- cluttered_search_session should flag the three added heuristic categories")
behavior4 = agent1_behavior.analyze(cluttered_search_session)
check("repeated_revisits found (apply_filters)",
      any(f.finding_type == "repeated_revisits" and f.element_id == "apply_filters" for f in behavior4.findings))
check("high_cognitive_load found", any(f.finding_type == "high_cognitive_load" for f in behavior4.findings))
check("element_never_discovered found (submit_button)",
      any(f.finding_type == "element_never_discovered" and f.element_id == "submit_button"
          for f in behavior4.findings))

print("\nAgent 2 -- the three added finding types map to their own heuristics, not silently dropped")
issues4 = agent2_evaluation.evaluate(behavior4, cluttered_search_session)
heuristics_seen = {i.heuristic for i in issues4}
check("Error prevention present", "Error prevention" in heuristics_seen)
check("Cognitive load present", any("Cognitive load" in h for h in heuristics_seen))
check("Accessibility present", "Accessibility" in heuristics_seen)
check("issue count matches finding count (nothing silently unmapped)",
      len(issues4) == len(behavior4.findings))

print("\nAgent 2 -- every issue must map to a known heuristic")
issues2 = agent2_evaluation.evaluate(behavior2, ignored_cta_session)
check("issues generated", len(issues2) > 0)
check("all issues have a heuristic assigned", all(i.heuristic for i in issues2))
check("issues sorted High first", issues2[0].severity == "High" if issues2 else True)

print("\nAgent 3 -- rule-based mode produces one recommendation per issue")
recs = agent3_recommendation.recommend_all(issues2)
check("recommendation count matches issue count", len(recs) == len(issues2))
check("every recommendation cites evidence", all("Evidence:" in r.recommendation for r in recs))

print("\nAgent 4 -- verifies real recommendations as Strong/Weak, not blanket-accepted")
verified = agent4_critic.verify(recs, ignored_cta_session)
check("at least one recommendation kept", any(v.kept for v in verified))
check("kept recommendations have confidence > 0", all(v.confidence > 0 for v in verified if v.kept))

print("\nAgent 4 -- MUST reject a fabricated recommendation not grounded in real metrics")
fake_rec = Recommendation(
    recommendation="Users are frustrated and abandoning the cart in large numbers, fix the checkout flow immediately.",
    linked_issue="Fabricated issue",
    element_id="checkout_button",
)
# clean_session's checkout_button metrics are FINE -- nothing should verify this claim
fake_verified = agent4_critic.verify([fake_rec], clean_session)
check("fabricated claim rejected (kept=False)", fake_verified[0].kept is False)
check("fabricated claim support is Unsupported", fake_verified[0].support == "Unsupported")

print("\nAgent 4 -- MUST reject generic non-actionable phrasing")
generic_rec = Recommendation(
    recommendation="Just make it better and improve the UI overall.",
    linked_issue="Some issue",
    element_id="checkout_button",
)
generic_verified = agent4_critic.verify([generic_rec], ignored_cta_session)
check("generic phrasing rejected", generic_verified[0].kept is False)

print("\nQuality gate -- how much the chain may claim")
import consolidate   # noqa: E402
import quality_gate  # noqa: E402
from orchestrator import run_pipeline  # noqa: E402

DIAG = (1694 ** 2 + 840 ** 2) ** 0.5    # the pilot laptop's screen, ~1891px
good = quality_gate.assess(quality_gate.QualityInput(
    gaze_error_px=98, error_source="accuracy_check", screen_diagonal_px=DIAG,
    tracked_pct=95, total_gaze_time=40, total_fixations=40))
check("98px over 40s is good, no ceiling", good.level == "good" and good.max_severity == "High")
fair = quality_gate.assess(quality_gate.QualityInput(
    gaze_error_px=166, screen_diagonal_px=DIAG, tracked_pct=95, total_gaze_time=40,
    total_fixations=40))
check("166px is limited: severities capped at Medium",
      fair.level == "limited" and fair.max_severity == "Medium")
bad = quality_gate.assess(quality_gate.QualityInput(
    gaze_error_px=437, screen_diagonal_px=DIAG, tracked_pct=95, total_gaze_time=24,
    total_fixations=40))
check("437px (the first real calibration) is insufficient", bad.level == "insufficient")
check("every reason names its number", any("437px" in r for r in bad.reasons))
check("unmeasured accuracy is limited, not good",
      quality_gate.assess(quality_gate.QualityInput(
          tracked_pct=95, total_gaze_time=40, total_fixations=40)).level == "limited")
check("a 3-second session is insufficient whatever the accuracy",
      quality_gate.assess(quality_gate.QualityInput(
          gaze_error_px=50, screen_diagonal_px=DIAG, tracked_pct=99, total_gaze_time=3,
          total_fixations=40)).level == "insufficient")

print("\nConsolidation -- one issue per element, readable, honest about size")
raw = run_pipeline(ignored_cta_session)
check("ignored CTA: two rules on one element merge into one issue",
      len(raw["issues_raw"]) == 2 and len(raw["issues"]) == 1
      and raw["issues"][0]["merged_count"] == 2 and raw["issues"][0]["also"])
check("merged issue keeps the most severe rating", raw["issues"][0]["severity"] == "High")
check("readable label replaces the id", raw["issues"][0]["element_label"] == "Checkout button")
check("one recommendation card per element", len(raw["recommendations_kept"]) == 1)
check("labels from the page config win over tidied ids",
      consolidate.readable_label("checkout_button", {"checkout_button": "Add to cart"}) == "Add to cart")
check("page-level findings read as 'Whole page'",
      consolidate.readable_label("__session__") == "Whole page")

eid = raw["issues"][0]["element_id"]
small = run_pipeline(ignored_cta_session, quality_gate.QualityInput(
    gaze_error_px=98, error_source="accuracy_check", screen_diagonal_px=DIAG,
    tracked_pct=95, total_gaze_time=40, total_fixations=40), reliability={eid: 0.5})
issue = small["issues"][0]
check("element smaller than the gaze error: downgraded one step, with a caveat",
      issue["severity_raw"] == "High" and issue["severity"] == "Medium" and "98px" in issue["caveat"])
rec = small["recommendations_kept"][0]
check("its recommendation's confidence scales with measurability",
      rec["measurability"] == 0.5 and rec["confidence"] == round(rec["confidence_raw"] * 0.5, 2))

limited = run_pipeline(ignored_cta_session, quality_gate.QualityInput(
    gaze_error_px=166, screen_diagonal_px=DIAG, tracked_pct=95, total_gaze_time=40,
    total_fixations=40))
check("limited session: nothing rated High",
      all(i["severity"] != "High" for i in limited["issues"]))
blocked = run_pipeline(ignored_cta_session, quality_gate.QualityInput(
    gaze_error_px=437, screen_diagonal_px=DIAG, tracked_pct=95, total_gaze_time=40,
    total_fixations=40))
check("insufficient session: no issues or recommendations at all",
      blocked["quality"]["level"] == "insufficient" and not blocked["issues"]
      and not blocked["recommendations_kept"])
check("no quality input = gate skipped (mock data has no measurement)",
      raw["quality"] is None)

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
