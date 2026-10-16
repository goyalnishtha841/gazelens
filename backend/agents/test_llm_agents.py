"""
test_llm_agents.py

LLM mode, with a fake Anthropic client -- no key, no network. Run on its
own (python3 test_llm_agents.py) or as part of test_agents.py.

What it proves:
  * with no key, the chain is the rule-based chain, unchanged
  * with a client, Agents 1-3 use the LLM's text, and the pipeline_result
    shape the frontend and PDF read is the same
  * Agent 4 rejects LLM text whose numbers it can't re-derive -- a wrong
    claim, a number in the prose with no claim, a claim about an element
    that doesn't exist -- and the rejection shows up in the report
  * an API error or a refusal falls back to rules instead of failing
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reports"))

import agent1_behavior
import agent2_evaluation
import agent3_recommendation
import llm_client
from mock_sessions import ignored_cta_session
from orchestrator import run_pipeline

PIPELINE_KEYS = {"session_id", "quality", "element_labels", "behavior_summary", "issues",
                 "issues_raw", "recommendations_kept", "recommendations_raw",
                 "recommendations_rejected", "llm"}

# ignored_cta_session: checkout_button has 0.4s dwell of 20s (2.0%), TTFF 8.4s.
GOOD_NARRATIVE = {
    "narrative": "Their eyes went to the Product image first and stayed there; the Checkout "
                 "button was only found after 8.4s and held 2% of their attention.",
    "claims": [{"element_id": "checkout_button", "metric": "ttff_s", "value": 8.4},
               {"element_id": "checkout_button", "metric": "dwell_pct", "value": 2.0}],
}
GOOD_EXPLANATIONS = {"explanations": [
    {"index": 0, "explanation": "The Checkout button took 8.4s to be noticed, so buying is slow to start.",
     "claims": [{"element_id": "checkout_button", "metric": "ttff_s", "value": 8.4}]},
    {"index": 1, "explanation": "It got 0.4s of looking, too little for the page's main action.",
     "claims": [{"element_id": "checkout_button", "metric": "dwell_time_s", "value": 0.4}]},
]}
GOOD_RECS = {"recommendations": [
    {"index": 0, "recommendation": "Move the Checkout button up beside the Product title so it sits "
                                   "in the first screen people scan, instead of being found after 8.4s.",
     "claims": [{"element_id": "checkout_button", "metric": "ttff_s", "value": 8.4}]},
    {"index": 1, "recommendation": "Give the Checkout button a solid brand-colour fill and 24px of "
                                   "clear space so it stands apart from the Product image.",
     "claims": []},
]}


class FakeClient:
    """Stands in for anthropic.Anthropic(); answers by which agent is asking."""

    def __init__(self, narrative=GOOD_NARRATIVE, explanations=GOOD_EXPLANATIONS,
                 recs=GOOD_RECS, error=None, stop_reason="end_turn"):
        self.answers = {"behaviour analyst": narrative, "UX evaluator": explanations,
                        "recommendation writer": recs}
        self.error, self.stop_reason, self.calls = error, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        answer = next(v for k, v in self.answers.items() if k in kwargs["system"])
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=json.dumps(answer))])


def run(check):
    print("\nLLM mode -- off without a key: the rule-based chain, unchanged")
    llm_client.set_client(None)
    rules_result = run_pipeline(ignored_cta_session)
    check("mode reported as rules", rules_result["llm"] == {"mode": "rules", "model": None, "audit": []})
    check("no narrative or explanations in rules mode",
          rules_result["behavior_summary"]["narrative"] is None
          and all(i["explanation"] is None for i in rules_result["issues"]))
    check("rules mode recommendations are templates",
          all(r["source"] == "rules" for r in rules_result["recommendations_kept"]))

    print("\nLLM mode -- grounded output is used, shape unchanged")
    fake = FakeClient()
    llm_client.set_client(fake)
    result = run_pipeline(ignored_cta_session, labels={"checkout_button": "Checkout button"})
    check("pipeline_result keeps the keys the frontend/PDF read", set(result) == PIPELINE_KEYS)
    check("mode and model reported", result["llm"]["mode"] == "llm"
          and result["llm"]["model"] == llm_client.DEFAULT_MODEL)
    check("three LLM calls (agents 1-3), none from the critic", len(fake.calls) == 3)
    check("requests use structured JSON output",
          all(c["output_config"]["format"]["type"] == "json_schema" for c in fake.calls))
    check("prompts carry the readable label, not just the id",
          all("Checkout button" in c["messages"][0]["content"] for c in fake.calls))
    check("verified narrative kept", result["behavior_summary"]["narrative"] == GOOD_NARRATIVE["narrative"])
    check("verified explanation reaches the consolidated issue",
          result["issues"][0]["explanation"] in {e["explanation"] for e in GOOD_EXPLANATIONS["explanations"]})
    check("rule findings untouched by the LLM",
          [i["heuristic"] for i in result["issues_raw"]] == [i["heuristic"] for i in rules_result["issues_raw"]]
          and [i["severity"] for i in result["issues_raw"]] == [i["severity"] for i in rules_result["issues_raw"]])
    check("LLM fixes kept", result["recommendations_kept"]
          and all(r["source"] == "llm" for r in result["recommendations_raw"]))
    check("nothing rejected when every number re-derives",
          not result["recommendations_rejected"] and not result["llm"]["audit"])

    print("\nLLM mode -- the critic rejects what it can't re-derive")
    bad_recs = {"recommendations": [
        # claim disagrees with the data (real TTFF is 8.4s)
        {"index": 0, "recommendation": "Move the Checkout button higher: it took 12s to find.",
         "claims": [{"element_id": "checkout_button", "metric": "ttff_s", "value": 12}]},
        # number in prose with no claim behind it
        {"index": 1, "recommendation": "Make the Checkout button larger; 40% of shoppers never saw it.",
         "claims": []},
    ]}
    bad_narrative = {"narrative": "They spent 9 seconds on the Promo video.",
                     "claims": [{"element_id": "promo_video", "metric": "dwell_time_s", "value": 9}]}
    llm_client.set_client(FakeClient(narrative=bad_narrative, recs=bad_recs))
    bad = run_pipeline(ignored_cta_session)
    rejected = [r for r in bad["recommendations_rejected"] if r["source"] == "llm"]
    check("both fabricated LLM fixes rejected", len(rejected) == 2)
    check("wrong value named in the reason",
          any("re-computed 8.40" in e for r in rejected for e in r["evidence"]))
    check("unclaimed number named in the reason",
          any('"40%"' in e for r in rejected for e in r["evidence"]))
    check("template fix stands in for the rejected ones",
          bad["recommendations_kept"] and all(r["source"] == "rules" for r in bad["recommendations_kept"]))
    check("narrative about a non-existent element cleared",
          bad["behavior_summary"]["narrative"] is None
          and any(a["agent"] == "Behaviour" for a in bad["llm"]["audit"]))
    check("every rejection is in the audit with reasons",
          len(bad["llm"]["audit"]) == 3 and all(a["reasons"] for a in bad["llm"]["audit"]))

    import report_generator
    html = report_generator._render_html(bad, ignored_cta_session.ui_page, None, None, None)
    check("report shows rejected fixes and why",
          "Thrown out by the critic" in html and "re-computed 8.40" in html)
    check("report shows removed AI text", "AI-written text the critic removed" in html
          and "Promo video" in html)
    good_html = report_generator._render_html(result, ignored_cta_session.ui_page, None, None, None)
    check("report uses the verified narrative", "held 2% of their attention" in good_html)

    print("\nLLM mode -- failures fall back to rules")
    llm_client.set_client(FakeClient(error=RuntimeError("connection reset")))
    errored = run_pipeline(ignored_cta_session)
    check("API error: same issues and fixes as rules mode",
          errored["issues"] == rules_result["issues"]
          and errored["recommendations_kept"] == rules_result["recommendations_kept"])
    llm_client.set_client(FakeClient(stop_reason="refusal"))
    refused = run_pipeline(ignored_cta_session)
    check("refusal: template fixes, no narrative",
          refused["behavior_summary"]["narrative"] is None
          and all(r["source"] == "rules" for r in refused["recommendations_kept"]))
    partial = FakeClient(recs={"recommendations": [GOOD_RECS["recommendations"][0]]})
    llm_client.set_client(partial)
    recs = agent3_recommendation.recommend_all(
        agent2_evaluation.evaluate(agent1_behavior.analyze(ignored_cta_session), ignored_cta_session),
        ignored_cta_session)
    check("an issue the LLM skipped still gets a template fix",
          [r.source for r in recs] == ["llm", "rules"])

    llm_client.set_client(None)


if __name__ == "__main__":
    results = {"passed": 0, "failed": 0}

    def check(label, condition):
        results["passed" if condition else "failed"] += 1
        print(f"  {'PASS' if condition else 'FAIL'}  {label}")

    run(check)
    print(f"\n{'=' * 40}\n{results['passed']} passed, {results['failed']} failed\n{'=' * 40}")
    if results["failed"]:
        raise SystemExit(1)
