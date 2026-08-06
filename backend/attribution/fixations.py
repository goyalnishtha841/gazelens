"""
fixations.py

Raw gaze points -> fixations, visits, and per-sample attribution.

THREE DIFFERENT THINGS, DELIBERATELY
------------------------------------
* per-sample attribution -> feeds DWELL TIME. "How long was gaze inside this
  box", including time spent sweeping across it.
* fixation (I-DT)        -> feeds FIXATION COUNT and TTFF. A cluster of
  spatially stable gaze. Gaze passing over an element is not a fixation on it.
* visit                  -> feeds REVISIT COUNT. A contiguous period during
  which gaze was on the element, however many fixations that contained.

Keeping them separate is what makes fixation_count and revisit_count
independent measurements rather than the same number twice.

THRESHOLDS, AND WHY
-------------------
MIN_FIXATION_DURATION = 100ms. The conventional lower bound; below it the
"fixation" is really part of a saccade.

DISPERSION_THRESHOLD = 0.06 normalised (~115px across x+y on a 1920x1080
screen), applied to SMOOTHED gaze. This is the load-bearing constant, and
getting it wrong is not subtle -- an earlier draft set it to 0.03 by
comparing it against gaze_estimation's ~40px per-frame error, which is the
wrong quantity entirely and made fixation detection fail outright on
realistic input (one fixation for a whole session).

I-DT dispersion is (max_x - min_x) + (max_y - min_y) over every sample in the
fixation, so it scales with the RANGE of the noise, not its standard
deviation. The expected range of n samples is roughly 4-5 sigma per axis, and
the two axes are summed, so a fixation of ~9 samples sits near 8 sigma. At the
measured sigma of 40px that is ~340px -- far larger than most UI elements, so
no usable threshold exists on the raw stream.

Hence SMOOTHING_WINDOW: a 5-sample moving average cuts sigma by sqrt(5) to
~18px, which brings 8 sigma to ~145px and makes a threshold of ~115px
workable. Smoothing here rather than upstream is deliberate --
backend/gaze_estimation leaves its stream deliberately raw and documents that
smoothing is attribution's decision to make, because it shortens saccades and
stretches fixations, which is precisely what this module measures.

Even so, a 115px threshold could in principle merge fixations on two adjacent
elements. It cannot, because fixation growth also stops at an element
boundary (see detect_fixations) -- a fixation on element A and one on element
B are by definition different fixations. That constraint is what makes the
exact threshold non-critical rather than a knife edge.

MAX_GAP = 150ms. Gaze briefly leaving an element -- a noise excursion, a
blink, a flick to the edge and back -- does not end a visit. Longer than
that and it is treated as a genuine departure.

BACKGROUND = None. Gaze on whitespace is attributed to no element. It still
counts toward total_gaze_time (see metrics.py) but never to an element.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .geometry import BBox, dispersion, hit_test, nearest_element

MIN_FIXATION_DURATION = 0.100        # seconds
DISPERSION_THRESHOLD = 0.06          # normalised page units
MAX_GAP = 0.150                      # seconds; bridging tolerance

# Moving-average window applied BEFORE fixation detection, in samples
# (5 @ 30Hz = 167ms). Not cosmetic -- see the threshold note above; without
# it, dispersion detection does not function at the measured gaze error.
SMOOTHING_WINDOW = 5

# A sample can only be credited with so much time. Without this, a stream that
# drops out for two seconds and resumes inside a button would credit that
# button with two seconds of dwell nobody actually spent looking at it.
MAX_SAMPLE_DURATION = 0.200          # seconds

# How far outside its box a point may sit and still be pulled back in, as a
# fraction of the page. Only ever applied to a point already bracketed by the
# same element -- never to attribute a stray point to something new.
EDGE_TOLERANCE = 0.01

BACKGROUND = None


@dataclass(frozen=True)
class GazeSample:
    """One raw gaze point.

    Matches the GazePoint shape backend/gaze_estimation emits (timestamp, x,
    y normalised, valid), but is defined independently -- this module must not
    import from the gaze-producing modules. See CONTRACT.md.
    """

    timestamp: float
    x: float
    y: float
    valid: bool = True
    confidence: float = 1.0


@dataclass
class Fixation:
    """A spatially stable cluster of gaze."""

    start: float
    end: float
    x: float                      # centroid
    y: float
    sample_count: int
    element_id: Optional[str] = None      # None = background

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Visit:
    """A contiguous period gaze spent on one element.

    `fixation_count` is what separates a real visit from a TRANSIT. Gaze
    travelling from an element at the top of the page to one at the bottom
    sweeps through everything in between, and those elements would otherwise
    each register a visit the user never made. A visit that contains no
    fixation is gaze passing over, not gaze stopping -- metrics.py counts only
    the ones that qualify. (The transit time still counts toward dwell_time,
    which is defined as time inside the box.)
    """

    element_id: str
    start: float
    end: float
    duration: float = 0.0         # summed sample time, not end-start
    fixation_count: int = 0

    @property
    def is_transit(self) -> bool:
        return self.fixation_count == 0


@dataclass
class AttributionTrace:
    """Everything downstream metrics need, plus the diagnostics to audit it."""

    samples: List[GazeSample]
    labels: List[Optional[str]]           # per-sample, post-smoothing
    durations: List[float]                # per-sample, seconds
    fixations: List[Fixation] = field(default_factory=list)
    visits: List[Visit] = field(default_factory=list)

    dropped_invalid: int = 0
    bridged_samples: int = 0
    background_time: float = 0.0
    valid_time: float = 0.0


# ----------------------------------------------------------------------


def _sample_durations(samples: Sequence[GazeSample]) -> List[float]:
    """How much time each sample represents.

    A sample stands for the interval until the next one. The final sample has
    no successor, so it gets the median of the others -- assuming the sampling
    rate held rather than inventing a long tail.
    """
    n = len(samples)
    if n == 0:
        return []
    if n == 1:
        return [MIN_FIXATION_DURATION]

    deltas = [
        max(0.0, samples[i + 1].timestamp - samples[i].timestamp)
        for i in range(n - 1)
    ]
    ordered = sorted(d for d in deltas if d > 0)
    median = ordered[len(ordered) // 2] if ordered else MIN_FIXATION_DURATION

    out = [min(d, MAX_SAMPLE_DURATION) for d in deltas]
    out.append(min(median, MAX_SAMPLE_DURATION))
    return out


def smooth_positions(
    samples: Sequence[GazeSample],
    window: int = SMOOTHING_WINDOW,
    max_gap: float = MAX_GAP,
) -> List[Tuple[float, float]]:
    """Centred moving average over valid samples.

    Invalid samples keep their own coordinates (they are excluded from every
    metric anyway) but do not contribute to their neighbours' averages -- a
    blink's coordinates are meaningless and would drag the average.

    The average never spans a gap longer than `max_gap`, so gaze either side
    of a dropout is not blended into a position the eye never occupied.
    """
    n = len(samples)
    if window <= 1 or n == 0:
        return [(s.x, s.y) for s in samples]

    half = window // 2
    out: List[Tuple[float, float]] = []

    for i, sample in enumerate(samples):
        if not sample.valid:
            out.append((sample.x, sample.y))
            continue

        xs, ys = [], []
        for j in range(max(0, i - half), min(n, i + half + 1)):
            neighbour = samples[j]
            if not neighbour.valid:
                continue
            if abs(neighbour.timestamp - sample.timestamp) > max_gap:
                continue
            xs.append(neighbour.x)
            ys.append(neighbour.y)

        if xs:
            out.append((sum(xs) / len(xs), sum(ys) / len(ys)))
        else:
            out.append((sample.x, sample.y))

    return out


def _raw_labels(
    samples: Sequence[GazeSample],
    positions: Sequence[Tuple[float, float]],
    boxes: Dict[str, BBox],
    priority: Optional[Sequence[str]],
) -> List[Optional[str]]:
    return [
        hit_test(boxes, px, py, priority) if s.valid else BACKGROUND
        # strict: these arrays are per-sample and must stay aligned. Silent
        # truncation would drop the tail of a session's gaze and look like a
        # short session rather than a bug.
        for s, (px, py) in zip(samples, positions, strict=True)
    ]


def _smooth_labels(
    samples: Sequence[GazeSample],
    positions: Sequence[Tuple[float, float]],
    labels: List[Optional[str]],
    boxes: Dict[str, BBox],
    max_gap: float,
) -> Tuple[List[Optional[str]], int]:
    """Bridge brief excursions out of an element.

    A run of samples labelled something else, shorter than `max_gap` and
    bracketed by the SAME element on both sides, is relabelled to that
    element. This is the noise tolerance: at ~40px of gaze error, a point
    that momentarily lands 20px outside a button the user is plainly staring
    at should not split one fixation into two.

    Two guards keep this from inventing attention:
      * only bridges when the same element sits on BOTH sides, so it can never
        create a visit that didn't happen;
      * a bridged run of BACKGROUND must also be spatially close to the box
        (EDGE_TOLERANCE), so a genuine glance away and back to the same
        element stays two visits rather than being silently merged into one.
    """
    n = len(labels)
    smoothed = list(labels)
    bridged = 0
    start = 0
    while start < n:
        end = start
        while end + 1 < n and smoothed[end + 1] == smoothed[start]:
            end += 1

        prev_label = smoothed[start - 1] if start > 0 else None
        next_label = smoothed[end + 1] if end + 1 < n else None
        run_label = smoothed[start]

        if (
            prev_label is not None
            and prev_label == next_label
            and run_label != prev_label
        ):
            span = samples[min(end + 1, n - 1)].timestamp - samples[start].timestamp
            if span <= max_gap:
                box = boxes.get(prev_label)
                close_enough = True
                if run_label is BACKGROUND and box is not None:
                    tolerant = box.expanded(EDGE_TOLERANCE)
                    close_enough = all(
                        (not samples[k].valid)
                        or tolerant.contains(positions[k][0], positions[k][1])
                        for k in range(start, end + 1)
                    )
                if close_enough:
                    for k in range(start, end + 1):
                        smoothed[k] = prev_label
                        bridged += 1

        start = end + 1

    return smoothed, bridged


def detect_fixations(
    samples: Sequence[GazeSample],
    positions: Optional[Sequence[Tuple[float, float]]] = None,
    labels: Optional[Sequence[Optional[str]]] = None,
    min_duration: float = MIN_FIXATION_DURATION,
    threshold: float = DISPERSION_THRESHOLD,
    max_gap: float = MAX_GAP,
) -> List[Fixation]:
    """I-DT dispersion-based fixation detection (Salvucci & Goldberg).

    Operates only on valid samples, but measures duration from timestamps, so
    a blink inside an otherwise stable gaze is spanned rather than splitting
    the fixation -- provided the blink is shorter than `max_gap`.

    `positions` should be the SMOOTHED coordinates (see smooth_positions);
    raw ones are used if omitted, which is only appropriate for near-noiseless
    input. `labels` constrains a fixation to a single element: gaze crossing
    from one element to another ends the fixation regardless of dispersion,
    which is what keeps the threshold from having to be knife-edge accurate.
    """
    if positions is None:
        positions = [(s.x, s.y) for s in samples]

    points = [
        (positions[i][0], positions[i][1], s.timestamp,
         labels[i] if labels is not None else None)
        for i, s in enumerate(samples) if s.valid
    ]
    fixations: List[Fixation] = []
    n = len(points)
    start = 0

    def _can_extend(idx: int, anchor_label) -> bool:
        if points[idx][2] - points[idx - 1][2] > max_gap:
            return False
        return labels is None or points[idx][3] == anchor_label

    while start < n:
        anchor_label = points[start][3]
        end = start

        # grow to the minimum duration
        while (end + 1 < n
               and points[end][2] - points[start][2] < min_duration
               and _can_extend(end + 1, anchor_label)):
            end += 1

        window = [(px, py) for px, py, _, _ in points[start:end + 1]]
        span = points[end][2] - points[start][2]

        if span < min_duration or dispersion(window) > threshold:
            start += 1
            continue

        # stable: extend while it stays stable, uninterrupted, and on the
        # same element
        while end + 1 < n and _can_extend(end + 1, anchor_label):
            candidate = window + [(points[end + 1][0], points[end + 1][1])]
            if dispersion(candidate) > threshold:
                break
            window = candidate
            end += 1

        xs = [p for p, _ in window]
        ys = [q for _, q in window]
        fixations.append(Fixation(
            start=points[start][2],
            end=points[end][2],
            x=sum(xs) / len(xs),
            y=sum(ys) / len(ys),
            sample_count=len(window),
        ))
        start = end + 1

    return fixations


def _build_visits(
    samples: Sequence[GazeSample],
    labels: Sequence[Optional[str]],
    durations: Sequence[float],
) -> List[Visit]:
    """Contiguous runs of the same element, after smoothing."""
    visits: List[Visit] = []
    current: Optional[Visit] = None

    for i, label in enumerate(labels):
        if label is BACKGROUND:
            current = None
            continue
        if current is not None and current.element_id == label:
            current.end = samples[i].timestamp
            current.duration += durations[i]
        else:
            current = Visit(
                element_id=label,
                start=samples[i].timestamp,
                end=samples[i].timestamp,
                duration=durations[i],
            )
            visits.append(current)

    return visits


def attribute(
    samples: Sequence[GazeSample],
    boxes: Dict[str, BBox],
    priority: Optional[Sequence[str]] = None,
    min_fixation_duration: float = MIN_FIXATION_DURATION,
    dispersion_threshold: float = DISPERSION_THRESHOLD,
    max_gap: float = MAX_GAP,
    smoothing_window: int = SMOOTHING_WINDOW,
) -> AttributionTrace:
    """The whole pipeline: smooth, label, bridge, detect fixations, segment."""
    samples = sorted(samples, key=lambda s: s.timestamp)
    durations = _sample_durations(samples)

    # Smoothing feeds BOTH labelling and fixation detection, so dwell time and
    # fixation counts describe the same reconstructed gaze path rather than
    # two different ones.
    positions = smooth_positions(samples, smoothing_window, max_gap)

    labels = _raw_labels(samples, positions, boxes, priority)
    labels, bridged = _smooth_labels(samples, positions, labels, boxes, max_gap)

    fixations = detect_fixations(
        samples,
        positions=positions,
        labels=labels,
        min_duration=min_fixation_duration,
        threshold=dispersion_threshold,
        max_gap=max_gap,
    )
    # A fixation belongs to the element under its CENTROID, not under whichever
    # sample happened to be first. The centroid averages away the per-sample
    # error, so it lands in the right box far more reliably than any one point.
    for fix in fixations:
        fix.element_id = hit_test(boxes, fix.x, fix.y, priority)
        if fix.element_id is BACKGROUND:
            # Just outside a box is almost always estimation error rather than
            # a deliberate fixation on the margin beside a button.
            fix.element_id = nearest_element(boxes, fix.x, fix.y, EDGE_TOLERANCE)

    visits = _build_visits(samples, labels, durations)

    # Tag each visit with the fixations that fall inside it, so transits can
    # be told apart from genuine visits.
    for fix in fixations:
        if fix.element_id is None:
            continue
        for visit in visits:
            if (visit.element_id == fix.element_id
                    and visit.start <= fix.start <= visit.end):
                visit.fixation_count += 1
                break

    valid_time = sum(d for d, s in zip(durations, samples, strict=True) if s.valid)
    background_time = sum(
        d for d, s, lab in zip(durations, samples, labels, strict=True)
        if s.valid and lab is BACKGROUND
    )

    return AttributionTrace(
        samples=list(samples),
        labels=labels,
        durations=durations,
        fixations=fixations,
        visits=visits,
        dropped_invalid=sum(1 for s in samples if not s.valid),
        bridged_samples=bridged,
        background_time=background_time,
        valid_time=valid_time,
    )


__all__ = [
    "GazeSample",
    "Fixation",
    "Visit",
    "AttributionTrace",
    "attribute",
    "detect_fixations",
    "BACKGROUND",
    "MIN_FIXATION_DURATION",
    "DISPERSION_THRESHOLD",
    "MAX_GAP",
    "MAX_SAMPLE_DURATION",
    "EDGE_TOLERANCE",
]
