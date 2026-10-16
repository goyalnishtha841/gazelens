"""
agent4_critic.py

Critic/Verifier Agent. This is the agent that makes the whole system
"not decorative": every recommendation from Agent 3 gets checked against
the RAW session metrics again, independently -- it does not trust Agent
1/2/3's evidence field at face value, it re-derives the underlying
condition itself. If a recommendation can't be re-verified, it is
rejected outright and does not reach the final report.

Two independent checks:
  1. Numeric re-verification: does the underlying metric condition that
     justified this issue still hold, computed fresh from session data?
  2. Text-level check: does the recommendation contain banned generic
     phrasing that signals the LLM ignored the "cite evidence" instruction?

LLM-written text (Agent 1's narrative, Agent 2's explanations, Agent 3's
fixes) gets a third check, and this agent never calls an LLM itself:
  3. Claim re-derivation: every {element_id, metric, value} the model
     listed is recomputed from the raw session and must match; and every
     metric-like number in the prose ("4.2s", "3%", "7 fixations") must
     match a verified claim or a rule threshold. One miss rejects the text.
     A rejected fix is kept=False (it shows under "thrown out" in the
     report); a rejected narrative or explanation is cleared, and either
     way the rejection is logged for the report's audit section.
"""

import re
from typing import List, Optional

from schemas import (SessionMetrics, Recommendation, VerifiedRecommendation,
                     BehaviorSummary, UXIssue)
import rules

BANNED_GENERIC_PHRASES = [
    "make it better",
    "improve the ui",
    "improve the design",
    "make it more user friendly",
    "enhance user experience",
]


def _text_is_generic(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in BANNED_GENERIC_PHRASES)


def _repeat_jumps(scanpath: list[str]) -> int:
    """Most times any one element was jumped back to (not just lingered on),
    counted fresh here rather than taken from Agent 1."""
    jumps: dict[str, int] = {}
    seen: set[str] = set()
    for prev, element_id in zip(scanpath, scanpath[1:]):
        if element_id != prev and element_id in seen:
            jumps[element_id] = jumps.get(element_id, 0) + 1
        seen.add(element_id)
    return max(jumps.values(), default=0)


def _reverify_session(session: SessionMetrics) -> list[str]:
    """Page-level conditions (layout confusion, cognitive load), recomputed."""
    evidence: list[str] = []
    jumps = _repeat_jumps(session.scanpath)
    if jumps >= rules.SCANPATH_REPEAT_JUMP_THRESHOLD:
        evidence.append(f"Scanpath re-checked: an element was jumped back to {jumps} times "
                        f">= {rules.SCANPATH_REPEAT_JUMP_THRESHOLD} threshold")
    distinct = len(set(session.scanpath))
    top_dwell = max((session.dwell_pct(e) for e in session.dwell_time), default=0.0)
    if (distinct >= rules.COGNITIVE_LOAD_MIN_DISTINCT_ELEMENTS
            and top_dwell < rules.COGNITIVE_LOAD_MAX_TOP_ELEMENT_DWELL_PCT):
        evidence.append(f"Attention spread re-checked: {distinct} distinct elements "
                        f">= {rules.COGNITIVE_LOAD_MIN_DISTINCT_ELEMENTS}, top dwell {top_dwell:.1f}% "
                        f"< {rules.COGNITIVE_LOAD_MAX_TOP_ELEMENT_DWELL_PCT}% threshold")
    return evidence


