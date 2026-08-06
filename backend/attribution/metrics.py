"""
metrics.py

AttributionTrace + UIConfig -> the agents' own SessionMetrics.

Every decision here is pinned to how backend/agents actually consumes the
field, because several of them are load-bearing in non-obvious ways.

dwell_time
    Sum of per-sample time attributed to the element. EVERY configured
    element appears, including ones that got 0.0 -- agent1's poor_visibility
    rule iterates dwell_time, so an omitted element is silently exempt from
    the rule most likely to flag it.

ttff
    Onset of the first FIXATION on the element, relative to session start.
    Not the first stray sample: "time to first fixation" means what it says,
    and a single noisy point clipping a corner is not discovery.

    Elements never fixated are OMITTED from this dict. That is the one place
    this module deliberately leaves a gap, and it is forced:
    agent1._first_noticed computes min(ttff, key=ttff.get), so a sentinel of
    0.0 would report an element nobody looked at as the first thing noticed.
    A sentinel of inf instead fires a bogus "delayed_discovery" reading
    "Time to first fixation was infs", and breaks the json.dumps in
    orchestrator's __main__ (Infinity is not valid JSON). Omission is the
    only option that leaves every agent rule correct -- and nothing is lost,
    because such an element still appears in dwell_time at 0.0, which is what
    drives the ignored/poor-visibility findings.

fixation_count
    Fixations whose CENTROID lands in the element.

revisit_count
    Visits after the first: max(0, visits - 1). A visit is one contiguous
    period on the element; it may contain several fixations. This keeps
    revisit_count independent of fixation_count rather than a restatement of
    it. (Mock data's numbers are not derivable from its own scanpaths -- they
    were hand-authored -- so they could not settle this; see CONTRACT.md.)

    A visit only counts if it contains at least one fixation. Elements sitting
    between two others collect gaze every time the eye travels past them --
    on the form page, name_field lies directly between promo_banner and
    email_field -- and counting those transits produced more revisits than
    fixations, which is incoherent. Passing over is not returning to.

total_gaze_time
    Total VALID gaze time in the session, including time on background.
    Not the sum of dwell_time. Read off the mock data: in 3 of 4 mock
    sessions the dwell times sum to less than total_gaze_time (clean_session:
    14.2 vs 20.0), so whitespace time belongs in the denominator that
    SessionMetrics.dwell_pct divides by. Blinks and dropouts are excluded --
    time the tracker was blind is not time the user spent looking.

scanpath
    One entry per fixation, in order, elements only. Consecutive repeats are
    kept: mock data has them ("product_image", "product_image"), and
    agent1._attention_scattered explicitly skips them, so they are expected
    and harmless. Background fixations are dropped -- a scanpath is a
    sequence of things looked AT.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .agents_schema import SessionMetrics
from .elements import UIConfig
from .fixations import AttributionTrace


@dataclass
class AttributionReport:
    """SessionMetrics plus the diagnostics that don't fit in it.

    SessionMetrics is a fixed contract owned by backend/agents and must not
    grow new fields, but several things are worth knowing when reading a
    report -- how much of the session was spent on nothing, how much data was
    lost to blinks, whether the boxes overlap. They live here instead.
    """

    metrics: SessionMetrics
    background_time: float = 0.0
    background_pct: float = 0.0
    tracked_pct: float = 0.0            # share of samples that were valid
    dropped_invalid: int = 0
    bridged_samples: int = 0
    total_fixations: int = 0
    background_fixations: int = 0
    unfixated_elements: List[str] = field(default_factory=list)
    overlapping_elements: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return {
            "metrics": asdict(self.metrics),
            "diagnostics": {
                "background_time": self.background_time,
                "background_pct": self.background_pct,
                "tracked_pct": self.tracked_pct,
                "dropped_invalid": self.dropped_invalid,
                "bridged_samples": self.bridged_samples,
                "total_fixations": self.total_fixations,
                "background_fixations": self.background_fixations,
                "unfixated_elements": self.unfixated_elements,
                "overlapping_elements": self.overlapping_elements,
                "warnings": self.warnings,
            },
        }


def build_metrics(
    trace: AttributionTrace,
    ui_config: UIConfig,
    session_id: str,
) -> AttributionReport:
    """Turn an attribution trace into the object backend/agents consumes."""
    element_ids = ui_config.element_ids

    # Every configured element is present in every per-element dict except
    # ttff -- see module docstring.
    dwell_time: Dict[str, float] = {eid: 0.0 for eid in element_ids}
    fixation_count: Dict[str, int] = {eid: 0 for eid in element_ids}
    visit_count: Dict[str, int] = {eid: 0 for eid in element_ids}
    ttff: Dict[str, float] = {}

    session_start = trace.samples[0].timestamp if trace.samples else 0.0

    # strict: labels/durations/samples are three views of the same gaze
    # stream. If they ever fell out of step, zip would silently stop at the
    # shortest and every dwell time would be quietly short -- a wrong number
    # that still looks entirely plausible in a report.
    for label, duration, sample in zip(
        trace.labels, trace.durations, trace.samples, strict=True
    ):
        if label is None or not sample.valid:
            continue
        if label in dwell_time:
            dwell_time[label] += duration

    scanpath: List[str] = []
    background_fixations = 0
    for fix in trace.fixations:
        if fix.element_id is None:
            background_fixations += 1
            continue
        if fix.element_id not in fixation_count:
            continue
        fixation_count[fix.element_id] += 1
        scanpath.append(fix.element_id)
        if fix.element_id not in ttff:
            ttff[fix.element_id] = fix.start - session_start

    # Only visits containing a fixation count. A visit with none is gaze
    # transiting across the element on its way somewhere else -- see Visit.
    for visit in trace.visits:
        if visit.element_id in visit_count and not visit.is_transit:
            visit_count[visit.element_id] += 1

    revisit_count = {eid: max(0, n - 1) for eid, n in visit_count.items()}

    metrics = SessionMetrics(
        session_id=session_id,
        ui_page=ui_config.ui_page,
        dwell_time={k: round(v, 4) for k, v in dwell_time.items()},
        ttff={k: round(v, 4) for k, v in ttff.items()},
        fixation_count=fixation_count,
        revisit_count=revisit_count,
        total_gaze_time=round(trace.valid_time, 4),
        scanpath=scanpath,
        element_importance=ui_config.importance_map(),
        element_type=ui_config.type_map(),
    )

    # ---- diagnostics + warnings ----
    total = trace.valid_time
    unfixated = [eid for eid in element_ids if eid not in ttff]
    warnings: List[str] = []

    tracked_pct = (
        100.0 * (len(trace.samples) - trace.dropped_invalid) / len(trace.samples)
        if trace.samples else 0.0
    )

    if total <= 0:
        warnings.append(
            "no valid gaze time in this session -- every metric is zero and "
            "the agent chain will have nothing to reason about"
        )
    if tracked_pct < 70.0 and trace.samples:
        warnings.append(
            f"only {tracked_pct:.0f}% of gaze samples were valid; dwell times "
            f"understate real attention and TTFF may be late"
        )
    background_pct = (100.0 * trace.background_time / total) if total > 0 else 0.0
    if background_pct > 50.0:
        warnings.append(
            f"{background_pct:.0f}% of gaze fell outside every configured element "
            f"-- the bounding boxes may not match the page that was shown"
        )
    if unfixated:
        warnings.append(
            f"{len(unfixated)} element(s) never fixated: {sorted(unfixated)} "
            f"(present in dwell_time at 0.0, omitted from ttff by design)"
        )

    return AttributionReport(
        metrics=metrics,
        background_time=round(trace.background_time, 4),
        background_pct=round(background_pct, 2),
        tracked_pct=round(tracked_pct, 2),
        dropped_invalid=trace.dropped_invalid,
        bridged_samples=trace.bridged_samples,
        total_fixations=len(trace.fixations),
        background_fixations=background_fixations,
        unfixated_elements=sorted(unfixated),
        overlapping_elements=[],
        warnings=warnings,
    )


__all__ = ["AttributionReport", "build_metrics"]
