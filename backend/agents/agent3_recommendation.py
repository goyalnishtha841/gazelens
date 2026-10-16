"""
agent3_recommendation.py

Recommendation Agent. This is the one agent where an LLM genuinely adds
value (phrasing a concrete, specific fix reads better from a language
model than from a template) -- but it's also the one most likely to
hallucinate, so two things are enforced:

1. RULE-BASED MODE (default, no API key needed): a templated
   recommendation library keyed by heuristic. Use this to build and
   test the full chain, and as the safe fallback the brief's own risk
   table names ("Alternative implementation: templated recommendation
   library, no LLM").

2. LLM MODE (on when ANTHROPIC_API_KEY is set -- see llm_client.py): the
   model gets Agent 2's structured issues plus the session's own metrics
   and readable element names, so it can write a fix specific to this
   page. It must list every number it relies on as a claim; Agent 4
   recomputes each one from the raw session and rejects the fix if any
   doesn't hold. A rejected LLM fix is replaced by the template fix for
   the same issue, which goes through the same critic.
"""

import json
from typing import Dict, Optional

from schemas import SessionMetrics, UXIssue, Recommendation
import llm_client


# --- Mode 1: rule-based template library -----------------------------------

RECOMMENDATION_LIBRARY = {
    "Visibility of system status": [
        "Move the element higher in the visual flow so it's encountered earlier.",
        "Increase the element's size or contrast so it registers faster.",
    ],
    "Visibility and visual hierarchy": [
        "Increase contrast between the element and its background.",
        "Reduce competing visual elements near it.",
        "Add whitespace around it to isolate it visually.",
    ],
    "Match between system and real world": [
        "Reduce visual styling that makes the non-interactive element look clickable.",
        "Add clearer visual distinction between interactive and decorative elements.",
    ],
    "Consistency and standards": [
        "Simplify the layout so scanning order matches reading order.",
        "Group related fields together to reduce back-and-forth scanning.",
    ],
}


def rule_based_recommend(issue: UXIssue) -> Recommendation:
    options = RECOMMENDATION_LIBRARY.get(issue.heuristic, ["Review this element's placement and prominence."])
    # first option in the list is the primary suggestion; keep it deterministic
    text = f"{options[0]} (Evidence: {issue.evidence})"
    return Recommendation(recommendation=text, linked_issue=issue.issue, element_id=issue.element_id)


# --- Mode 2: LLM-backed, evidence-grounded -----------------------------------

RECOMMENDATION_SYSTEM_PROMPT = f"""You are the recommendation writer in a gaze-tracking UX
evaluation. You receive one participant's gaze metrics for a web page and a numbered list of
usability issues (each with heuristic, severity, element and evidence). For EACH issue,
propose exactly ONE concrete, specific fix for that element on this page -- name the
element by its label and say what to change (placement, size, contrast, wording, grouping,
styling). The fix must follow from the evidence given for that issue.

{llm_client.GROUNDING_RULES}"""

RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "recommendation": {"type": "string"},
                    "claims": {"type": "array", "items": llm_client.CLAIM_SCHEMA},
                },
                "required": ["index", "recommendation", "claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["recommendations"],
    "additionalProperties": False,
}


def _llm_recommend_all(issues: list[UXIssue], session: Optional[SessionMetrics],
                       labels: Optional[Dict[str, str]]) -> Dict[int, Recommendation]:
    """index -> LLM recommendation, for the issues the model answered."""
    listed = [{"index": n, "issue": i.issue, "heuristic": i.heuristic, "severity": i.severity,
               "element_id": i.element_id, "label": (labels or {}).get(i.element_id, i.element_id),
               "evidence": i.evidence}
              for n, i in enumerate(issues)]
    context = (f"Session metrics:\n{llm_client.metrics_digest(session, labels)}\n\n"
               if session is not None else "")
    data = llm_client.complete_json(
        RECOMMENDATION_SYSTEM_PROMPT,
        f"{context}Issues:\n{json.dumps(listed, indent=1)}",
        RECOMMENDATION_SCHEMA,
    )
    out: Dict[int, Recommendation] = {}
    for item in (data or {}).get("recommendations") or []:
        n = item.get("index")
        text = str(item.get("recommendation", "")).strip()
        if isinstance(n, int) and 0 <= n < len(issues) and text and n not in out:
            out[n] = Recommendation(
                recommendation=text,
                linked_issue=issues[n].issue,
                element_id=issues[n].element_id,  # from the issue, never from the model
                source="llm",
                claims=list(item.get("claims") or []),
            )
    return out


def recommend_all(issues: list[UXIssue], session: Optional[SessionMetrics] = None,
                  labels: Optional[Dict[str, str]] = None) -> list[Recommendation]:
    """One recommendation per issue, in issue order. LLM where it answered, template otherwise."""
    llm_recs = _llm_recommend_all(issues, session, labels) if issues and llm_client.enabled() else {}
    return [llm_recs.get(n) or rule_based_recommend(issue) for n, issue in enumerate(issues)]
