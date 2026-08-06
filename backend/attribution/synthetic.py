"""
synthetic.py

Hand-written fake gaze streams and UI configs.

Same pattern backend/agents used with mock_sessions.py: build the module
against written-down inputs so it can be finished and tested before the thing
upstream of it exists. Nothing here imports backend/cv, backend/calibration
or backend/gaze_estimation -- this module's only inputs are gaze coordinates
and bounding boxes, and that independence is the point.

The layouts reuse the element IDs and geometry already in
backend/reports/heatmap_stub.py's DEMO_LAYOUTS, and the importance/type
labels from backend/agents/mock_sessions.py. So a session generated here is
directly comparable to the hand-authored mock the agents were built against,
and the resulting metrics can be sanity-checked by eye against those.

`scripted_session` drives gaze with an explicit list of
(element_or_point, seconds) instructions. Being able to say "look at the
product image for 6 seconds, then the checkout button for 0.4" is what makes
the tests assertions about known truth rather than assertions about whatever
the code happened to produce.
"""

import random
from typing import List, Sequence, Tuple, Union

from .elements import UIConfig, build_ui_config
from .fixations import GazeSample

SAMPLE_RATE_HZ = 30.0
DEFAULT_DT = 1.0 / SAMPLE_RATE_HZ

# Gaze error to simulate, in normalised page units. 0.008 of a 1920px screen
# is ~15px, which is optimistic but non-zero; backend/gaze_estimation measures
# ~40px per frame, available below as REALISTIC_NOISE.
CLEAN_NOISE = 0.008
REALISTIC_NOISE = 0.021          # ~40px on 1920 -- the measured figure
BAD_NOISE = 0.05


# ----------------------------------------------------------------------
# layouts -- geometry from reports/heatmap_stub.py, labels from
# agents/mock_sessions.py


ECOMMERCE = {
    "nav_bar": {"bbox": (0.05, 0.03, 0.90, 0.08), "importance": "low", "type": "nav"},
    "product_image": {"bbox": (0.05, 0.16, 0.40, 0.55), "importance": "medium", "type": "image"},
    "product_title": {"bbox": (0.50, 0.16, 0.45, 0.14), "importance": "medium", "type": "text"},
    "checkout_button": {"bbox": (0.50, 0.38, 0.28, 0.10), "importance": "high", "type": "CTA"},
}

FORM_PAGE = {
    "promo_banner": {"bbox": (0.10, 0.04, 0.80, 0.09), "importance": "low", "type": "non-interactive"},
    "name_field": {"bbox": (0.20, 0.20, 0.60, 0.09), "importance": "medium", "type": "text"},
    "email_field": {"bbox": (0.20, 0.34, 0.60, 0.09), "importance": "medium", "type": "text"},
    "helper_text": {"bbox": (0.20, 0.46, 0.60, 0.05), "importance": "low", "type": "text"},
    "submit_button": {"bbox": (0.35, 0.60, 0.30, 0.10), "importance": "high", "type": "CTA"},
}

# Deliberately nested: the card contains the button. Auto element detection
# produces this constantly, and it exercises smallest-box-wins.
NESTED_PAGE = {
    "product_card": {"bbox": (0.10, 0.10, 0.50, 0.50), "importance": "medium", "type": "image"},
    "buy_button": {"bbox": (0.20, 0.40, 0.15, 0.08), "importance": "high", "type": "CTA"},
    "sidebar": {"bbox": (0.70, 0.10, 0.25, 0.50), "importance": "low", "type": "non-interactive"},
}


def ecommerce_config() -> UIConfig:
    return build_ui_config("ecommerce_product_page", ECOMMERCE)


def form_config() -> UIConfig:
    return build_ui_config("form_page", FORM_PAGE)


def nested_config() -> UIConfig:
    return build_ui_config("nested_page", NESTED_PAGE)


# ----------------------------------------------------------------------


Target = Union[str, Tuple[float, float], None]
Step = Tuple[Target, float]


