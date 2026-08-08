"""
rules.py

All the numeric thresholds Agent 1 and Agent 2 use, in one place, so
tuning them later doesn't mean hunting through agent logic. The first four
are named directly in the project brief -- treat them as the starting
point, not gospel; you'll likely retune after the pilot study. The other
three (error prevention, cognitive load, accessibility) were added to cover
the rest of the brief's Nielsen heuristic list -- the brief names all seven
categories but only worked four rule examples; without these three, Agent 2
could never actually produce them, since it only maps findings Agent 1
already emitted.
"""

CTA_TTFF_DELAYED_THRESHOLD_SECONDS = 5.0        # "If CTA TTFF > 5s -> delayed discovery"
CTA_DWELL_POOR_VISIBILITY_PCT = 5.0             # "If CTA dwell time < 5% of total -> poor visibility"
NON_INTERACTIVE_HIGH_FIXATION_COUNT = 5          # fixations before a non-clickable element counts as "high"
SCANPATH_REPEAT_JUMP_THRESHOLD = 3               # same element revisited via jumps this many times -> confusion flag

# Error prevention: an interactive element (CTA/form_field) the participant
# kept returning to, rather than committing to once. High revisits on
# something actionable reads as "I'm not sure this did what I expected" --
# the system isn't preventing the uncertainty/error that's driving the
# repeat visits.
REVISIT_ERROR_PREVENTION_COUNT = 4

# Cognitive load: attention spread thin across many elements with no clear
# focus anywhere, rather than concentrated on a few. Both conditions
# together, not either alone -- visiting many elements is normal for a
# busy dashboard; visiting many AND never settling on any of them is the
# "I can't figure out where to look" signal.
COGNITIVE_LOAD_MIN_DISTINCT_ELEMENTS = 6
COGNITIVE_LOAD_MAX_TOP_ELEMENT_DWELL_PCT = 15.0

# Accessibility: a high-importance element that received exactly zero
# fixations for the whole session -- distinct from "delayed_discovery"
# (found late, TTFF > threshold), which requires the element to have been
# found at all. Zero fixations despite genuine session coverage is a
# stronger claim: not "found late" but "never found."
ACCESSIBILITY_MIN_SESSION_GAZE_TIME_SECONDS = 5.0

SEVERITY_BY_ELEMENT_IMPORTANCE = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
