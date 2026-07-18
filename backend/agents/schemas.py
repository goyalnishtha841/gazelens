"""
schemas.py

This is the CONTRACT between the metrics pipeline (Students 1-3's work)
and the agent chain (this module). Nothing here depends on webcam,
detectors, or gaze estimation -- it only depends on this shape existing.

Keep this file as the single source of truth. If the real metrics module
ends up producing something with a different shape, change it HERE first,
then update mock_sessions.py to match -- never let the agents silently
assume a shape that isn't written down.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class SessionMetrics:
    """What Student 3's metrics/attribution module is expected to output
    for one completed session. This is the ONLY input the agent chain needs."""

    session_id: str
    ui_page: str  # e.g. "ecommerce_product_page"

    # per-element metrics, keyed by element_id (from the UI's bbox config)
    dwell_time: Dict[str, float]          # seconds spent looking at each element
    ttff: Dict[str, float]                # time-to-first-fixation, seconds
    fixation_count: Dict[str, int]        # number of distinct fixations
    revisit_count: Dict[str, int]         # number of times user returned to it

    total_gaze_time: float                # seconds, whole session
    scanpath: List[str]                   # ordered list of element_ids gazed at, in sequence

    # element metadata (importance/type) -- comes from the UI config, not gaze data
    element_importance: Dict[str, str]    # element_id -> "high" | "medium" | "low"
    element_type: Dict[str, str]          # element_id -> "CTA" | "text" | "image" | "nav" | "non-interactive"

    def dwell_pct(self, element_id: str) -> float:
        """Dwell time on an element as a percentage of total gaze time."""
        if self.total_gaze_time <= 0:
            return 0.0
        return (self.dwell_time.get(element_id, 0.0) / self.total_gaze_time) * 100


@dataclass
class BehaviorFinding:
    """One atomic observation from Agent 1, always tied to a metric."""
    finding_type: str      # e.g. "delayed_discovery", "poor_visibility", "misleading_affordance", "layout_confusion"
    element_id: str
    evidence: str           # human-readable, must reference the actual number
    metric_value: float


@dataclass
class BehaviorSummary:
    """Agent 1's full output."""
    session_id: str
    first_noticed: Optional[str]
    most_attended: Optional[str]
    ignored_important_elements: List[str]
    attention_scattered: bool
    findings: List[BehaviorFinding] = field(default_factory=list)


@dataclass
class UXIssue:
    """One issue from Agent 2, mapped to a Nielsen heuristic."""
    issue: str
    severity: str            # "High" | "Medium" | "Low"
    evidence: str
    heuristic: str
    element_id: str


@dataclass
class Recommendation:
    """One proposed fix from Agent 3."""
    recommendation: str
    linked_issue: str
    element_id: str


@dataclass
class VerifiedRecommendation:
    """Agent 4's output: a recommendation plus its support check."""
    recommendation: str
    element_id: str
    support: str              # "Strong" | "Weak" | "Unsupported"
    evidence: List[str]
    confidence: float         # 0.0 - 1.0
    kept: bool                 # False if Agent 4 rejected it
