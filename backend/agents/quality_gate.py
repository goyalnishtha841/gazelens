"""
quality_gate.py
Data-quality gate. Runs BEFORE Agent 1, and decides how much the rest of
the chain is allowed to claim.

The other agents take SessionMetrics at face value. That is what produced
"3 high-severity issues" from 24 seconds of gaze measured at 437px error:
every rule fired correctly on numbers that were noise. This gate looks at
how trustworthy the numbers are, not at what they say:

  * gaze error      -- the accuracy-check median from calibration (falls
                       back to the held-out calibration error), as a share
                       of the screen diagonal
  * tracked_pct     -- share of gaze samples that were valid
  * total_gaze_time -- seconds of usable gaze
  * fixations       -- how many fixations attribution found

Three levels:
  "insufficient" -- the chain does not run; the report says why
  "limited"      -- the chain runs, but no finding may be rated High
  "good"         -- unrestricted

Deliberately 100% rule-based, like Agent 1: the gate has to be explainable
in one sentence per reason, and its thresholds are numbers a reviewer can
argue with.
"""

from dataclasses import dataclass, field
from typing import List, Optional

# Gaze error as a fraction of the screen diagonal. Same cut-offs as the
# calibration accuracy check (backend/gaze_estimation/validation.py), so
# "fair" there means "limited" here and "poor" means "insufficient".
ERROR_LIMITED_FRACTION = 0.08
ERROR_INSUFFICIENT_FRACTION = 0.15

TRACKED_LIMITED_PCT = 70.0
TRACKED_INSUFFICIENT_PCT = 50.0

GAZE_TIME_LIMITED_S = 15.0
GAZE_TIME_INSUFFICIENT_S = 5.0

MIN_FIXATIONS = 5

LEVELS = ("good", "limited", "insufficient")


@dataclass
class QualityInput:
    gaze_error_px: Optional[float] = None
    error_source: Optional[str] = None      # "accuracy_check" | "calibration_cv"
    screen_diagonal_px: Optional[float] = None
    tracked_pct: float = 100.0
    total_gaze_time: float = 0.0
    total_fixations: int = 0
    low_confidence_elements: List[str] = field(default_factory=list)


@dataclass
class QualityVerdict:
    level: str                               # one of LEVELS
    max_severity: Optional[str]              # "High" | "Medium" | None (= no issues at all)
    reasons: List[str] = field(default_factory=list)
    gaze_error_px: Optional[float] = None
    gaze_error_pct_diagonal: Optional[float] = None
    error_source: Optional[str] = None
    low_confidence_elements: List[str] = field(default_factory=list)


def assess(q: QualityInput) -> QualityVerdict:
    insufficient: List[str] = []
    limited: List[str] = []

    pct = None
    if q.gaze_error_px is not None and q.screen_diagonal_px:
        frac = q.gaze_error_px / q.screen_diagonal_px
        pct = 100.0 * frac
        source = "accuracy check" if q.error_source == "accuracy_check" else "calibration"
        msg = f"gaze error {q.gaze_error_px:.0f}px ({pct:.1f}% of the screen, from the {source})"
        if frac > ERROR_INSUFFICIENT_FRACTION:
            insufficient.append(f"{msg} is too large to attribute gaze to page elements")
        elif frac > ERROR_LIMITED_FRACTION:
            limited.append(f"{msg} only supports conclusions about larger page regions")
    else:
        limited.append("gaze accuracy was never measured for this calibration")

    if q.tracked_pct < TRACKED_INSUFFICIENT_PCT:
        insufficient.append(f"only {q.tracked_pct:.0f}% of the session was tracked")
    elif q.tracked_pct < TRACKED_LIMITED_PCT:
        limited.append(f"{q.tracked_pct:.0f}% of the session was tracked")

    if q.total_gaze_time < GAZE_TIME_INSUFFICIENT_S:
        insufficient.append(f"only {q.total_gaze_time:.1f}s of usable gaze")
    elif q.total_gaze_time < GAZE_TIME_LIMITED_S:
        limited.append(f"a short session ({q.total_gaze_time:.0f}s of usable gaze)")

    if q.total_fixations < MIN_FIXATIONS:
        insufficient.append(f"only {q.total_fixations} fixation(s) detected")

    if insufficient:
        level, max_sev, reasons = "insufficient", None, insufficient + limited
    elif limited:
        level, max_sev, reasons = "limited", "Medium", limited
    else:
        level, max_sev, reasons = "good", "High", []

    return QualityVerdict(
        level=level,
        max_severity=max_sev,
        reasons=reasons,
        gaze_error_px=q.gaze_error_px,
        gaze_error_pct_diagonal=round(pct, 2) if pct is not None else None,
        error_source=q.error_source,
        low_confidence_elements=list(q.low_confidence_elements),
    )
