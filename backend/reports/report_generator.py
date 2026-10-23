"""
report_generator.py

Turns an orchestrator.run_pipeline() result into an HTML report, then a
PDF. This is deliberately decoupled from the agent chain: it only reads
the JSON shape orchestrator.py already produces, so nothing here changes
when the agents get smarter or when mock sessions get replaced by real ones.

Uses WeasyPrint (pip install weasyprint) for the HTML -> PDF step.
wkhtmltopdf was dropped from this file because it's no longer maintained
upstream and isn't installable via Homebrew anymore -- WeasyPrint is a
pure pip package, so `pip install -r requirements.txt` is enough on any
machine, no separate system binary to hunt down.
"""

import datetime
import html
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from pdf_backends import PDFBackendUnavailable, html_to_pdf

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _build_narrative(pipeline_result: dict, ui_page: str) -> dict:
    """
    Turns the structured JSON into a couple of plain-language sentences and
    a top-level severity banner, so a non-technical reader gets the point
    in the first five seconds instead of having to parse a table first.
    """
    behavior = pipeline_result["behavior_summary"]
    issues = pipeline_result["issues"]
    quality = pipeline_result.get("quality") or {}
    label = _labeller(pipeline_result)
    page_name = PAGE_NAMES.get(ui_page, ui_page.replace("_", " ")).replace("the ", "", 1)

    if quality.get("level") == "insufficient":
        reasons = "; ".join(quality.get("reasons") or []) or "the gaze data was unreliable"
        return {
            "banner_level": "insufficient",
            "banner_text": "Not enough reliable gaze data to evaluate this page",
            "summary_html": f"No findings were drawn from this session on the {page_name}: "
                            f"{reasons}. Recalibrate and run it again.",
        }

    high_count = sum(1 for i in issues if i["severity"] == "High")
    medium_count = sum(1 for i in issues if i["severity"] == "Medium")

    if high_count > 0:
        banner_level = "critical"
        banner_text = f"{high_count} high-severity issue{'s' if high_count != 1 else ''} found — review before shipping"
    elif medium_count > 0:
        banner_level = "warning"
        banner_text = f"{medium_count} usability concern{'s' if medium_count != 1 else ''} worth addressing"
    else:
        banner_level = "good"
        banner_text = "No significant usability issues detected"

    sentences = []
    if behavior["first_noticed"]:
        sentences.append(f"People noticed <strong>{label(behavior['first_noticed'])}</strong> first.")
    if behavior["ignored_important_elements"]:
        ignored = ", ".join(f"<strong>{label(e)}</strong>" for e in behavior["ignored_important_elements"])
        sentences.append(f"{ignored} {'was' if len(behavior['ignored_important_elements']) == 1 else 'were'} barely looked at, even though {'it matters' if len(behavior['ignored_important_elements']) == 1 else 'they matter'}.")
    if behavior["attention_scattered"]:
        sentences.append("Eyes kept jumping back and forth between the same parts, a sign the layout may be confusing.")
    if not issues:
        sentences.append("Attention went where you'd expect on this page.")
    # LLM mode: the behaviour agent's own account replaces the templated
    # sentences. It was already re-checked by the critic, and cleared
    # upstream if any number in it didn't hold.
    if behavior.get("narrative"):
        sentences = [html.escape(behavior["narrative"])]
    if quality.get("level") == "limited":
        sentences.append("Eye-tracking precision was only fair, so no finding is rated above \"worth fixing\".")

    return {
        "banner_level": banner_level,
        "banner_text": banner_text,
        "summary_html": " ".join(sentences),
    }


def _labeller(pipeline_result: dict):
    """element_id -> readable name, from the consolidated result's labels."""
    labels = pipeline_result.get("element_labels") or {}

    def label(element_id: str) -> str:
        if element_id == "__session__":
            return "Whole page"
        return labels.get(element_id, element_id)

    return label


def _build_before_after(pipeline_result: dict) -> list[dict]:
    """One before/after row per kept recommendation.

    "Before" is the critic's own re-derived evidence (VerifiedRecommendation.
    evidence), not a fresh lookup against the issue -- that's the evidence
    that was actually independently re-verified against raw session metrics,
    so before/after uses exactly the number the report already stands behind
    rather than a second copy of it from a different stage of the pipeline.

    "After" is the recommendation text as written, deliberately NOT a
    generated mockup or a synthesised new layout: nothing in this pipeline
    has verified what a redesigned page would actually measure, so drawing
    one would present a guess with the same visual authority as the
    measured heatmap next to it. The instruction the recommendation gives
    is the honest "after" -- what to change, not a fabricated result of
    having changed it.
    """
    rows = []
    for rec in pipeline_result.get("recommendations_kept", []):
        rows.append({
            "element_id": rec["element_id"],
            "before": "; ".join(rec.get("evidence", [])) or "No evidence recorded.",
            "after": rec["recommendation"],
            "support": rec.get("support"),
            "confidence": rec.get("confidence"),
        })
    return rows


