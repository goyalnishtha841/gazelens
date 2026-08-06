"""
pdf_backends.py

HTML -> PDF, with a fallback chain, because the original single dependency
does not install everywhere.

THE PROBLEM
-----------
report_generator.py originally imported WeasyPrint at module scope. WeasyPrint
is a pure pip package, but it binds to native GTK libraries (libgobject,
pango, cairo) that pip cannot install on Windows. On a machine without a
GTK runtime, `from weasyprint import HTML` raises OSError -- and because the
import was at module scope, that took down the whole module: no HTML report
either, even though the HTML path needs nothing native at all.

THE FIX
-------
Two changes in behaviour:

  1. Backends are tried in order and imported LAZILY, so a missing one costs
     a fallback rather than an import crash.
  2. Chromium is the second backend. That is not a new dependency: the README
     already requires `playwright install chromium` for backend/render, so on
     any machine set up per the instructions it is present. Chromium is also
     the more faithful renderer of the two -- it is a browser, and the report
     template is a web page.

Order is weasyprint first, deliberately: it is what the existing reports were
authored and reviewed against, so nothing about their appearance changes on
the machines where it already works.

wkhtmltopdf is still not in the chain -- it remains unmaintained upstream,
which was the original reason for dropping it.
"""

import contextlib
import io
from pathlib import Path
from typing import Callable, List, Tuple


class PDFBackendUnavailable(RuntimeError):
    """No usable HTML -> PDF backend on this machine."""


@contextlib.contextmanager
def _quiet_import():
    """Swallow a failing backend's import chatter.

    WeasyPrint prints a multi-line "could not import some external libraries"
    banner when its GTK bind fails. On a machine using the Chromium fallback
    that appears on every successful run and reads like a failure. A fallback
    that worked should be quiet; the error path below still reports
    everything it tried.

    Both streams are captured because WeasyPrint writes that banner to
    STDOUT, not stderr -- redirecting stderr alone silences nothing, and
    shell `2>/dev/null` doesn't touch it either.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


def _weasyprint(html_path: Path, pdf_path: Path) -> None:
    # filename= (not string=) makes WeasyPrint resolve the HTML file's own
    # relative asset paths -- the embedded heatmap PNG in particular.
    with _quiet_import():
        from weasyprint import HTML

    HTML(filename=str(html_path)).write_pdf(str(pdf_path))


def _chromium_render(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,      # keep the report's colour blocks
                margin={"top": "12mm", "bottom": "12mm",
                        "left": "10mm", "right": "10mm"},
            )
        finally:
            browser.close()


def _chromium(html_path: Path, pdf_path: Path) -> None:
    """Print the page with headless Chromium via Playwright.

    Loaded over file:// so relative asset paths resolve exactly as they do in
    a browser, matching WeasyPrint's filename= behaviour. `networkidle` waits
    for the heatmap image to actually load -- printing on `load` alone can
    race it and emit a PDF with a blank figure.

    THE THREAD IS NOT OPTIONAL. Playwright's sync API refuses to run when an
    asyncio event loop is already running in the calling thread:
    "It looks like you are using Playwright Sync API inside the asyncio loop."
    Report generation is triggered from a FastAPI request, so that is exactly
    where it runs. Handing the work to a plain worker thread -- which has no
    loop of its own -- lets the one synchronous implementation serve both
    callers, instead of maintaining a parallel async version for the API.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _chromium_render(html_path, pdf_path)     # no loop here, run directly
        return

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_chromium_render, html_path, pdf_path).result()


BACKENDS: List[Tuple[str, Callable[[Path, Path], None]]] = [
    ("weasyprint", _weasyprint),
    ("chromium", _chromium),
]


def available_backends() -> List[str]:
    """Which backends could actually run here, cheapest check first.

    Used by the diagnostics in report_generator and worth calling before a
    long pipeline run: finding out at the final step that no PDF can be
    written wastes everything before it.
    """
    found: List[str] = []
    try:
        with _quiet_import():
            import weasyprint  # noqa: F401
        found.append("weasyprint")
    except Exception:       # noqa: BLE001 -- OSError from the GTK bind, not just ImportError
        pass
    try:
        import playwright  # noqa: F401
        found.append("chromium")
    except ImportError:
        pass
    return found


def html_to_pdf(html_path: Path, pdf_path: Path) -> str:
    """Render `html_path` to `pdf_path`. Returns the backend that succeeded.

    Raises PDFBackendUnavailable listing what was tried and why each failed,
    rather than surfacing whichever error happened to come last.
    """
    html_path = Path(html_path)
    pdf_path = Path(pdf_path)
    failures: List[str] = []

    for name, render in BACKENDS:
        try:
            render(html_path, pdf_path)
            return name
        except Exception as exc:            # noqa: BLE001
            # Deliberately broad: a backend can fail at import (ImportError),
            # at native library bind (OSError), or at render. All three mean
            # the same thing here -- try the next one.
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    raise PDFBackendUnavailable(
        "no HTML -> PDF backend worked. The HTML report was still written.\n"
        + "\n".join(f"  - {f}" for f in failures)
        + "\n\nFix either one:\n"
          "  weasyprint -- needs native GTK libraries pip cannot install:\n"
          "      Windows: install the GTK3 runtime\n"
          "      Linux:   apt install libpango-1.0-0 libpangoft2-1.0-0\n"
          "      macOS:   brew install pango\n"
          "  chromium   -- pip install playwright && playwright install chromium\n"
          "      (already required by backend/render, so usually the easier one)"
    )


__all__ = ["html_to_pdf", "available_backends", "PDFBackendUnavailable", "BACKENDS"]
