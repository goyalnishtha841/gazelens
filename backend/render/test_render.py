"""
test_render.py

Run with: python3 test_render.py   (from inside backend/render)

Captures a hand-written local HTML page over file://, so the whole suite runs
offline and deterministically -- a test that depends on a live website fails
whenever that site redesigns, and teaches everyone to ignore it.

The fixture is built to exercise the decisions that matter: a real button, a
CTA-classed link, a footer link, a nav landmark, an image, headings, form
fields, a decorative icon too small to attribute, a full-page wrapper too
large to attribute, and an element scrolled off the bottom.

Same shape as backend/agents/test_agents.py.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render.capture import (                                    # noqa: E402
    capture_page,
    render_available,
)
from render.classify import (                                   # noqa: E402
    TYPE_CTA,
    TYPE_IMAGE,
    TYPE_NAV,
    TYPE_NON_INTERACTIVE,
    TYPE_TEXT,
    classify_type,
    element_id_for,
)

passed = 0
failed = 0
skipped = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}")
        failed += 1


def skip(label, why):
    global skipped
    print(f"  SKIP  {label} ({why})")
    skipped += 1


FIXTURE = """<!doctype html>
<html><head><title>Checkout Demo</title></head>
<body style="margin:0;font-family:sans-serif;width:1280px">
  <!-- <main>, not <div>: the collector only queries semantic/interactive
       tags, so a plain div would never be detected and the "too large" filter
       would go untested while the assertion still passed. -->
  <main id="page_wrapper" style="position:absolute;left:0;top:0;width:1280px;height:700px"></main>
  <nav id="main_nav" style="position:absolute;left:0;top:0;width:1280px;height:60px;background:#eee">
    <a href="/home" style="display:inline-block;width:120px;height:40px">Home</a>
  </nav>
  <img id="hero_image" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="
       style="position:absolute;left:40px;top:90px;width:520px;height:380px">
  <h1 id="product_title" style="position:absolute;left:600px;top:100px;width:600px;height:70px">
    Wireless Headphones</h1>
  <p id="product_blurb" style="position:absolute;left:600px;top:190px;width:600px;height:90px">
    Noise cancelling, 30 hour battery.</p>
  <button id="checkout_button"
          style="position:absolute;left:600px;top:310px;width:280px;height:64px">
    Buy now</button>
  <a id="wishlist_link" class="btn btn-secondary"
     style="position:absolute;left:900px;top:310px;width:220px;height:64px;display:block">
     Add to wishlist</a>
  <input id="promo_code" name="promo" type="text"
         style="position:absolute;left:600px;top:400px;width:280px;height:44px">
  <!-- a real <button>, so it IS collected and the size filter is what drops
       it -- a decorative 10x10 control gaze can't be attributed to at 40px
       of estimation error. -->
  <button id="tiny_icon" style="position:absolute;left:1240px;top:10px;width:10px;height:10px">*</button>
  <a id="privacy_link" href="/privacy"
     style="position:absolute;left:40px;top:620px;width:180px;height:30px;display:block">
     Privacy policy</a>
  <button id="way_below" style="position:absolute;left:40px;top:2400px;width:200px;height:50px">
    Offscreen</button>
