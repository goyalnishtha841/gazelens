"""
agent1_behavior.py

Behavior Analysis Agent. Deliberately 100% rule-based -- no LLM call
anywhere in this file. This agent's job is to turn raw numbers into
labeled observations, and rules are the right tool for that: it's fast,
free, fully deterministic, and testable without mocking an API.

Implements the four rules from the project brief:
  - CTA TTFF > 5s                    -> delayed discovery
  - CTA dwell time < 5% of total     -> poor visibility
  - non-clickable, high fixation     -> misleading visual affordance
  - scanpath jumps repeatedly        -> possible layout confusion
"""

from collections import Counter
from schemas import SessionMetrics, BehaviorFinding, BehaviorSummary
import rules


def _first_noticed(session: SessionMetrics) -> str | None:
    if not session.ttff:
        return None
    return min(session.ttff, key=session.ttff.get)


def _most_attended(session: SessionMetrics) -> str | None:
    if not session.dwell_time:
        return None
    return max(session.dwell_time, key=session.dwell_time.get)


def _ignored_important_elements(session: SessionMetrics) -> list[str]:
    ignored = []
    for element_id, importance in session.element_importance.items():
        if importance != "high":
            continue
        dwell_pct = session.dwell_pct(element_id)
        if dwell_pct < rules.CTA_DWELL_POOR_VISIBILITY_PCT:
            ignored.append(element_id)
    return ignored


def _attention_scattered(session: SessionMetrics) -> bool:
    """Flag scattering if any element is revisited via non-adjacent jumps
    at least SCANPATH_REPEAT_JUMP_THRESHOLD times (not just lingered on)."""
    jump_counts = Counter()
    seen_since_last = set()
    for i, element_id in enumerate(session.scanpath):
        if i == 0:
            continue
        prev = session.scanpath[i - 1]
        if element_id != prev and element_id in seen_since_last:
            jump_counts[element_id] += 1
        seen_since_last.add(element_id)
    return any(count >= rules.SCANPATH_REPEAT_JUMP_THRESHOLD for count in jump_counts.values())


def analyze(session: SessionMetrics) -> BehaviorSummary:
    findings: list[BehaviorFinding] = []

    for element_id, ttff in session.ttff.items():
        if session.element_type.get(element_id) != "CTA":
            continue
        if ttff > rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS:
            findings.append(BehaviorFinding(
                finding_type="delayed_discovery",
                element_id=element_id,
                evidence=f"Time to first fixation was {ttff:.1f}s (threshold: {rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS}s)",
                metric_value=ttff,
            ))

    for element_id in session.dwell_time:
        if session.element_type.get(element_id) != "CTA":
            continue
        dwell_pct = session.dwell_pct(element_id)
        if dwell_pct < rules.CTA_DWELL_POOR_VISIBILITY_PCT:
            findings.append(BehaviorFinding(
                finding_type="poor_visibility",
                element_id=element_id,
                evidence=f"Received only {dwell_pct:.1f}% of total gaze time (threshold: {rules.CTA_DWELL_POOR_VISIBILITY_PCT}%)",
                metric_value=dwell_pct,
            ))

    for element_id, fixations in session.fixation_count.items():
        if session.element_type.get(element_id) != "non-interactive":
            continue
        if fixations >= rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT:
            findings.append(BehaviorFinding(
                finding_type="misleading_affordance",
                element_id=element_id,
                evidence=f"Non-interactive element received {fixations} fixations (threshold: {rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT})",
                metric_value=float(fixations),
            ))

    scattered = _attention_scattered(session)
    if scattered:
        findings.append(BehaviorFinding(
            finding_type="layout_confusion",
            element_id="__session__",
            evidence=f"Scanpath repeatedly jumped back to the same elements (threshold: {rules.SCANPATH_REPEAT_JUMP_THRESHOLD} repeat jumps)",
            metric_value=float(rules.SCANPATH_REPEAT_JUMP_THRESHOLD),
        ))

    return BehaviorSummary(
        session_id=session.session_id,
        first_noticed=_first_noticed(session),
        most_attended=_most_attended(session),
        ignored_important_elements=_ignored_important_elements(session),
        attention_scattered=scattered,
        findings=findings,
    )
