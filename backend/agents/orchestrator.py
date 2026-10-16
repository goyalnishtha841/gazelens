"""
orchestrator.py

Runs the full chain: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4.
This is the function the report/dashboard modules (Task 4/6) will
eventually call with a REAL SessionMetrics object. Nothing in here
changes when the CV pipeline is finished -- only mock_sessions.py
gets replaced by a real metrics source.
"""

from dataclasses import asdict
from typing import Dict, Optional

from schemas import SessionMetrics
import agent1_behavior
import agent2_evaluation
import agent3_recommendation
import agent4_critic
import consolidate
import llm_client
import quality_gate


def run_pipeline(
    session: SessionMetrics,
    quality: Optional[quality_gate.QualityInput] = None,
    labels: Optional[Dict[str, str]] = None,
    reliability: Optional[Dict[str, float]] = None,
) -> dict:
    """Quality gate -> Agents 1-4 -> consolidation.

    quality: how trustworthy the session's gaze was (see quality_gate.py).
      None skips the gate -- mock sessions and the agent tests have no
      measurement behind them to judge.
    labels: element_id -> readable name, for the report.
    reliability: element_id -> size/gaze-error ratio, from attribution.

    "issues" and "recommendations_kept" are the consolidated lists (one per
    element); "issues_raw" / "recommendations_raw" keep the agents' own
    output for audit.

    "llm" says which mode ran and lists every piece of LLM text the critic
    threw out ("audit"), with its reasons. Rule-based mode is the default;
    see llm_client.py for how LLM mode is switched on.
    """
    verdict = quality_gate.assess(quality) if quality is not None else None
    labels = labels or {}
    result = {
        "session_id": session.session_id,
        "quality": asdict(verdict) if verdict else None,
        "element_labels": {e: consolidate.readable_label(e, labels)
                           for e in session.element_type},
        "llm": {"mode": "llm" if llm_client.enabled() else "rules",
                "model": llm_client.model_name() if llm_client.enabled() else None,
                "audit": []},
    }

    if verdict is not None and verdict.level == "insufficient":
        # Don't let rules fire on numbers we already know are noise.
        result.update({
            "behavior_summary": {"session_id": session.session_id, "first_noticed": None,
                                 "most_attended": None, "ignored_important_elements": [],
                                 "attention_scattered": False, "findings": []},
            "issues": [], "issues_raw": [],
            "recommendations_kept": [], "recommendations_raw": [],
            "recommendations_rejected": [],
        })
        return result

    names = result["element_labels"]
    behavior = agent1_behavior.analyze(session, names)
    issues = agent2_evaluation.evaluate(behavior, session, names)
    recommendations = agent3_recommendation.recommend_all(issues, session, names)

    # The critic re-checks every LLM claim against the raw metrics.
    audit = agent4_critic.audit_behavior(behavior, session)
    audit += agent4_critic.audit_issues(issues, session)
    verified = agent4_critic.verify(recommendations, session)

    # A thrown-out LLM fix stays in the rejected list; its issue still gets
    # the template fix, which the critic checks the same way.
    fallbacks = [agent3_recommendation.rule_based_recommend(issue)
                 for issue, v in zip(issues, verified, strict=True) if v.source == "llm" and not v.kept]
    for v in verified:
        if v.source == "llm" and not v.kept:
            audit.append({"agent": "Recommendation", "element_id": v.element_id,
                          "text": v.recommendation, "reasons": v.evidence})
    verified += agent4_critic.verify(fallbacks, session)
    result["llm"]["audit"] = audit

    kept = [asdict(v) for v in verified if v.kept]
    rejected = [asdict(v) for v in verified if not v.kept]
    raw_issues = [asdict(i) for i in issues]
    gaze_error = verdict.gaze_error_px if verdict else None

    result.update({
        "behavior_summary": asdict(behavior),
        "issues": consolidate.merge_issues(
            raw_issues, labels, reliability, gaze_error,
            max_severity=verdict.max_severity if verdict else "High"),
        "issues_raw": raw_issues,
        "recommendations_kept": consolidate.merge_recommendations(kept, labels, reliability),
        "recommendations_raw": kept,
        "recommendations_rejected": rejected,
    })
    return result


if __name__ == "__main__":
    import json
    from mock_sessions import ALL_MOCK_SESSIONS

    for session in ALL_MOCK_SESSIONS:
        print(f"\n{'=' * 70}\nSESSION: {session.session_id}\n{'=' * 70}")
        result = run_pipeline(session)
        print(json.dumps(result, indent=2))