PAGE_NAMES = {
    "uploaded_image": "the uploaded screenshot",
    "ecommerce_product_page": "the shop product page",
    "form_page": "the sign-up form",
    "dashboard_page": "the dashboard page",
    "login_page": "the login page",
    "article_page": "the news article page",
    "captured_page": "your website",
}


def _clean(text: str) -> str:
    """Drop the trailing "(Evidence: ...)" the agents append; the PDF shows
    the evidence separately."""
    import re
    return re.sub(r"\s*\(Evidence:.*\)\s*$", "", text or "")


def _render_html(pipeline_result: dict, ui_page: str, heatmap_path: str | None,
                 scanpath_path: str | None = None,
                 dwell_chart_path: str | None = None,
                 page_name: str | None = None,
                 attention: dict | None = None) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["label"] = _labeller(pipeline_result)
    env.filters["clean"] = _clean
    env.filters["truncate_list"] = lambda items, n: list(items)[:n] + (["…"] if len(list(items)) > n else [])
    template = env.get_template("report_template.html.j2")
    narrative = _build_narrative(pipeline_result, ui_page)

    return template.render(
        session_id=pipeline_result["session_id"],
        ui_page=ui_page,
        page_name=page_name or PAGE_NAMES.get(ui_page, ui_page.replace("_", " ")),
        attention=attention,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        behavior=pipeline_result["behavior_summary"],
        issues=pipeline_result["issues"],
        recommendations_kept=pipeline_result["recommendations_kept"],
        recommendations_rejected=pipeline_result["recommendations_rejected"],
        before_after=_build_before_after(pipeline_result),
        heatmap_path=heatmap_path,
        scanpath_path=scanpath_path,
        dwell_chart_path=dwell_chart_path,
        quality=pipeline_result.get("quality"),
        llm=pipeline_result.get("llm") or {"mode": "rules", "audit": []},
        **narrative,
    )


def _html_to_pdf(html_path: Path, pdf_path: Path) -> str:
    # Delegates to pdf_backends, which tries WeasyPrint first and falls back
    # to headless Chromium. Both resolve the HTML file's own directory as the
    # base for relative paths, so <img src="foo_heatmap.png"> works the same
    # way it did under wkhtmltopdf's --enable-local-file-access.
    #
    # Backends are imported lazily in there: WeasyPrint binds to native GTK
    # libraries pip cannot install on Windows, and importing it at module
    # scope used to take this whole module down -- losing the HTML report too,
    # which needs nothing native.
    return html_to_pdf(html_path, pdf_path)


def generate_report(pipeline_result: dict, ui_page: str, output_dir: str, heatmap_path: str | None = None,
                    scanpath_path: str | None = None, dwell_chart_path: str | None = None,
                    page_name: str | None = None, attention: dict | None = None) -> dict:
    """
    pipeline_result: output of orchestrator.run_pipeline(session)
    ui_page:          which test UI this session was run against
    output_dir:       where to write session_<id>.html / .pdf
    heatmap_path:      path to a heatmap image (absolute, or relative to output_dir)
    scanpath_path:     path to a gaze-path image (absolute, or relative to output_dir)

    Returns {"html_path": ..., "pdf_path": ...}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = pipeline_result["session_id"]
    html_path = output_dir / f"{session_id}.html"
    pdf_path = output_dir / f"{session_id}.pdf"

    html_content = _render_html(pipeline_result, ui_page, heatmap_path, scanpath_path,
                                dwell_chart_path, page_name=page_name, attention=attention)
    html_path.write_text(html_content, encoding="utf-8")

    # HTML is written first and unconditionally, so a machine that can't
    # produce a PDF still gets a readable report rather than nothing.
    #
    # A PDF failure must NOT propagate: it would discard the html_path of a
    # file that has already been written, which defeats the point of writing
    # it first. The caller gets the HTML plus pdf_error explaining what to
    # install, and can decide whether the PDF mattered.
    backend = None
    pdf_error = None
    try:
        backend = _html_to_pdf(html_path, pdf_path)
    except PDFBackendUnavailable as exc:
        pdf_error = str(exc)

    return {
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if backend else None,
        "pdf_backend": backend,
        "pdf_error": pdf_error,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

    from orchestrator import run_pipeline
    from mock_sessions import ALL_MOCK_SESSIONS
    from heatmap_stub import generate_attention_figure, generate_scanpath_figure, DEMO_LAYOUTS

    OUTPUT_DIR = Path(__file__).parent / "generated"

    for session in ALL_MOCK_SESSIONS:
        result = run_pipeline(session)

        layout = DEMO_LAYOUTS.get(session.ui_page, {})
        heatmap_file = OUTPUT_DIR / f"{session.session_id}_heatmap.png"
        generate_attention_figure(session, layout, str(heatmap_file))
        scanpath_file = OUTPUT_DIR / f"{session.session_id}_scanpath.png"
        generate_scanpath_figure(session, layout, str(scanpath_file))

        paths = generate_report(
            result,
            ui_page=session.ui_page,
            output_dir=str(OUTPUT_DIR),
            heatmap_path=heatmap_file.name,   # relative to the html file's own directory
            scanpath_path=scanpath_file.name,
        )
        print(f"{session.session_id}: {paths['pdf_path']}")