</body></html>
"""


print("classify -- unambiguous tags")
check("<button> is a CTA", classify_type({"tag": "button"})[0] == TYPE_CTA)
check("input[type=submit] is a CTA",
      classify_type({"tag": "input", "input_type": "submit"})[0] == TYPE_CTA)
check("<nav> is nav", classify_type({"tag": "nav"})[0] == TYPE_NAV)
check("<img> is image", classify_type({"tag": "img"})[0] == TYPE_IMAGE)
check("<h1> is text", classify_type({"tag": "h1"})[0] == TYPE_TEXT)
check("a text input is text, not a CTA",
      classify_type({"tag": "input", "input_type": "text"})[0] == TYPE_TEXT)
check("unambiguous tags are high confidence",
      classify_type({"tag": "button"})[1] >= 0.9)

print("\nclassify -- links are the ambiguous case, and say so")
cta_link = classify_type({"tag": "a", "classes": ["btn", "btn-primary"]})
plain_link = classify_type({"tag": "a", "classes": ["footer-link"]})
nav_link = classify_type({"tag": "a", "classes": [], "in_nav": True})
check("a link with a CTA-ish class reads as a CTA", cta_link[0] == TYPE_CTA)
check("...but at lower confidence than a <button>",
      cta_link[1] < classify_type({"tag": "button"})[1])
check("a plain link is not promoted to CTA", plain_link[0] != TYPE_CTA)
check("a link inside a nav reads as nav", nav_link[0] == TYPE_NAV)
check("the ambiguity is recorded in the reason",
      "could be either" in plain_link[2] or "no CTA signal" in plain_link[2])

print("\nclassify -- the default is the inert label")
unknown = classify_type({"tag": "div", "classes": []})
check("an unlabelled div is non-interactive, not CTA",
      unknown[0] == TYPE_NON_INTERACTIVE)
check("and is marked low confidence", unknown[1] < 0.5)

print("\nclassify -- element ids prefer the author's own naming")
check("uses the DOM id", element_id_for({"tag": "button", "dom_id": "checkout"}, set())
      == "checkout")
check("falls back to aria-label",
      element_id_for({"tag": "button", "aria_label": "Add to cart"}, set())
      == "add_to_cart")
check("falls back to tag + text",
      element_id_for({"tag": "button", "text": "Buy now"}, set()) == "button_buy_now")
check("never collides",
      element_id_for({"tag": "button", "dom_id": "checkout"}, {"checkout"}) != "checkout")

# Ids are printed verbatim in the report and on the heatmap, so a footer whose
# text is its entire link list must not become a 60-character identifier.
long_id = element_id_for(
    {"tag": "footer",
     "text": "Domain Names Root Zone Registry INT Registry Reserved Domains"},
    set())
check("a long text run is cut to a readable id", len(long_id) <= 34)
check("...at a word boundary, not mid-word", not long_id.endswith("_"))
print(f"        long-text id -> {long_id!r}")

# ----------------------------------------------------------------------
print("\ncapture -- a real page through headless Chromium")

if not render_available():
    skip("capture end-to-end", "playwright not installed")
else:
    tmp = Path(tempfile.mkdtemp(prefix="gazelens_render_test_"))
    page = tmp / "fixture.html"
    page.write_text(FIXTURE, encoding="utf-8")
    shot = tmp / "shot.png"

    result = capture_page(page.as_uri(), viewport=(1280, 720), scope="viewport",
                          screenshot_path=shot)

    check("page title read", result.title == "Checkout Demo")
    check("screenshot written", shot.exists() and shot.stat().st_size > 0)
    check("elements detected", result.detected > 0)
    check("elements kept", result.kept > 0)
    print(f"        detected {result.detected}, kept {result.kept}; "
          f"dropped {result.too_small_dropped} small / "
          f"{result.too_large_dropped} large / {result.below_fold_dropped} offscreen")

    layout = result.layout
    check("the button was found", "checkout_button" in layout)
    check("...and typed as a CTA", layout["checkout_button"]["type"] == TYPE_CTA)
    check("...and marked high importance (above the fold)",
          layout["checkout_button"]["importance"] == "high")

    check("the nav was found and typed", layout.get("main_nav", {}).get("type") == TYPE_NAV)
    check("the hero image was typed", layout.get("hero_image", {}).get("type") == TYPE_IMAGE)
    check("the heading was typed as text",
          layout.get("product_title", {}).get("type") == TYPE_TEXT)
    check("the btn-classed link was promoted to CTA",
          layout.get("wishlist_link", {}).get("type") == TYPE_CTA)
    check("the text input is text, not a CTA",
          layout.get("promo_code", {}).get("type") == TYPE_TEXT)

    print("\ncapture -- filtering")
    check("the 10x10 icon was dropped as too small", "tiny_icon" not in layout)
    check("the full-page wrapper was dropped as too large", "page_wrapper" not in layout)
    check("the element at y=2400 was dropped as offscreen", "way_below" not in layout)
    check("small/large/offscreen drops were all counted",
          result.too_small_dropped > 0 and result.too_large_dropped > 0
          and result.below_fold_dropped > 0)

    print("\ncapture -- coordinates are viewport-normalised and clipped")
    for eid, spec in layout.items():
        x, y, w, h = spec["bbox"]
        ok = (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
              and w > 0 and h > 0 and x + w <= 1.0001 and y + h <= 1.0001)
        if not ok:
            check(f"{eid} bbox in range", False)
            break
    else:
        check("every bbox is inside the viewport", True)

    bx, by, bw, bh = layout["checkout_button"]["bbox"]
    check("button x matches its CSS position (600/1280)", abs(bx - 600 / 1280) < 0.002)
    check("button y matches its CSS position (310/720)", abs(by - 310 / 720) < 0.002)
    check("button width matches (280/1280)", abs(bw - 280 / 1280) < 0.002)

    print("\ncapture -- confidence is reported, not hidden")
    check("every kept element has classification detail",
          set(result.classification) == set(layout))
    check("each records why it was classified that way",
          all(c["classified_by"] for c in result.classification.values()))
    print(f"        low-confidence fraction: {result.low_confidence_fraction:.0%}")
    check("low_confidence_fraction is a proportion",
          0.0 <= result.low_confidence_fraction <= 1.0)

    print("\ncapture -- output feeds attribution unchanged")
    from attribution import build_ui_config

    ui_config = build_ui_config(ui_page="captured_page", elements=layout)
    check("attribution accepts the layout as-is",
          set(ui_config.element_ids) == set(layout))
    check("and can render it for the heatmap",
          len(ui_config.layout_for_heatmap()) == len(layout))

    print("\ncapture -- document scope covers a page taller than one screen")
    # The failure this scope exists to prevent: capture the first screen of a
    # long page and every element below it is simply absent from the report,
    # indistinguishable from "nobody looked at them".
    tall = tmp / "tall.html"
    tall.write_text("""<!doctype html><html><head><title>Tall</title></head>
      <body style="margin:0;width:1280px;height:2880px">
        <button id="top_cta" style="position:absolute;left:40px;top:100px;width:240px;height:60px">Top</button>
        <img id="mid_image" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="
             style="position:absolute;left:40px;top:1200px;width:400px;height:300px">
        <button id="bottom_cta" style="position:absolute;left:40px;top:2600px;width:240px;height:60px">Bottom</button>
      </body></html>""", encoding="utf-8")

    vp = capture_page(tall.as_uri(), viewport=(1280, 720), scope="viewport")
    doc = capture_page(tall.as_uri(), viewport=(1280, 720), scope="document")

    check("viewport scope sees only the first screen", "top_cta" in vp.layout
          and "bottom_cta" not in vp.layout)
    check("...and warns that the page is taller than it captured",
          any("viewports tall" in w for w in vp.warnings))
    check("document scope reports the real page height", doc.page_screens >= 3.9)
    check("document scope keeps elements below the fold",
          {"top_cta", "mid_image", "bottom_cta"} <= set(doc.layout))
    print(f"        viewport scope kept {vp.kept}; document scope kept "
          f"{doc.kept} across {doc.page_screens} screens")

    top_y = doc.layout["top_cta"]["bbox"][1]
    bottom_y = doc.layout["bottom_cta"]["bbox"][1]
    check("document-space y is a fraction of the whole page, not the screen",
          abs(top_y - 100 / 2880) < 0.01 and abs(bottom_y - 2600 / 2880) < 0.01)
    check("the bottom element sits near the end of the document",
          bottom_y > 0.85)
    check("every document-space bbox is still within [0,1]",
          all(0 <= b["bbox"][1] <= 1 and b["bbox"][1] + b["bbox"][3] <= 1.0001
              for b in doc.layout.values()))

    print("\ncapture -- refuses what it can't handle")
    try:
        capture_page("ftp://example.com/x")
        check("non-http scheme rejected", False)
    except ValueError:
        check("non-http scheme rejected", True)

    empty = tmp / "empty.html"
    empty.write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    blank = capture_page(empty.as_uri(), viewport=(1280, 720))
    check("an empty page yields no elements rather than raising",
          blank.kept == 0)
    check("...and warns why", any("no attributable elements" in w
                                  for w in blank.warnings))

    import shutil

    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'=' * 40}\n{passed} passed, {failed} failed, {skipped} skipped\n{'=' * 40}")

if failed:
    raise SystemExit(1)
