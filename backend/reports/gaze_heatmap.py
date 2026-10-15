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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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

# App palette (frontend-new/src/index.css), so the images match the report.
BG = "#0A0E14"
TEXT = "#E8EEF5"
TEXT_SOFT = "#8A97A8"
ACCENT = "#2EE6C5"
CORAL = "#FF6B5A"
PAGE_DIM = 0.32           # how much the page is darkened under the overlay

# The GazeLens brand ramp -- cool #5B8CFF -> iris #2EE6C5 -> amber #FFB547
# -> coral #FF6B5A -- so reports and the app share one colour scale. Alpha
# rises with density so the page stays visible.
_COLORS = [
    (0.00, (0.357, 0.549, 1.000, 0.00)),
    (0.06, (0.357, 0.549, 1.000, 0.18)),
    (0.22, (0.357, 0.549, 1.000, 0.48)),
    (0.45, (0.180, 0.902, 0.773, 0.62)),
    (0.70, (1.000, 0.710, 0.278, 0.75)),
    (1.00, (1.000, 0.420, 0.353, 0.88)),
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


def _hotspots(density: np.ndarray, k: int = 3, min_sep_cells: int = 40, floor: float = 0.5):
    """The k strongest, well-separated peaks of the density, as grid cells."""
    d = density.copy()
    peaks = []
    for _ in range(k):
        idx = np.unravel_index(int(np.argmax(d)), d.shape)
        if d[idx] < floor:
            break
        peaks.append(idx)
        y, x = idx
        d[max(0, y - min_sep_cells):y + min_sep_cells + 1,
          max(0, x - min_sep_cells):x + min_sep_cells + 1] = 0
    return peaks


def _canvas(w: int, h: int, background, footer_in: float = 0.6, fig_w: float = 12.0):
    """Figure with the page on top and a dark caption bar below."""
    dpi = 150
    fig_h = fig_w * h / w + footer_in
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor=BG)
    ax = fig.add_axes([0, footer_in / fig_h, 1, 1 - footer_in / fig_h])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")
    if background is not None:
        ax.imshow(background, extent=(0, w, h, 0), zorder=0)
        ax.add_patch(plt.Rectangle((0, 0), w, h, color=BG, alpha=PAGE_DIM, lw=0, zorder=1))
    else:
        ax.add_patch(plt.Rectangle((0, 0), w, h, color="#111723", zorder=0))
    return fig, ax, fig_h, dpi


def _empty_layout(ax, layout, labels, w, h):
    """Without a screenshot, show the element boxes so the map has context."""
    for eid, (x, y, bw, bh) in (layout or {}).items():
        ax.add_patch(plt.Rectangle(
            (x * w, y * h), bw * w, bh * h, fill=True, lw=0.8,
            fc="#1A2230", ec="#2A3446", zorder=1,
        ))
        ax.text(x * w + 8, y * h + 18, (labels or {}).get(eid, eid), fontsize=8,
                color=TEXT_SOFT, zorder=1)


def _footer(fig, fig_h, footer_in, text, legend=None):
    y = 0.5 * footer_in / fig_h
    fig.text(0.015, y, text, fontsize=10, color=TEXT_SOFT, va="center")
    if legend == "heat":
        bar = fig.add_axes([0.74, y - 0.12 * footer_in / fig_h, 0.12, 0.24 * footer_in / fig_h])
        bar.imshow(np.linspace(0.15, 1, 256)[None, :], cmap=HEAT_CMAP, aspect="auto")
        bar.axis("off")
        fig.text(0.73, y, "less", fontsize=9, color=TEXT_SOFT, va="center", ha="right")
        fig.text(0.87, y, "more attention", fontsize=9, color=TEXT_SOFT, va="center")


def _save(fig, output_path: str, dpi: int) -> str:
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return output_path


