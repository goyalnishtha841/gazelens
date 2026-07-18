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
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path

INK = "#1c2321"
INK_SOFT = "#5b6460"
ACCENT_HIGH = "#c4432b"
FRAME = "#d8d5ce"
GOOD = "#3e8c63"

HEAT_CMAP = LinearSegmentedColormap.from_list("heat", ["#f4f6f4", "#f0d6cd", "#dd8064", ACCENT_HIGH])


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
        for k, p in zip(labels, pcts)
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