def _reverify_element(element_id: str, session: SessionMetrics) -> list[str]:
    """Element-level conditions, recomputed from the raw session."""
    evidence: list[str] = []
    dwell_pct = session.dwell_pct(element_id)
    ttff = session.ttff.get(element_id)
    fixations = session.fixation_count.get(element_id, 0)
    revisits = session.revisit_count.get(element_id, 0)
    el_type = session.element_type.get(element_id)

    if el_type == "CTA" and ttff is not None and ttff > rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS:
        evidence.append(f"TTFF re-checked: {ttff:.1f}s > {rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS}s threshold")

    # a CTA never looked at has no dwell entry; it's at 0%, not "absent"
    if el_type == "CTA" and dwell_pct < rules.CTA_DWELL_POOR_VISIBILITY_PCT:
        evidence.append(f"Dwell time re-checked: {dwell_pct:.1f}% < {rules.CTA_DWELL_POOR_VISIBILITY_PCT}% threshold")

    if el_type == "non-interactive" and fixations >= rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT:
        evidence.append(f"Fixation count re-checked: {fixations} >= {rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT} threshold")

    if el_type in ("CTA", "form_field") and revisits >= rules.REVISIT_ERROR_PREVENTION_COUNT:
        evidence.append(f"Revisit count re-checked: {revisits} >= {rules.REVISIT_ERROR_PREVENTION_COUNT} threshold")

    if (session.element_importance.get(element_id) == "high" and fixations == 0
            and session.total_gaze_time >= rules.ACCESSIBILITY_MIN_SESSION_GAZE_TIME_SECONDS):
        evidence.append(f"Fixation count re-checked: 0 fixations on a high-importance element across a "
                        f"{session.total_gaze_time:.1f}s session "
                        f"(>= {rules.ACCESSIBILITY_MIN_SESSION_GAZE_TIME_SECONDS}s minimum)")
    return evidence


def _reverify_against_metrics(rec: Recommendation, session: SessionMetrics) -> tuple[str, list[str], float]:
    """
    Returns (support_level, evidence_list, confidence).
    Independently recomputes whether SOMETHING is actually wrong with
    rec.element_id, without trusting rec.recommendation's claims.
    Every Agent 1 rule has a matching re-check here, using the same
    thresholds from rules.py.
    """
    element_id = rec.element_id

    if element_id == "__session__":
        evidence = _reverify_session(session)
    else:
        # an element on the page config but never looked at is still real --
        # it just has no dwell/ttff entry
        known = (element_id in session.element_type or element_id in session.element_importance
                 or element_id in session.dwell_time or element_id in session.ttff)
        if not known:
            return "Unsupported", [f"Element '{element_id}' not found in session metrics at all"], 0.0
        evidence = _reverify_element(element_id, session)

    if not evidence:
        # nothing we independently recomputed backs this up
        return "Unsupported", ["No matching metric condition found on re-check"], 0.0

    # 0.4 per confirmed condition, plus a small bump for having any; cap below 1.0
    confidence = min(0.4 * len(evidence) + 0.2, 0.95)
    support = "Strong" if confidence >= 0.6 else "Weak"
    return support, evidence, round(confidence, 2)


# --- Claim re-derivation (LLM output) ----------------------------------------

SESSION_ELEMENT = "__session__"
SESSION_METRICS = {"total_gaze_time_s", "distinct_elements"}

# A number followed by one of these is a measurement claim. Plain design
# numbers ("16px", "2 columns") aren't, and are left alone.
_METRIC_NUMBER = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%|percent\b|s\b|secs?\b|seconds?\b|fixations?\b|"
    r"times\b|revisits?\b|visits?\b|glances?\b|elements?\b)",
    re.IGNORECASE,
)

_THRESHOLDS = [
    rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS, rules.CTA_DWELL_POOR_VISIBILITY_PCT,
    rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT, rules.SCANPATH_REPEAT_JUMP_THRESHOLD,
    rules.REVISIT_ERROR_PREVENTION_COUNT, rules.COGNITIVE_LOAD_MIN_DISTINCT_ELEMENTS,
    rules.COGNITIVE_LOAD_MAX_TOP_ELEMENT_DWELL_PCT, rules.ACCESSIBILITY_MIN_SESSION_GAZE_TIME_SECONDS,
]


