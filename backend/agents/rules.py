"""
rules.py

All the numeric thresholds Agent 1 and Agent 2 use, in one place, so
tuning them later doesn't mean hunting through agent logic. These are the
four rules named directly in the project brief -- treat them as the
starting point, not gospel; you'll likely retune after the pilot study.
"""

CTA_TTFF_DELAYED_THRESHOLD_SECONDS = 5.0        # "If CTA TTFF > 5s -> delayed discovery"
CTA_DWELL_POOR_VISIBILITY_PCT = 5.0             # "If CTA dwell time < 5% of total -> poor visibility"
NON_INTERACTIVE_HIGH_FIXATION_COUNT = 5          # fixations before a non-clickable element counts as "high"
SCANPATH_REPEAT_JUMP_THRESHOLD = 3               # same element revisited via jumps this many times -> confusion flag

SEVERITY_BY_ELEMENT_IMPORTANCE = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
