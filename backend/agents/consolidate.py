"""
consolidate.py
Runs AFTER Agent 4. Turns the chain's raw output into what a report reader
should see:

  * one issue per element -- several rules often fire on one cause (a CTA
    nobody looked at trips both "poor visibility" and "high-importance
    element ignored"), which read as two problems when they are one
  * one recommendation card per element, the best-supported one leading
  * readable names ("Subscribe button") instead of ids ("subscribe_cta")
  * honesty about measurement limits: findings on an element smaller than
    the session's gaze error are downgraded one severity step and carry a
    caveat, and their recommendations' confidence is scaled by how
    measurable the element was -- the critic re-checks the metric, this
    accounts for whether the metric could be trusted in the first place
  * the quality gate's severity ceiling

Works on the dicts orchestrator.run_pipeline returns, so nothing upstream
changes shape. The unmerged lists are kept beside the result for audit.
"""

import re
from typing import Dict, List, Optional

SEVERITY_ORDER = ["Low", "Medium", "High"]
SESSION_ELEMENT = "__session__"

# Recommendation confidence is multiplied by the element's size/error
# ratio, but never below this: a small element can still have a real,
# corroborated problem; it just can't be stated with full confidence.
MIN_RELIABILITY_FACTOR = 0.3

# Mirrors agent4_critic: Strong at or above this.
STRONG_CONFIDENCE = 0.6

_WORD_FIXES = {"cta": "button", "nav": "navigation", "btn": "button", "img": "image"}


def readable_label(element_id: str, labels: Optional[Dict[str, str]] = None) -> str:
    """Authored label -> visible text -> a tidied-up id."""
    if element_id == SESSION_ELEMENT:
        return "Whole page"
    label = (labels or {}).get(element_id)
    if label:
        return label
    words = [w for w in re.split(r"[_\-\s]+", element_id) if w]
    words = [_WORD_FIXES.get(w.lower(), w.lower()) for w in words]
    text = " ".join(words) or element_id
    return text[0].upper() + text[1:]


def _rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else 0


def _cap(severity: str, ceiling: Optional[str]) -> str:
    if ceiling is None or _rank(severity) <= _rank(ceiling):
        return severity
    return ceiling


def _unique(items) -> List[str]:
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def merge_issues(
    issues: List[dict],
    labels: Optional[Dict[str, str]] = None,
    reliability: Optional[Dict[str, float]] = None,
    gaze_error_px: Optional[float] = None,
    max_severity: Optional[str] = "High",
) -> List[dict]:
    """Agent 2's issues -> one per element, most severe first."""
    reliability = reliability or {}
    groups: Dict[str, List[dict]] = {}
    for issue in issues:
        eid = issue["element_id"]
        # page-level issues are distinct problems, not one element's symptoms
        key = f"{eid}::{issue['issue']}" if eid == SESSION_ELEMENT else eid
        groups.setdefault(key, []).append(issue)

    merged = []
    for group in groups.values():
        group = sorted(group, key=lambda i: -_rank(i["severity"]))
        lead = group[0]
        eid = lead["element_id"]
        severity = lead["severity"]
        caveat = None
        ratio = reliability.get(eid)
        if ratio is not None and ratio < 1.0:
            severity = SEVERITY_ORDER[max(0, _rank(severity) - 1)]
            caveat = (f"This element is smaller than the measured gaze error"
                      f"{f' ({gaze_error_px:.0f}px)' if gaze_error_px else ''}, so this "
                      f"finding is indicative rather than measured.")
        merged.append({
            "issue": lead["issue"],
            "severity": _cap(severity, max_severity),
            "severity_raw": lead["severity"],
            "heuristic": "; ".join(_unique(i["heuristic"] for i in group)),
            "evidence": " · ".join(_unique(i["evidence"] for i in group)),
            "element_id": eid,
            "element_label": readable_label(eid, labels),
            "also": _unique(i["issue"] for i in group[1:] if i["issue"] != lead["issue"]),
            "merged_count": len(group),
            "caveat": caveat,
            # LLM mode: the critic-verified plain-English explanation, if any
            "explanation": next((i.get("explanation") for i in group if i.get("explanation")), None),
        })
    merged.sort(key=lambda i: (-_rank(i["severity"]), i["element_label"]))
    return merged


def merge_recommendations(
    recs: List[dict],
    labels: Optional[Dict[str, str]] = None,
    reliability: Optional[Dict[str, float]] = None,
) -> List[dict]:
    """Agent 4's kept recommendations -> one card per element."""
    reliability = reliability or {}
    groups: Dict[str, List[dict]] = {}
    for rec in recs:
        groups.setdefault(rec["element_id"], []).append(rec)

    merged = []
    for eid, group in groups.items():
        group = sorted(group, key=lambda r: -r["confidence"])
        lead = group[0]
        factor = 1.0
        ratio = reliability.get(eid)
        if ratio is not None:
            factor = max(MIN_RELIABILITY_FACTOR, min(1.0, ratio))
        confidence = round(lead["confidence"] * factor, 2)
        merged.append({
            "recommendation": lead["recommendation"],
            "element_id": eid,
            "element_label": readable_label(eid, labels),
            "also": _unique(r["recommendation"] for r in group[1:]
                            if r["recommendation"] != lead["recommendation"]),
            "evidence": _unique(e for r in group for e in r.get("evidence", [])),
            "confidence": confidence,
            "confidence_raw": lead["confidence"],
            "measurability": round(factor, 2),
            "support": "Strong" if confidence >= STRONG_CONFIDENCE else "Weak",
            "kept": True,
            "source": lead.get("source", "rules"),
        })
    merged.sort(key=lambda r: (-r["confidence"], r["element_label"]))
    return merged


__all__ = [
    "readable_label",
    "merge_issues",
    "merge_recommendations",
]
