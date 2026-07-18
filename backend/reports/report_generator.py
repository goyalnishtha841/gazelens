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
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _build_narrative(pipeline_result: dict, ui_page: str) -> dict:
    """
    Turns the structured JSON into a couple of plain-language sentences and
    a top-level severity banner, so a non-technical reader gets the point
    in the first five seconds instead of having to parse a table first.
    """
    behavior = pipeline_result["behavior_summary"]
    issues = pipeline_result["issues"]
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

    page_name = ui_page.replace("_", " ")
    sentences = []
    if behavior["first_noticed"]:
        sentences.append(f"On the {page_name}, the first thing noticed was <strong>{behavior['first_noticed']}</strong>.")
    if behavior["ignored_important_elements"]:
        ignored = ", ".join(f"<strong>{e}</strong>" for e in behavior["ignored_important_elements"])
        sentences.append(f"{ignored} did not receive the attention expected for its importance.")
    if behavior["attention_scattered"]:
        sentences.append("Gaze repeatedly jumped between the same elements, suggesting the layout may be causing confusion.")
    if not issues:
        sentences.append("Attention was distributed in line with expectations for this page.")

    return {
        "banner_level": banner_level,
        "banner_text": banner_text,
        "summary_html": " ".join(sentences),
    }


def _render_html(pipeline_result: dict, ui_page: str, heatmap_path: str | None) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report_template.html.j2")
    narrative = _build_narrative(pipeline_result, ui_page)

    return template.render(
        session_id=pipeline_result["session_id"],
        ui_page=ui_page,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        behavior=pipeline_result["behavior_summary"],
        issues=pipeline_result["issues"],
        recommendations_kept=pipeline_result["recommendations_kept"],
        recommendations_rejected=pipeline_result["recommendations_rejected"],
        heatmap_path=heatmap_path,
        **narrative,
    )


def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    # filename= (not string=) makes WeasyPrint use the HTML file's own
    # directory as the base for relative paths, so <img src="foo_heatmap.png">
    # resolves the same way it did under wkhtmltopdf's --enable-local-file-access.
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))


def generate_report(pipeline_result: dict, ui_page: str, output_dir: str, heatmap_path: str | None = None) -> dict:
    """
    pipeline_result: output of orchestrator.run_pipeline(session)
    ui_page:          which test UI this session was run against
    output_dir:       where to write session_<id>.html / .pdf
    heatmap_path:      path to a heatmap image (absolute, or relative to output_dir)

    Returns {"html_path": ..., "pdf_path": ...}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session_id = pipeline_result["session_id"]
    html_path = output_dir / f"{session_id}.html"
    pdf_path = output_dir / f"{session_id}.pdf"

    html_content = _render_html(pipeline_result, ui_page, heatmap_path)
    html_path.write_text(html_content, encoding="utf-8")

    _html_to_pdf(html_path, pdf_path)

    return {"html_path": str(html_path), "pdf_path": str(pdf_path)}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

    from orchestrator import run_pipeline
    from mock_sessions import ALL_MOCK_SESSIONS
    from heatmap_stub import generate_attention_figure, DEMO_LAYOUTS

    OUTPUT_DIR = Path(__file__).parent / "generated"

    for session in ALL_MOCK_SESSIONS:
        result = run_pipeline(session)

        heatmap_file = OUTPUT_DIR / f"{session.session_id}_heatmap.png"
        layout = DEMO_LAYOUTS.get(session.ui_page, {})
        generate_attention_figure(session, layout, str(heatmap_file))

        paths = generate_report(
            result,
            ui_page=session.ui_page,
            output_dir=str(OUTPUT_DIR),
            heatmap_path=heatmap_file.name,  # relative to the html file's own directory
        )
        print(f"{session.session_id}: {paths['pdf_path']}")