"""
orchestrator.py

Runs the full chain: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4.
This is the function the report/dashboard modules (Task 4/6) will
eventually call with a REAL SessionMetrics object. Nothing in here
changes when the CV pipeline is finished -- only mock_sessions.py
gets replaced by a real metrics source.
"""

from dataclasses import asdict
from schemas import SessionMetrics
import agent1_behavior
import agent2_evaluation
import agent3_recommendation
import agent4_critic


def run_pipeline(session: SessionMetrics) -> dict:
    behavior = agent1_behavior.analyze(session)
    issues = agent2_evaluation.evaluate(behavior, session)
    recommendations = agent3_recommendation.recommend_all(issues)
    verified = agent4_critic.verify(recommendations, session)

    kept = [v for v in verified if v.kept]
    rejected = [v for v in verified if not v.kept]

    return {
        "session_id": session.session_id,
        "behavior_summary": asdict(behavior),
        "issues": [asdict(i) for i in issues],
        "recommendations_kept": [asdict(v) for v in kept],
        "recommendations_rejected": [asdict(v) for v in rejected],
    }


if __name__ == "__main__":
    import json
    from mock_sessions import ALL_MOCK_SESSIONS

    for session in ALL_MOCK_SESSIONS:
        print(f"\n{'=' * 70}\nSESSION: {session.session_id}\n{'=' * 70}")
        result = run_pipeline(session)
        print(json.dumps(result, indent=2))
