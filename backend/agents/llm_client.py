"""
llm_client.py

The one place the agent chain talks to an LLM. Agents 1-3 call
`complete_json()`; Agent 4 (the critic) never does -- it stays
deterministic and re-checks whatever the LLM wrote.

LLM mode is OFF unless an API key is present, so tests, CI and offline use
run the rule-based path with no network and no extra setup:

  ANTHROPIC_API_KEY     turns LLM mode on (read by the Anthropic SDK)
  GAZELENS_LLM=off      forces rule-based mode even with a key set
  GAZELENS_LLM_MODEL    model id, default claude-opus-5-5
  GAZELENS_LLM_EFFORT   low | medium | high, default medium

Any failure -- no SDK installed, network error, refusal, malformed JSON --
returns None, and the calling agent falls back to its rule-based output
for that step. The pipeline never fails because the LLM did.

Tests inject a fake client with `set_client()`.
"""

import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 16000

# Shared by every LLM agent. Each claim names one number the text relies
# on, so the critic can recompute it from the raw session instead of
# trusting the prose.
CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "element_id": {"type": "string"},
        "metric": {"type": "string", "enum": [
            "dwell_time_s", "dwell_pct", "ttff_s", "fixation_count",
            "revisit_count", "total_gaze_time_s", "distinct_elements",
        ]},
        "value": {"type": "number"},
    },
    "required": ["element_id", "metric", "value"],
    "additionalProperties": False,
}

GROUNDING_RULES = """Grounding rules (a separate checker recomputes every number from the raw data and
discards anything it cannot reproduce):
- Use ONLY the metrics you are given. Never invent participants, percentages, timings or counts.
- Every number you write in prose must also appear in your "claims" list as
  {element_id, metric, value}. Use element_id "__session__" for whole-page metrics
  (total_gaze_time_s, distinct_elements).
- Refer to elements by their readable label in prose, by element_id in claims.
- Plain English for a product team, not academic UX jargon. No generic advice such as
  "improve the UI" or "enhance user experience"."""

_client: Any = None
_client_set = False


def set_client(client: Any) -> None:
    """Inject a client (tests), or None to force rule-based mode."""
    global _client, _client_set
    _client, _client_set = client, True


def reset_client() -> None:
    """Back to reading the environment on next use."""
    global _client, _client_set
    _client, _client_set = None, False


def model_name() -> str:
    return os.environ.get("GAZELENS_LLM_MODEL", DEFAULT_MODEL)


def get_client() -> Any:
    global _client, _client_set
    if _client_set:
        return _client
    _client_set = True
    if os.environ.get("GAZELENS_LLM", "").lower() in ("off", "0", "false", "no"):
        _client = None
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        _client = None
    else:
        try:
            import anthropic
            _client = anthropic.Anthropic()
        except ImportError:
            log.warning("ANTHROPIC_API_KEY is set but the anthropic package is not "
                        "installed; using rule-based agents")
            _client = None
    return _client


def enabled() -> bool:
    return get_client() is not None


def complete_json(system: str, user: str, schema: dict) -> Optional[dict]:
    """One structured-output call. Returns the parsed JSON, or None on any failure."""
    client = get_client()
    if client is None:
        return None
    try:
        response = client.beta.messages.create(
            model=model_name(),
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": os.environ.get("GAZELENS_LLM_EFFORT", DEFAULT_EFFORT),
                "format": {"type": "json_schema", "schema": schema},
            },
            # On a safety decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except Exception as exc:  # network, auth, rate limit, bad request: all mean "use rules"
        log.warning("LLM call failed (%s); using rule-based output", exc)
        return None

    if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
        log.warning("LLM stopped with %s; using rule-based output", response.stop_reason)
        return None
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON; using rule-based output")
        return None
    return data if isinstance(data, dict) else None


def metrics_digest(session, labels: Optional[dict] = None) -> str:
    """The session as compact JSON for a prompt -- the same numbers the critic will check."""
    labels = labels or {}
    elements = []
    for eid in session.element_type:
        elements.append({
            "element_id": eid,
            "label": labels.get(eid, eid),
            "type": session.element_type.get(eid),
            "importance": session.element_importance.get(eid),
            "dwell_time_s": round(session.dwell_time.get(eid, 0.0), 2),
            "dwell_pct": round(session.dwell_pct(eid), 1),
            "ttff_s": None if eid not in session.ttff else round(session.ttff[eid], 2),
            "fixation_count": session.fixation_count.get(eid, 0),
            "revisit_count": session.revisit_count.get(eid, 0),
        })
    return json.dumps({
        "page": session.ui_page,
        "total_gaze_time_s": round(session.total_gaze_time, 2),
        "distinct_elements": len(set(session.scanpath)),
        "scanpath_first_20": session.scanpath[:20],
        "elements": elements,
    }, indent=1)
