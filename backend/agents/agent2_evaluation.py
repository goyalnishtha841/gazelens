"""
agent2_evaluation.py

UX Evaluation Agent. Takes Agent 1's BehaviorSummary and maps each
finding onto a Nielsen-style heuristic category. The mapping and the
severity stay a lookup table, because "which heuristic does 'poor
visibility' violate" is a fixed, known mapping, not something to generate.

In LLM mode the agent additionally asks the model to explain each issue in
plain English for this specific page -- what the participant's gaze shows
and why it matters here. The model cannot add issues, drop them, or change
their heuristic or severity; Agent 4 clears any explanation whose numbers
it cannot re-derive.
"""

import json
from typing import Dict, Optional

from schemas import BehaviorSummary, SessionMetrics, UXIssue
import llm_client
import rules

# finding_type -> (heuristic name, issue label template)
HEURISTIC_MAP = {
    "delayed_discovery": (
        "Visibility of system status",
        "Primary action discovered late",
    ),
    "poor_visibility": (
        "Visibility and visual hierarchy",
        "Primary CTA received minimal attention",
    ),
    "misleading_affordance": (
        "Match between system and real world",
        "Non-interactive element visually competes with real controls",
    ),
    "layout_confusion": (
        "Consistency and standards",
        "Layout structure likely causing disorientation",
    ),
    "repeated_revisits": (
        "Error prevention",
        "Interactive element revisited repeatedly",
    ),
    "high_cognitive_load": (
        "Cognitive load / minimalist design",
        "Attention scattered across the page without settling",
    ),
    "element_never_discovered": (
        "Accessibility",
        "High-importance element received no attention at all",
    ),
}


def evaluate(behavior: BehaviorSummary, session: SessionMetrics,
             labels: Optional[Dict[str, str]] = None) -> list[UXIssue]:
    issues: list[UXIssue] = []

    for finding in behavior.findings:
        if finding.finding_type not in HEURISTIC_MAP:
            continue  # unknown finding type -- fail closed, don't guess a heuristic

        heuristic, issue_label = HEURISTIC_MAP[finding.finding_type]
        importance = session.element_importance.get(finding.element_id, "medium")
        severity = rules.SEVERITY_BY_ELEMENT_IMPORTANCE.get(importance, "Medium")

        issues.append(UXIssue(
            issue=issue_label,
            severity=severity,
            evidence=finding.evidence,
            heuristic=heuristic,
            element_id=finding.element_id,
        ))

    # sort High -> Medium -> Low so downstream agents/report see priority order
    order = {"High": 0, "Medium": 1, "Low": 2}
    issues.sort(key=lambda i: order.get(i.severity, 1))
    if issues and llm_client.enabled():
        _llm_explain(issues, session, labels)
    return issues


# --- LLM mode: per-issue explanations -----------------------------------------

EXPLAIN_SYSTEM_PROMPT = f"""You are the UX evaluator in a gaze-tracking usability study.
You receive one participant's gaze metrics for a web page and a numbered list of issues a
rule engine found, each already mapped to a usability heuristic with a severity. For EACH
issue, write 1-2 sentences explaining what the gaze data shows about that part of this page
and why it matters for someone trying to use it. Keep the given heuristic and severity;
do not add, merge or drop issues.

{llm_client.GROUNDING_RULES}"""

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "explanation": {"type": "string"},
                    "claims": {"type": "array", "items": llm_client.CLAIM_SCHEMA},
                },
                "required": ["index", "explanation", "claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["explanations"],
    "additionalProperties": False,
}


def _llm_explain(issues: list[UXIssue], session: SessionMetrics,
                 labels: Optional[Dict[str, str]]) -> None:
    listed = [{"index": n, "issue": i.issue, "heuristic": i.heuristic, "severity": i.severity,
               "element_id": i.element_id, "evidence": i.evidence}
              for n, i in enumerate(issues)]
    user = (f"Session metrics:\n{llm_client.metrics_digest(session, labels)}\n\n"
            f"Issues:\n{json.dumps(listed, indent=1)}")
    data = llm_client.complete_json(EXPLAIN_SYSTEM_PROMPT, user, EXPLAIN_SCHEMA)
    if not data:
        return
    for item in llm_client.dict_items(data, "explanations"):
        n = item.get("index")
        text = str(item.get("explanation", "")).strip()
        if isinstance(n, int) and 0 <= n < len(issues) and text:
            issues[n].explanation = text
            issues[n].explanation_claims = llm_client.dict_items(item, "claims")