def _load(screenshot_path, size):
    if screenshot_path and Path(screenshot_path).exists():
        background = plt.imread(screenshot_path)
        h, w = background.shape[:2]
        return background, w, h
    w, h = size or DEFAULT_SIZE
    return None, w, h


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
    screenshot_path: the page as shown, dimmed so the heat reads clearly.
      Without one, the element boxes on a dark canvas stand in.
    size: the page's pixel size when there's no screenshot.
    sigma_px: the session's gaze error in page pixels (blur width).
    sigma_frac: the same as a fraction of the page width -- use this when
      the screenshot's resolution may differ from the size the page was
      shown at. Wins over sigma_px.
    """
    background, w, h = _load(screenshot_path, size)

    pts = [(float(p["x"]), float(p["y"])) for p in gaze_points
           if p.get("valid", True) and p.get("x") is not None and p.get("y") is not None]
    if sigma_frac:
        sigma = float(sigma_frac) * w
    else:
        sigma = float(sigma_px) if sigma_px else MIN_SIGMA_PX
    density = gaze_density(pts, (w, h), sigma)

    footer_in = 0.6
    fig, ax, fig_h, dpi = _canvas(w, h, background, footer_in)
    if background is None:
        _empty_layout(ax, layout, labels, w, h)

    # No hard mask: the colormap's alpha starts at 0, so sparse areas fade
    # out smoothly instead of ending on a jagged grid-cell edge.
    shown = np.where(density < VISIBLE_FRACTION, 0.0, density)
    ax.imshow(shown, extent=(0, w, h, 0), cmap=HEAT_CMAP, vmin=0, vmax=1,
              interpolation="bicubic", zorder=2)
    if density.max() > 0:
        # soft outline around the hottest areas
        gy, gx = density.shape
        xs = np.linspace(0, w, gx); ys = np.linspace(0, h, gy)
        ax.contour(xs, ys, density, levels=[0.55, 0.8], colors=["white"],
                   linewidths=[0.6, 0.9], alpha=0.45, zorder=3)

    # Number the top spots so the report text can refer to them.
    for rank, (cy, cx) in enumerate(_hotspots(density, min_sep_cells=max(20, int(0.09 * w / GRID_STEP))), start=1):
        px, py = (cx + 0.5) * w / density.shape[1], (cy + 0.5) * h / density.shape[0]
        r = max(14.0, 0.016 * w)
        ax.add_patch(plt.Circle((px, py), r, fc=BG, ec="white", lw=1.6, alpha=0.92, zorder=4))
        ax.text(px, py, str(rank), ha="center", va="center", fontsize=11,
                color="white", fontweight="bold", zorder=5)

    caption = (f"{len(pts)} gaze samples   ·   numbers mark the hottest spots   ·   "
               f"blur matches the measured tracking error ({sigma:.0f}px)")
    if not pts:
        caption = "No valid gaze samples were recorded on this page."
    _footer(fig, fig_h, footer_in, caption, legend="heat" if pts else None)
    return _save(fig, output_path, dpi)


def detect_fixations(
    gaze_points: Sequence[dict],
    size: Tuple[int, int],
    radius_px: float,
    min_duration: float = 0.12,
    max_gap: float = 0.25,
) -> List[Dict]:
    """Dispersion-style fixations from the raw stream, for drawing only.

    Consecutive valid samples that stay within radius_px of their running
    centre form one fixation; anything shorter than min_duration is dropped.
    Returns [{"x", "y" (normalised), "duration" (s), "start" (s)}].
    """
    w, h = size
    pts = [p for p in gaze_points if p.get("valid", True) and p.get("x") is not None]
    fixations: List[Dict] = []
    cluster: List[dict] = []

    def close():
        if len(cluster) >= 2:
            dur = float(cluster[-1].get("timestamp", 0)) - float(cluster[0].get("timestamp", 0))
            if dur >= min_duration:
                fixations.append({
                    "x": float(np.median([c["x"] for c in cluster])),
                    "y": float(np.median([c["y"] for c in cluster])),
                    "duration": dur,
                    "start": float(cluster[0].get("timestamp", 0)),
                })

    for p in pts:
        if cluster:
            cx = np.mean([c["x"] for c in cluster]); cy = np.mean([c["y"] for c in cluster])
            gap = float(p.get("timestamp", 0)) - float(cluster[-1].get("timestamp", 0))
            if np.hypot((p["x"] - cx) * w, (p["y"] - cy) * h) > radius_px or gap > max_gap:
                close()
                cluster = []
        cluster.append(p)
    close()
    return fixations


def group_into_areas(fixations: Sequence[Dict], size: Tuple[int, int], radius_px: float) -> Dict:
    """Fixations -> areas of the page and the order they were visited.

    Webcam noise splits one long look into several nearby fixations. Any
    fixations within radius_px of an area's centre join it, so the path
    shows real moves between parts of the page, not jitter. Consecutive
    fixations in the same area are one visit.
    """
    w, h = size
    centres: List[List[float]] = []   # running sums: x, y, weight
    time: List[float] = []
    visits: List[int] = []
    for f in fixations:
        x, y, d = f["x"] * w, f["y"] * h, max(f["duration"], 0.05)
        best, best_d = None, radius_px
        for i, (sx, sy, sw) in enumerate(centres):
            dist = np.hypot(x - sx / sw, y - sy / sw)
            if dist <= best_d:
                best, best_d = i, dist
        if best is None:
            centres.append([x * d, y * d, d]); time.append(0.0); best = len(centres) - 1
        else:
            centres[best][0] += x * d; centres[best][1] += y * d; centres[best][2] += d
        time[best] += d
        if not visits or visits[-1] != best:
            visits.append(best)
    return {
        "centres": [(sx / sw, sy / sw) for sx, sy, sw in centres],
        "time": time,
        "visits": visits,
        "n_visits": max(0, len(visits) - 1),
    }


def generate_gaze_path(
    gaze_points: Sequence[dict],
    output_path: str,
    screenshot_path: Optional[str] = None,
    layout: Optional[Dict[str, Tuple[float, float, float, float]]] = None,
    labels: Optional[Dict[str, str]] = None,
    size: Optional[Tuple[int, int]] = None,
    error_frac: Optional[float] = None,
    max_steps: int = 30,
) -> str:
    """The eye path: where the eyes stopped, in order, over the page.

    Circles are fixations found in the gaze stream itself (not element
    centres), sized by how long the eyes stayed; the line runs teal -> coral
    in visit order. Very long sessions show the first max_steps fixations.
    """
    background, w, h = _load(screenshot_path, size)
    radius = max(40.0, 0.9 * (error_frac or 0.05) * w)
    fixes = detect_fixations(gaze_points, (w, h), radius)
    total = len(fixes)
    fixes = fixes[:max_steps]

    footer_in = 0.6
    fig, ax, fig_h, dpi = _canvas(w, h, background, footer_in)
    if background is None:
        _empty_layout(ax, layout, labels, w, h)

    areas = group_into_areas(fixes, (w, h), radius * 1.6)
    if areas["visits"]:
        path_cmap = LinearSegmentedColormap.from_list("path", [ACCENT, "#FFB547", CORAL])
        centres = areas["centres"]
        visits = areas["visits"][:max_steps]
        n = len(visits)
        seen_edges: Dict[Tuple[int, int], int] = {}
        for i in range(n - 1):
            a_, b_ = visits[i], visits[i + 1]
            c = path_cmap(i / max(n - 2, 1))
            # curve each repeat of the same hop a bit more, so back-and-forth stays readable
            key = (min(a_, b_), max(a_, b_))
            k = seen_edges.get(key, 0); seen_edges[key] = k + 1
            rad = (0.18 + 0.12 * k) * (1 if a_ < b_ else -1)
            ax.annotate("", xy=centres[b_], xytext=centres[a_], zorder=4,
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=2.0, alpha=0.9,
                                        shrinkA=16, shrinkB=18, mutation_scale=14,
                                        connectionstyle=f"arc3,rad={rad}"))
        base = max(14.0, 0.012 * w)
        total_time = max(sum(areas["time"]), 1e-6)
        for idx, (cx, cy) in enumerate(centres):
            order = [i + 1 for i, v in enumerate(visits) if v == idx]
            if not order:
                continue
            c = path_cmap((order[0] - 1) / max(n - 1, 1))
            share = areas["time"][idx] / total_time
            r = base * (1.0 + 2.2 * np.sqrt(share))
            ax.add_patch(plt.Circle((cx, cy), r * 1.55, fc=c, ec="none", alpha=0.2, zorder=5))
            ax.add_patch(plt.Circle((cx, cy), r, fc=BG, ec=c, lw=2.4, alpha=0.95, zorder=6))
            ax.text(cx, cy, str(order[0]), ha="center", va="center", fontsize=11,
                    color="white", fontweight="bold", zorder=7)
            label = f"{share:.0%} of time"
            if len(order) > 1:
                more = ", ".join(str(o) for o in order[1:5]) + ("…" if len(order) > 5 else "")
                label += f"  ·  back at {more}"
            ax.text(cx + r + 8, cy, label, ha="left", va="center", fontsize=8.5, color="white",
                    zorder=7, bbox=dict(boxstyle="round,pad=0.35,rounding_size=0.8", fc=BG, ec=c, lw=1, alpha=0.88))
        caption = (f"{len(centres)} areas looked at, {areas['n_visits']} moves between them"
                   + (f" (first {n} shown)" if areas["n_visits"] > n else "")
                   + "   ·   numbers = order first seen   ·   bigger circle = more time")
    else:
        caption = "Not enough steady gaze to draw an eye path for this page."
    _footer(fig, fig_h, footer_in, caption)
    return _save(fig, output_path, dpi)


__all__ = ["generate_gaze_heatmap", "generate_gaze_path", "detect_fixations", "gaze_density", "HEAT_CMAP"]