def scripted_session(
    ui_config: UIConfig,
    script: Sequence[Step],
    noise: float = CLEAN_NOISE,
    blink_rate: float = 0.0,
    dt: float = DEFAULT_DT,
    start_time: float = 1000.0,
    seed: int = 0,
    jitter: float = 0.0,
) -> List[GazeSample]:
    """Turn a list of (target, seconds) instructions into a gaze stream.

    A target is an element_id (gaze sits at that element's centre), an
    explicit (x, y), or None for background/whitespace.

    `jitter` adds a slow drift across the dwell, so a long look at one element
    isn't a single mathematically identical point repeated -- that would make
    dispersion exactly zero and let a broken fixation detector pass.
    """
    rng = random.Random(seed)
    boxes = ui_config.boxes
    samples: List[GazeSample] = []
    t = start_time

    for target, seconds in script:
        if isinstance(target, str):
            if target not in boxes:
                raise KeyError(f"script targets unknown element {target!r}")
            cx, cy = boxes[target].center
        elif target is None:
            cx, cy = 0.02, 0.97          # a margin, outside every box
        else:
            cx, cy = target

        n = max(1, int(round(seconds / dt)))
        for i in range(n):
            drift = jitter * (i / n - 0.5) if n > 1 else 0.0
            blink = rng.random() < blink_rate
            samples.append(GazeSample(
                timestamp=round(t, 6),
                x=min(max(cx + drift + rng.gauss(0, noise), 0.0), 1.0),
                y=min(max(cy + drift + rng.gauss(0, noise), 0.0), 1.0),
                valid=not blink,
                confidence=0.0 if blink else round(rng.uniform(0.7, 0.99), 3),
            ))
            t += dt

    return samples


# ----------------------------------------------------------------------
# named scenarios, mirroring backend/agents/mock_sessions.py


def clean_gaze_session(**kw) -> Tuple[List[GazeSample], UIConfig]:
    """CTA found early and looked at properly. Should raise no findings."""
    cfg = ecommerce_config()
    script: List[Step] = [
        ("product_image", 2.0),
        ("product_title", 1.5),
        ("checkout_button", 2.0),
        ("product_image", 1.5),
        ("checkout_button", 1.5),
        ("nav_bar", 0.8),
    ]
    return scripted_session(cfg, script, jitter=0.004, **kw), cfg


def ignored_cta_session(**kw) -> Tuple[List[GazeSample], UIConfig]:
    """Checkout button discovered late and barely looked at.

    Should reproduce agents' delayed_discovery + poor_visibility findings:
    ~9s before the CTA is first fixated, and well under 5% of gaze time on it.
    """
    cfg = ecommerce_config()
    script: List[Step] = [
        ("product_image", 5.0),
        ("product_title", 2.0),
        ("product_image", 2.5),
        ("nav_bar", 1.5),
        ("checkout_button", 0.45),
    ]
    return scripted_session(cfg, script, jitter=0.004, **kw), cfg


def scattered_session(**kw) -> Tuple[List[GazeSample], UIConfig]:
    """Attention bouncing back to a non-interactive banner.

    Should reproduce misleading_affordance (promo_banner is non-interactive
    and gets many fixations) and layout_confusion (repeated jumps back).
    """
    cfg = form_config()
    script: List[Step] = []
    for field_id in ("name_field", "email_field", "helper_text", "name_field"):
        script.append(("promo_banner", 0.8))
        script.append((field_id, 0.7))
    script.append(("promo_banner", 0.8))
    script.append(("submit_button", 0.9))
    return scripted_session(cfg, script, jitter=0.004, **kw), cfg


def noisy_session(**kw) -> Tuple[List[GazeSample], UIConfig]:
    """Realistic gaze error plus blinks, on the same script as clean.

    Exists so the tests can check that the metrics survive the noise level
    backend/gaze_estimation actually measures, rather than only working on
    unrealistically clean input.
    """
    kw.setdefault("noise", REALISTIC_NOISE)
    kw.setdefault("blink_rate", 0.08)
    return clean_gaze_session(**kw)


__all__ = [
    "GazeSample",
    "SAMPLE_RATE_HZ",
    "CLEAN_NOISE",
    "REALISTIC_NOISE",
    "BAD_NOISE",
    "ECOMMERCE",
    "FORM_PAGE",
    "NESTED_PAGE",
    "ecommerce_config",
    "form_config",
    "nested_config",
    "scripted_session",
    "clean_gaze_session",
    "ignored_cta_session",
    "scattered_session",
    "noisy_session",
]
