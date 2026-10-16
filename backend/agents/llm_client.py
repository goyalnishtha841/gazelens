"""
llm_client.py

The one place the agent chain talks to an LLM. Agents 1-3 call
`complete_json()`; Agent 4 (the critic) never does -- it stays
deterministic and re-checks whatever the LLM wrote.

LLM mode is OFF unless an API key is present, so tests, CI and offline use
run the rule-based path with no network and no extra setup. Two providers:

  GROQ_API_KEY            Groq (free tier available), default openai/gpt-oss-120b
  ANTHROPIC_API_KEY       Claude, default claude-opus-5-5
  GAZELENS_LLM_PROVIDER   groq | anthropic -- only needed when both keys are set
                          (otherwise Anthropic wins)
  GAZELENS_LLM=off        forces rule-based mode even with a key set
  GAZELENS_LLM_MODEL      overrides the provider's default model
  GAZELENS_LLM_EFFORT     low | medium | high, default medium

Both providers are asked for strict JSON-schema output, so the agents and
the critic see the same shape whichever one ran.

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

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "groq": "openai/gpt-oss-120b"}
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
- Write every measured number as digits ("5 times", not "five times"), so it can be checked.
- Numbers that describe a DESIGN CHANGE are not measurements: give them in px or in words
  ("24px of padding", "noticeably larger"), never as a percentage or in seconds -- a "%" or
  "s" in your text is read as a measurement claim and must match the data.
- Refer to elements by their readable label in prose, by element_id in claims.
- Plain English for a product team, not academic UX jargon. No generic advice such as
  "improve the UI" or "enhance user experience"."""

_client: Any = None
_provider: Optional[str] = None
_client_set = False


def set_client(client: Any, provider: str = "anthropic") -> None:
    """Inject a client (tests), or None to force rule-based mode."""
    global _client, _provider, _client_set
    _client, _provider, _client_set = client, (provider if client is not None else None), True


def reset_client() -> None:
    """Back to reading the environment on next use."""
    global _client, _provider, _client_set
    _client, _provider, _client_set = None, None, False


def _pick_provider() -> Optional[str]:
    chosen = os.environ.get("GAZELENS_LLM_PROVIDER", "").lower()
    has = {"anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
           "groq": bool(os.environ.get("GROQ_API_KEY"))}
    if chosen in has:
        return chosen if has[chosen] else None
    if has["anthropic"]:
        return "anthropic"
    return "groq" if has["groq"] else None


def get_client() -> Any:
    global _client, _provider, _client_set
    if _client_set:
        return _client
    _client_set = True
    _client = _provider = None
    if os.environ.get("GAZELENS_LLM", "").lower() in ("off", "0", "false", "no"):
        return None
    provider = _pick_provider()
    try:
        if provider == "anthropic":
            import anthropic
            _client = anthropic.Anthropic()
        elif provider == "groq":
            import groq
            _client = groq.Groq()
    except ImportError:
        log.warning("%s API key is set but its package is not installed "
                    "(pip install %s); using rule-based agents", provider, provider)
        return None
    _provider = provider if _client is not None else None
    return _client


def enabled() -> bool:
    return get_client() is not None


def provider_name() -> Optional[str]:
    get_client()
    return _provider


def model_name() -> Optional[str]:
    provider = provider_name()
    if provider is None:
        return None
    return os.environ.get("GAZELENS_LLM_MODEL", DEFAULT_MODELS[provider])


def _effort() -> str:
    effort = os.environ.get("GAZELENS_LLM_EFFORT", DEFAULT_EFFORT).lower()
    return effort if effort in ("low", "medium", "high") else DEFAULT_EFFORT


def _anthropic_text(client: Any, system: str, user: str, schema: dict) -> Optional[str]:
    response = client.beta.messages.create(
        model=model_name(),
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": _effort(), "format": {"type": "json_schema", "schema": schema}},
        # On a safety decline, the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
        log.warning("LLM stopped with %s; using rule-based output", response.stop_reason)
        return None
    return next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)


def _groq_text(client: Any, system: str, user: str, schema: dict) -> Optional[str]:
    model = model_name()
    extra = {}
    if model.startswith("openai/gpt-oss"):
        # reasoning models: keep the reasoning out of the reply, JSON only
        extra = {"reasoning_effort": _effort(), "include_reasoning": False}
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=MAX_TOKENS,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "agent_output", "strict": True, "schema": schema}},
        **extra,
    )
    choice = response.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        log.warning("LLM reply was cut off; using rule-based output")
        return None
    return choice.message.content


def complete_json(system: str, user: str, schema: dict) -> Optional[dict]:
    """One structured-output call. Returns the parsed JSON, or None on any failure."""
    client = get_client()
    if client is None:
        return None
    call = _groq_text if _provider == "groq" else _anthropic_text
    try:
        text = call(client, system, user, schema)
    except Exception as exc:  # network, auth, rate limit, bad request: all mean "use rules"
        log.warning("LLM call failed (%s); using rule-based output", exc)
        return None
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON; using rule-based output")
        return None
    return data if isinstance(data, dict) else None


def dict_items(data: Any, key: str) -> list:
    """data[key] if it is a list, keeping only the dict entries. Strict schema
    output should never need this; it's the guard for when it isn't strict."""
    value = data.get(key) if isinstance(data, dict) else None
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


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
