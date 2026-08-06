"""
points.py

The calibration target grid.

Coordinates are normalised to [0, 1] of the viewport, NOT pixels. The
participant's screen size is recorded once per session, so the same
calibration data stays meaningful if the study later runs on a different
monitor -- and so gaze_estimation trains on a resolution-independent target.

The grid is inset from the edges: a target at exactly (0, 0) sits in the
screen corner where the browser chrome is, and asking someone to fixate
there produces an extreme eye rotation that the pupil detector handles
badly. MARGIN pulls the outer ring inwards so every point is comfortably
reachable.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Supported patterns -> (columns, rows). 9 is the quick calibration,
# 16 the thorough one; both are what Calibration.jsx is expected to offer.
PATTERNS: Dict[int, Tuple[int, int]] = {
    9: (3, 3),
    16: (4, 4),
}

DEFAULT_PATTERN = 16

# Fraction of the viewport kept clear at each edge.
MARGIN = 0.08


@dataclass(frozen=True)
class CalibrationPoint:
    """One on-screen target the participant is asked to look at."""

    index: int
    x: float          # normalised [0, 1], left -> right
    y: float          # normalised [0, 1], top -> bottom

    def to_dict(self) -> dict:
        return {"index": self.index, "x": self.x, "y": self.y}


def generate_points(pattern: int = DEFAULT_PATTERN) -> List[CalibrationPoint]:
    """The grid for a pattern, in presentation order.

    Order is row-major (left to right, top to bottom). Deliberately
    deterministic: a participant who can predict the next point calibrates
    faster, and a fixed order makes two sessions directly comparable.

    The client is not obliged to present them in this order -- every sample
    it posts carries its point_index, so the server pairs targets to pupils
    by index, never by arrival order.
    """
    if pattern not in PATTERNS:
        raise ValueError(
            f"unsupported calibration pattern {pattern!r}; "
            f"expected one of {sorted(PATTERNS)}"
        )

    cols, rows = PATTERNS[pattern]
    span = 1.0 - 2 * MARGIN
    points: List[CalibrationPoint] = []
    index = 0
    for r in range(rows):
        for c in range(cols):
            points.append(
                CalibrationPoint(
                    index=index,
                    x=round(MARGIN + span * c / (cols - 1), 4),
                    y=round(MARGIN + span * r / (rows - 1), 4),
                )
            )
            index += 1
    return points


def point_at(pattern: int, index: int) -> CalibrationPoint:
    """Look up one target. Raises IndexError for an out-of-range index."""
    points = generate_points(pattern)
    if not 0 <= index < len(points):
        raise IndexError(
            f"point_index {index} out of range for a {pattern}-point calibration "
            f"(valid: 0-{len(points) - 1})"
        )
    return points[index]


__all__ = [
    "PATTERNS",
    "DEFAULT_PATTERN",
    "MARGIN",
    "CalibrationPoint",
    "generate_points",
    "point_at",
]
