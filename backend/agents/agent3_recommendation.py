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

2. LLM MODE (opt-in): the prompt is given ONLY Agent 2's structured
   issue list -- never the raw session, never the scanpath, never
   anything the model could use to invent plausible-sounding but
   unverified detail. Agent 4 checks its output against the real
   metrics regardless of which mode produced it.

Switch modes with USE_LLM = True below, after wiring in your API key.
"""

from schemas import UXIssue, Recommendation

USE_LLM = False  # flip to True once agent4_critic and your API key are ready


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


def _rule_based_recommend(issue: UXIssue) -> Recommendation:
    options = RECOMMENDATION_LIBRARY.get(issue.heuristic, ["Review this element's placement and prominence."])
    # first option in the list is the primary suggestion; keep it deterministic
    text = f"{options[0]} (Evidence: {issue.evidence})"
    return Recommendation(recommendation=text, linked_issue=issue.issue, element_id=issue.element_id)


# --- Mode 2: LLM-backed, constrained prompt ---------------------------------

RECOMMENDATION_SYSTEM_PROMPT = """You are a UX recommendation generator. You will be given a single
structured issue (heuristic, severity, evidence) and nothing else -- no raw
session data, no screenshots, no scanpath.

Rules:
- Propose exactly ONE concrete, actionable fix.
- Your recommendation MUST reference the evidence field you were given.
- Do NOT invent numbers, user counts, or details not present in the input.
- Do NOT use generic phrases like "improve the UI" or "make it better."
- Output ONLY the recommendation sentence. No preamble.
"""


def _llm_recommend(issue: UXIssue) -> Recommendation:
    """
    Wire your actual API call in here. Example shape using the Anthropic
    Python SDK (pip install anthropic):

        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=RECOMMENDATION_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"Heuristic: {issue.heuristic}\\n"
                    f"Severity: {issue.severity}\\n"
                    f"Evidence: {issue.evidence}\\n"
                    f"Issue: {issue.issue}"
                ),
            }],
        )
        text = response.content[0].text.strip()
        return Recommendation(recommendation=text, linked_issue=issue.issue, element_id=issue.element_id)

    Left unimplemented here so the module runs with zero external
    dependencies until you're ready to wire in a real key.
    """
    raise NotImplementedError(
        "LLM mode not wired up yet -- add your API call above, or keep USE_LLM = False."
    )


def recommend_all(issues: list[UXIssue]) -> list[Recommendation]:
    fn = _llm_recommend if USE_LLM else _rule_based_recommend
    return [fn(issue) for issue in issues]