def derive_metric(session: SessionMetrics, element_id: str, metric: str) -> Optional[float]:
    """Recompute one metric from the raw session. None if it can't be derived."""
    if metric in SESSION_METRICS:
        if element_id != SESSION_ELEMENT:
            return None
        if metric == "total_gaze_time_s":
            return session.total_gaze_time
        return float(len(set(session.scanpath)))
    if element_id not in session.element_type and element_id not in session.dwell_time:
        return None
    if metric == "dwell_time_s":
        return session.dwell_time.get(element_id, 0.0)
    if metric == "dwell_pct":
        return session.dwell_pct(element_id)
    if metric == "ttff_s":
        return session.ttff.get(element_id)
    if metric == "fixation_count":
        return float(session.fixation_count.get(element_id, 0))
    if metric == "revisit_count":
        return float(session.revisit_count.get(element_id, 0))
    return None


def _close(a: float, b: float, rel: float, floor: float) -> bool:
    return abs(a - b) <= max(floor, rel * abs(b))


def check_llm_text(text: str, claims: List[dict], session: SessionMetrics) -> List[str]:
    """Problems with one piece of LLM text; empty means every number re-derived."""
    problems: List[str] = []
    verified: List[float] = []
    for claim in claims or []:
        eid, metric, value = claim.get("element_id"), claim.get("metric"), claim.get("value")
        if not isinstance(value, (int, float)):
            problems.append(f"Claim without a numeric value: {claim}")
            continue
        actual = derive_metric(session, eid, metric)
        if actual is None:
            problems.append(f"Cannot re-derive {metric} for '{eid}' from the session")
        elif not _close(float(value), actual, rel=0.02, floor=0.1):
            problems.append(f"Claimed {metric} of '{eid}' = {value:g}, re-computed {actual:.2f}")
        else:
            verified.append(float(value))

    allowed = verified + [float(t) for t in _THRESHOLDS]
    for match in _METRIC_NUMBER.finditer(text or ""):
        number = float(match.group(1))
        # prose rounds, so allow half a unit either way
        if not any(_close(number, v, rel=0.05, floor=0.5) for v in allowed):
            problems.append(f"\"{match.group(0).strip()}\" in the text matches no verified metric")
    return problems


def _audit_entry(agent: str, element_id: str, text: str, problems: List[str]) -> dict:
    return {"agent": agent, "element_id": element_id, "text": text, "reasons": problems}


def audit_behavior(behavior: BehaviorSummary, session: SessionMetrics) -> List[dict]:
    """Clear Agent 1's narrative if it fails re-check; return the rejection, if any."""
    if not behavior.narrative:
        return []
    problems = check_llm_text(behavior.narrative, behavior.narrative_claims, session)
    if not problems:
        return []
    entry = _audit_entry("Behaviour", SESSION_ELEMENT, behavior.narrative, problems)
    behavior.narrative, behavior.narrative_claims = None, []
    return [entry]


def audit_issues(issues: List[UXIssue], session: SessionMetrics) -> List[dict]:
    """Clear any Agent 2 explanation that fails re-check; return the rejections."""
    rejected = []
    for issue in issues:
        if not issue.explanation:
            continue
        problems = check_llm_text(issue.explanation, issue.explanation_claims, session)
        if problems:
            rejected.append(_audit_entry("Evaluation", issue.element_id, issue.explanation, problems))
            issue.explanation, issue.explanation_claims = None, []
    return rejected


def verify(recommendations: list[Recommendation], session: SessionMetrics) -> list[VerifiedRecommendation]:
    verified = []
    for rec in recommendations:
        support, evidence, confidence = _reverify_against_metrics(rec, session)

        if rec.source == "llm":
            problems = check_llm_text(rec.recommendation, rec.claims, session)
            if problems:
                support, confidence = "Unsupported", 0.0
                evidence = [f"Rejected: {p}" for p in problems]

        if _text_is_generic(rec.recommendation):
            support = "Unsupported"
            confidence = 0.0
            evidence = ["Rejected: recommendation used banned generic phrasing instead of a specific fix"]

        kept = support != "Unsupported"

        verified.append(VerifiedRecommendation(
            recommendation=rec.recommendation,
            element_id=rec.element_id,
            support=support,
            evidence=evidence,
            confidence=confidence,
            kept=kept,
            source=rec.source,
        ))
    return verified
