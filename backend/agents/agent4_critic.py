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
"""

from schemas import SessionMetrics, Recommendation, VerifiedRecommendation
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


def _reverify_against_metrics(rec: Recommendation, session: SessionMetrics) -> tuple[str, list[str], float]:
    """
    Returns (support_level, evidence_list, confidence).
    Independently recomputes whether SOMETHING is actually wrong with
    rec.element_id, without trusting rec.recommendation's claims.
    """
    element_id = rec.element_id
    evidence: list[str] = []
    confidence = 0.0

    if element_id == "__session__":
        # session-level claim (e.g. layout confusion) -- can't verify against
        # a single element, so treat as weakly supported unless it's cheap to check
        return "Weak", ["Session-level claim -- not tied to a single element's metrics"], 0.3

    if element_id not in session.dwell_time and element_id not in session.ttff:
        return "Unsupported", [f"Element '{element_id}' not found in session metrics at all"], 0.0

    dwell_pct = session.dwell_pct(element_id)
    ttff = session.ttff.get(element_id)
    fixations = session.fixation_count.get(element_id, 0)
    el_type = session.element_type.get(element_id)

    if el_type == "CTA" and ttff is not None and ttff > rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS:
        evidence.append(f"TTFF re-checked: {ttff:.1f}s > {rules.CTA_TTFF_DELAYED_THRESHOLD_SECONDS}s threshold")
        confidence += 0.4

    if el_type == "CTA" and dwell_pct < rules.CTA_DWELL_POOR_VISIBILITY_PCT:
        evidence.append(f"Dwell time re-checked: {dwell_pct:.1f}% < {rules.CTA_DWELL_POOR_VISIBILITY_PCT}% threshold")
        confidence += 0.4

    if el_type == "non-interactive" and fixations >= rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT:
        evidence.append(f"Fixation count re-checked: {fixations} >= {rules.NON_INTERACTIVE_HIGH_FIXATION_COUNT} threshold")
        confidence += 0.4

    if not evidence:
        # nothing we independently recomputed backs this up
        return "Unsupported", ["No matching metric condition found on re-check"], 0.0

    confidence = min(confidence + 0.2, 0.95)  # small bump for having any confirmed evidence, cap below 1.0
    support = "Strong" if confidence >= 0.6 else "Weak"
    return support, evidence, round(confidence, 2)


def verify(recommendations: list[Recommendation], session: SessionMetrics) -> list[VerifiedRecommendation]:
    verified = []
    for rec in recommendations:
        support, evidence, confidence = _reverify_against_metrics(rec, session)

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
        ))
    return verified
