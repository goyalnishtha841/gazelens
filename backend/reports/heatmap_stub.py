"""
heatmap_stub.py

PLACEHOLDER for Student 3's real heatmap/attribution renderer (Task 4).
Real dwell_time numbers drive everything drawn here -- only the element
POSITIONS are fake (stand-ins for real bounding boxes from the UI config).

Produces one combined figure with two panels, designed to be read by a
non-technical stakeholder in under 5 seconds:
  LEFT  -- a page-layout mockup with each element drawn as a box, shaded
           by how much attention it received (darker = more attention).
           This reads like "a picture of the page" instead of abstract
           floating circles.
  RIGHT -- a horizontal bar chart ranking elements by % of total gaze
           time, with a dashed threshold line so it's obvious at a glance
           which elements fell below the visibility bar.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path

INK = "#1c2321"
INK_SOFT = "#5b6460"
ACCENT_HIGH = "#c4432b"
FRAME = "#d8d5ce"
GOOD = "#3e8c63"

HEAT_CMAP = LinearSegmentedColormap.from_list("heat", ["#f4f6f4", "#f0d6cd", "#dd8064", ACCENT_HIGH])

# Start (GOOD, green) -> end (ACCENT_HIGH, red) -- so a point's colour alone
# says roughly when in the session it happened, without reading the number.
PATH_CMAP = LinearSegmentedColormap.from_list("path", [GOOD, "#c99a3e", ACCENT_HIGH])


def generate_attention_figure(session, layout: dict, output_path: str, dwell_threshold_pct: float = 5.0) -> str:
    """
    layout: element_id -> (x, y, w, h) in normalized [0,1] page-space,
            (x, y) = top-left corner, y grows downward (screen convention).
    """
    fig, (ax_map, ax_bar) = plt.subplots(
        1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.1, 1]}
    )
    fig.patch.set_facecolor("white")

    max_dwell = max(session.dwell_time.values()) if session.dwell_time else 1.0

    # ---------- LEFT: page-layout attention map ----------
    ax_map.set_xlim(0, 1)
    ax_map.set_ylim(0, 1)
    ax_map.invert_yaxis()
    ax_map.axis("off")
    ax_map.add_patch(mpatches.FancyBboxPatch(
        (0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0,rounding_size=0.01",
        linewidth=1, edgecolor=FRAME, facecolor="#fbfbfa",
    ))

    for element_id, (x, y, w, h) in layout.items():
        dwell = session.dwell_time.get(element_id, 0.0)
        intensity = min(dwell / max_dwell, 1.0) if max_dwell > 0 else 0.0
        color = HEAT_CMAP(intensity)
        importance = session.element_importance.get(element_id, "medium")

        edge_color = ACCENT_HIGH if importance == "high" else FRAME
        edge_width = 1.8 if importance == "high" else 1.0

        ax_map.add_patch(mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012",
            linewidth=edge_width, edgecolor=edge_color, facecolor=color,
        ))
        dwell_pct = session.dwell_pct(element_id)
        text_color = "white" if intensity > 0.55 else INK
        ax_map.text(
            x + w / 2, y + h / 2, f"{element_id}\n{dwell_pct:.1f}%",
            ha="center", va="center", fontsize=7.3, color=text_color, linespacing=1.4,
        )

    ax_map.set_title("Where attention landed", fontsize=10, color=INK, loc="left", pad=10, fontweight="bold")

    # ---------- RIGHT: dwell-time ranking bar chart ----------
    items = sorted(session.dwell_time.items(), key=lambda kv: session.dwell_pct(kv[0]))
    labels = [k for k, _ in items]
    pcts = [session.dwell_pct(k) for k, _ in items]
    colors = [
        ACCENT_HIGH if (session.element_importance.get(k) == "high" and p < dwell_threshold_pct) else
        GOOD if session.element_importance.get(k) == "high" else "#9aa39d"
        # strict: labels and pcts are built from the same sorted list, so a
        # length mismatch is impossible today -- but a silent zip truncation
        # here would drop bars off the chart rather than raise, and a heatmap
        # missing an element reads as "that element got no attention".
        for k, p in zip(labels, pcts, strict=True)
    ]

    y_pos = range(len(labels))
    ax_bar.barh(y_pos, pcts, color=colors, height=0.55)
    ax_bar.set_yticks(list(y_pos))
    ax_bar.set_yticklabels(labels, fontsize=8, color=INK)
    ax_bar.set_xlabel("% of total gaze time", fontsize=8, color=INK_SOFT)
    ax_bar.axvline(dwell_threshold_pct, color=INK, linestyle="--", linewidth=1, alpha=0.6)
    ax_bar.set_ylim(-0.9, len(labels) - 0.3)
    ax_bar.text(
        dwell_threshold_pct, -0.85, f"{dwell_threshold_pct:.0f}% threshold",
        fontsize=7, color=INK_SOFT, ha="left", va="bottom",
    )
    ax_bar.set_title("Attention share by element", fontsize=10, color=INK, loc="left", pad=10, fontweight="bold")
    for spine in ["top", "right"]:
        ax_bar.spines[spine].set_visible(False)
    ax_bar.tick_params(length=0)

    fig.tight_layout(pad=1.4)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor="white")
    plt.close(fig)
    return output_path


def generate_scanpath_figure(session, layout: dict, output_path: str) -> str:
    """The sequence heatmap can't show: WHERE attention went, in ORDER.

    A dwell-time heatmap answers "how much did each element get" but
    collapses time -- two sessions with identical dwell totals can have
    completely different paths (one steady progression vs. one that
    ping-pongs back and forth), and only the second is what Agent 1's
    layout_confusion rule is actually flagging. This draws that path:
    numbered points at each element's centre, connected in visit order,
    start and end marked distinctly.

    Consecutive repeats in session.scanpath (the same element gazed at
    for several samples in a row) are collapsed into one point -- they're
    one fixation, not several. A NON-consecutive repeat (the element shows
    up again later) gets its own point and its own arrow back, which is
    the revisit signal layout_confusion and repeated_revisits are built on;
    collapsing those too would erase the exact thing this figure exists
    to show.

    layout: same element_id -> (x, y, w, h) normalised boxes the heatmap
    uses, so the two figures are directly comparable side by side.
    """
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    fig.patch.set_facecolor("white")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.invert_yaxis()
    ax.axis("off")
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0,rounding_size=0.01",
        linewidth=1, edgecolor=FRAME, facecolor="#fbfbfa",
    ))

    for element_id, (x, y, w, h) in layout.items():
        ax.add_patch(mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.012",
            linewidth=1.0, edgecolor=FRAME, facecolor="#f4f5f3",
        ))
        ax.text(x + w / 2, y + h + 0.025, element_id, ha="center", va="top",
                fontsize=6.3, color=INK_SOFT)

    # Collapse consecutive duplicates -- see docstring.
    steps = []
    for element_id in session.scanpath:
        if not steps or steps[-1] != element_id:
            steps.append(element_id)

    def centre(element_id):
        box = layout.get(element_id)
        if box is None:
            return None
        x, y, w, h = box
        return x + w / 2, y + h / 2

    points = [(eid, centre(eid)) for eid in steps]
    points = [(eid, c) for eid, c in points if c is not None]  # off-layout ids skipped, not guessed at

    # A revisited element's centre gets plotted more than once -- without an
    # offset those circles land exactly on top of each other and only the
    # last one drawn stays visible, which HIDES the revisit instead of
    # showing it. Fanning each repeat out around the true centre keeps every
    # visit visible and keeps the revisit count itself readable at a glance,
    # which matters here specifically: repeated_revisits and layout_confusion
    # are both defined by revisits, so a figure that visually erases them
    # would misrepresent the exact thing it's illustrating.
    visit_counts = {}
    OFFSET_RADIUS = 0.02

    n = len(points)
    plotted = []
    for i, (element_id, (cx, cy)) in enumerate(points):
        visit = visit_counts.get(element_id, 0)
        visit_counts[element_id] = visit + 1
        if visit == 0:
            px, py = cx, cy
        else:
            angle = visit * 2.399963  # golden angle -- successive offsets don't stack in a line
            px = cx + OFFSET_RADIUS * visit ** 0.5 * np.cos(angle)
            py = cy + OFFSET_RADIUS * visit ** 0.5 * np.sin(angle)
        plotted.append((px, py))

        frac = i / max(n - 1, 1)
        color = PATH_CMAP(frac)
        if i > 0:
            qx, qy = plotted[i - 1]
            ax.annotate(
                "", xy=(px, py), xytext=(qx, qy),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.3, alpha=0.85,
                                shrinkA=8, shrinkB=8),
            )
        is_start, is_end = i == 0, i == n - 1
        radius = 0.028 if (is_start or is_end) else 0.018
        ax.add_patch(mpatches.Circle(
            (px, py), radius,
            facecolor=GOOD if is_start else (ACCENT_HIGH if is_end else color),
            edgecolor="white", linewidth=1.1, zorder=5,
        ))
        if is_start or is_end or n <= 12:
            ax.text(px, py, str(i + 1), ha="center", va="center",
                    fontsize=6.0, color="white", fontweight="bold", zorder=6)

    ax.set_title("Gaze path, in order", fontsize=10, color=INK, loc="left", pad=10, fontweight="bold")
    legend_handles = [
        mpatches.Patch(facecolor=GOOD, edgecolor="none", label="First fixation"),
        mpatches.Patch(facecolor=ACCENT_HIGH, edgecolor="none", label="Last fixation"),
    ]
    ax.legend(handles=legend_handles, loc="lower center", bbox_to_anchor=(0.5, -0.08),
              ncol=2, fontsize=7, frameon=False, labelcolor=INK_SOFT)

    fig.tight_layout(pad=1.2)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor="white")
    plt.close(fig)
    return output_path


# Kept for backwards compatibility with anything importing the old name.
def generate_placeholder_heatmap(session, element_positions: dict, output_path: str) -> str:
    layout = {eid: (x - 0.08, y - 0.05, 0.16, 0.1) for eid, (x, y) in element_positions.items()}
    return generate_attention_figure(session, layout, output_path)


# Rough normalized (x, y, w, h) bounding boxes per test page -- stand-ins for
# real positions that will come from each test UI's actual bbox config (test_uis/).
DEMO_LAYOUTS = {
    "ecommerce_product_page": {
        "nav_bar": (0.05, 0.03, 0.90, 0.08),
        "product_image": (0.05, 0.16, 0.40, 0.55),
        "product_title": (0.50, 0.16, 0.45, 0.14),
        "checkout_button": (0.50, 0.38, 0.28, 0.10),
    },
    "form_page": {
        "promo_banner": (0.10, 0.04, 0.80, 0.09),
        "name_field": (0.20, 0.20, 0.60, 0.09),
        "email_field": (0.20, 0.34, 0.60, 0.09),
        "helper_text": (0.20, 0.46, 0.60, 0.05),
        "submit_button": (0.35, 0.60, 0.30, 0.10),
    },
    "dashboard_page": {
        "nav_menu": (0.05, 0.03, 0.90, 0.06),
        "chart_widget": (0.05, 0.13, 0.55, 0.48),
        "sidebar_ad": (0.65, 0.13, 0.30, 0.14),
        "promo_widget": (0.65, 0.31, 0.30, 0.14),
        "help_icon": (0.87, 0.03, 0.08, 0.05),
        "cta_primary": (0.05, 0.66, 0.25, 0.09),
        "cta_secondary": (0.33, 0.66, 0.25, 0.09),
        "footer_link": (0.05, 0.90, 0.20, 0.04),
    },
}