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

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed\n{'=' * 40}")

if failed:
    raise SystemExit(1)
