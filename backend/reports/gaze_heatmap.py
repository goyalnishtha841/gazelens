"""
gaze_heatmap.py

The real heatmap: where the gaze actually went, drawn over a screenshot of
the page as it was shown.

Replaces heatmap_stub.py's attention figure as the report's main image.
(That figure shades each element's box by its dwell time, which is a
summary of attribution, not a picture of gaze. Its dwell-time bar chart is
still used beside this.)

How it is drawn:
  * every valid gaze sample is one unit of attention (samples arrive at a
    steady rate, so count is proportional to time)
  * the density is blurred with a Gaussian whose sigma is the session's
    measured gaze error -- the map is exactly as sharp as the measurement,
    and never suggests a precision the tracker didn't have
  * low-density areas stay transparent so the page shows through
  * element boxes are outlined faintly, so the map can be read against the
    layout attribution actually used

Imported by path from backend/api/pipeline.py, like the rest of reports/.
"""

from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

DEFAULT_SIZE = (1280, 720)
MIN_SIGMA_PX = 15.0       # a perfect tracker still shouldn't draw single pixels
GRID_STEP = 4             # density computed on a grid this many px per cell
VISIBLE_FRACTION = 0.03   # density below this share of the peak is dropped as noise

INK = "#1c2321"
INK_SOFT = "#5b6460"

# transparent -> blue -> green -> yellow -> red, the convention people read
# heatmaps with; alpha rises with density so the page stays visible
_COLORS = [
    (0.00, (0.10, 0.30, 0.90, 0.00)),
    (0.08, (0.10, 0.40, 0.95, 0.12)),
    (0.20, (0.10, 0.45, 0.95, 0.38)),
    (0.40, (0.15, 0.75, 0.35, 0.50)),
    (0.65, (0.98, 0.85, 0.15, 0.62)),
    (1.00, (0.90, 0.15, 0.10, 0.75)),
]
HEAT_CMAP = LinearSegmentedColormap.from_list(
    "gaze", [(p, c) for p, c in _COLORS]
)


def _gaussian_kernel(sigma: float) -> np.ndarray:
    radius = max(1, int(round(3 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-(x ** 2) / (2 * sigma ** 2))
    return k / k.sum()


def _blur(grid: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur (numpy only; scipy isn't a dependency)."""
    k = _gaussian_kernel(sigma)
    out = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, grid)
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, out)


def gaze_density(
    points: Iterable[Tuple[float, float]],
    size: Tuple[int, int],
    sigma_px: float,
) -> np.ndarray:
    """Normalised gaze points -> density grid (h/GRID_STEP, w/GRID_STEP), peak 1.

    Points outside [0, 1] are dropped: they were off the page.
    """
    w, h = size
    gw, gh = max(1, w // GRID_STEP), max(1, h // GRID_STEP)
    grid = np.zeros((gh, gw), dtype=float)
    for x, y in points:
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            gx = min(gw - 1, int(x * gw))
            gy = min(gh - 1, int(y * gh))
            grid[gy, gx] += 1.0
    if grid.max() <= 0:
        return grid
    grid = _blur(grid, max(MIN_SIGMA_PX, sigma_px) / GRID_STEP)
    return grid / grid.max()


def generate_gaze_heatmap(
    gaze_points: Sequence[dict],
    output_path: str,
    screenshot_path: Optional[str] = None,
    layout: Optional[Dict[str, Tuple[float, float, float, float]]] = None,
    labels: Optional[Dict[str, str]] = None,
    size: Optional[Tuple[int, int]] = None,
    sigma_px: Optional[float] = None,
    sigma_frac: Optional[float] = None,
) -> str:
    """Draw the heatmap and save it as a PNG. Returns output_path.

    gaze_points: GazePoint dicts in the same normalised space as `layout`
      ({"x", "y", "valid", ...}); invalid points are skipped.
    screenshot_path: the page as shown. Without one, a neutral canvas with the
      element boxes stands in -- still honest, just less legible.
    size: the page's pixel size when there's no screenshot.
    sigma_px: the session's gaze error in page pixels (blur width).
    sigma_frac: the same as a fraction of the page width -- use this when
      the screenshot's resolution may differ from the size the page was
      shown at. Wins over sigma_px.
    """
    background = None
    if screenshot_path and Path(screenshot_path).exists():
        background = plt.imread(screenshot_path)
        h, w = background.shape[:2]
    else:
        w, h = size or DEFAULT_SIZE

    pts = [(float(p["x"]), float(p["y"])) for p in gaze_points
           if p.get("valid", True) and p.get("x") is not None and p.get("y") is not None]
    if sigma_frac:
        sigma = float(sigma_frac) * w
    else:
        sigma = float(sigma_px) if sigma_px else MIN_SIGMA_PX
    density = gaze_density(pts, (w, h), sigma)

    dpi = 100
    fig_w, footer_in = 10.0, 0.45           # inches; footer holds the caption
    fig_h = fig_w * h / w + footer_in
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
    ax = fig.add_axes([0, footer_in / fig_h, 1, 1 - footer_in / fig_h])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")

    if background is not None:
        ax.imshow(background, extent=(0, w, h, 0), zorder=0)
    else:
        ax.add_patch(plt.Rectangle((0, 0), w, h, color="#f4f4f2", zorder=0))

    for eid, (x, y, bw, bh) in (layout or {}).items():
        ax.add_patch(plt.Rectangle(
            (x * w, y * h), bw * w, bh * h, fill=False, lw=0.8,
            ls=(0, (3, 3)), ec=INK_SOFT, alpha=0.55 if background is not None else 0.9,
            zorder=1,
        ))
        if background is None:
            ax.text(x * w + 6, y * h + 16, (labels or {}).get(eid, eid), fontsize=8,
                    color=INK_SOFT, zorder=1)

    # No hard mask: the colormap's alpha starts at 0, so sparse areas fade
    # out smoothly instead of ending on a jagged grid-cell edge.
    ax.imshow(np.where(density < VISIBLE_FRACTION, 0.0, density), extent=(0, w, h, 0),
              cmap=HEAT_CMAP, vmin=0, vmax=1, interpolation="bicubic", zorder=2)

    caption = (f"{len(pts)} gaze samples  ·  blur = measured gaze error "
               f"({sigma:.0f}px)  ·  red = most attention")
    if not pts:
        caption = "No valid gaze samples were recorded on this page."
    fig.text(0.01, 0.12 * footer_in / fig_h, caption, fontsize=9, color=INK_SOFT,
             va="bottom")

    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


__all__ = ["generate_gaze_heatmap", "gaze_density", "HEAT_CMAP"]
