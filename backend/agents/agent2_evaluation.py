"""
agent2_evaluation.py

UX Evaluation Agent. Takes Agent 1's BehaviorSummary and maps each
finding onto a Nielsen-style heuristic category. Still no LLM here --
this is a lookup table, because "which heuristic does 'poor visibility'
violate" is a fixed, known mapping, not something that needs generation.
"""

from schemas import BehaviorSummary, SessionMetrics, UXIssue
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
}


def evaluate(behavior: BehaviorSummary, session: SessionMetrics) -> list[UXIssue]:
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
    return issues
