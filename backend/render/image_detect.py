"""
image_detect.py

Find the elements on an uploaded screenshot automatically.

A captured website has a DOM to read element boxes from (capture.py); an
uploaded image has only pixels. This module proposes the same kind of layout
from pixels alone, in two passes:

  1. Text: an OCR model (RapidOCR, ONNX, CPU) finds every line of text with
     its box and reads it. That gives names ("Add to cart") as well as
     positions.
  2. Shapes: OpenCV separates the page background from everything drawn on
     it, then looks for rectangles -- filled blocks (buttons, photos, cards)
     and outlined ones (input fields).

Then rules decide what each thing is, the same vocabulary the agents use:

  * CTA (button)   a filled shape holding one short line of text, sized like
                   a button
  * text (field)   an outlined, wide, short rectangle; named from its
                   placeholder text if it has one
  * nav            a row of short words across the top of the page
  * image          a large shape with lots of colour and little text
  * text           remaining lines, merged into headings and paragraphs

and importance follows the same geometry render/classify.py uses for live
pages: a button in the first screen is "high", a heading or large image
there is "medium", the rest "low".

These are guesses from pixels, and they are returned as SUGGESTIONS: the web
app shows them as editable boxes the tester checks, renames, deletes or adds
to before the test starts. Each carries a confidence and a reason, so the
tester can see why it was proposed.
"""

from dataclasses import dataclass, field
from typing import List

import numpy as np

# Work on at most this width; boxes are returned as fractions, so scale is free.
WORK_WIDTH = 1400
# First screen of the page, as a fraction of width (a 16:9 window, the same
# window the web app shows an upload in) -- "above the fold".
FOLD_ASPECT = 9 / 16
MAX_ELEMENTS = 40
MIN_SIDE_PX = 12

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(self.w, 0) * max(self.h, 0)

    def inter(self, o: "Box") -> float:
        w = min(self.x1, o.x1) - max(self.x0, o.x0)
        h = min(self.y1, o.y1) - max(self.y0, o.y0)
        return max(w, 0) * max(h, 0)

    def contains(self, o: "Box", slack: float = 0.9) -> bool:
        return o.area > 0 and self.inter(o) / o.area >= slack

    def union(self, o: "Box") -> "Box":
        return Box(min(self.x0, o.x0), min(self.y0, o.y0), max(self.x1, o.x1), max(self.y1, o.y1))


@dataclass
class TextLine:
    box: Box
    text: str
    conf: float


@dataclass
class Detected:
    box: Box
    type: str
    importance: str
    label: str
    confidence: float
    why: str
    text: str = ""
    children: List[TextLine] = field(default_factory=list)


# ---------------------------------------------------------------------- pixels


def _background(img: np.ndarray) -> np.ndarray:
    """The page colour: the most common colour along the image border."""
    border = np.concatenate([img[0], img[-1], img[:, 0], img[:, -1]]).astype(int)
    q = (border // 8) * 8
    vals, counts = np.unique(q, axis=0, return_counts=True)
    return vals[counts.argmax()].astype(float) + 4


def _rects(img: np.ndarray, bg: np.ndarray) -> List[Box]:
    """Every box drawn on the page: solid shapes and outlined ones."""
    import cv2

    h, w = img.shape[:2]
    found: List[Box] = []

    def keep(x, y, bw, bh):
        if bw >= MIN_SIDE_PX and bh >= MIN_SIDE_PX and bw * bh < 0.85 * w * h:
            found.append(Box(x, y, x + bw, y + bh))

    # Solid shapes: regions that differ from the page colour.
    diff = np.abs(img.astype(float) - bg).max(axis=2)
    fg = cv2.morphologyEx((diff > 22).astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    for c in cv2.findContours(fg, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(c)
        if cv2.contourArea(c) > 0.8 * bw * bh:
            keep(x, y, bw, bh)

    # Outlined shapes: rectangles traced by edges, even faint ones (a light
    # grey input border on a white card).
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    edges = cv2.dilate(cv2.Canny(gray, 8, 24), np.ones((3, 3), np.uint8))
    for c in cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < 24 or bh < 16:
            continue
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if 4 <= len(approx) <= 12 and cv2.contourArea(c) > 0.75 * bw * bh:
            keep(x, y, bw, bh)

    # The same box is usually found more than once; keep one of each.
    found.sort(key=lambda b: b.area)
    out: List[Box] = []
    for b in found:
        if not any(b.inter(o) / (b.area + o.area - b.inter(o)) > 0.8 for o in out):
            out.append(b)
    return out


def _median_colour(img: np.ndarray, b: Box) -> np.ndarray:
    crop = img[int(b.y0):int(b.y1), int(b.x0):int(b.x1)]
    return np.median(crop.reshape(-1, 3), axis=0) if crop.size else np.zeros(3)


def _ring_colour(img: np.ndarray, b: Box, pad: int = 4) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0 = max(int(b.x0) - pad, 0), max(int(b.y0) - pad, 0)
    x1, y1 = min(int(b.x1) + pad, w), min(int(b.y1) + pad, h)
    parts = [img[y0:int(b.y0), x0:x1], img[int(b.y1):y1, x0:x1],
             img[y0:y1, x0:int(b.x0)], img[y0:y1, int(b.x1):x1]]
    px = np.concatenate([p.reshape(-1, 3) for p in parts if p.size]) if any(p.size for p in parts) else None
    return np.median(px, axis=0) if px is not None else np.zeros(3)


def _ink(img: np.ndarray, b: Box) -> float:
    """How dark a text line's darkest strokes are (0 black .. 255 white)."""
    crop = img[int(b.y0):int(b.y1), int(b.x0):int(b.x1)]
    if crop.size == 0:
        return 0.0
    lum = crop.reshape(-1, 3).astype(float).mean(axis=1)
    return float(np.percentile(lum, 5))


def _colourfulness(img: np.ndarray, b: Box) -> float:
    crop = img[int(b.y0):int(b.y1), int(b.x0):int(b.x1)]
    if crop.size == 0:
        return 0.0
    return float(crop.reshape(-1, 3).astype(float).std(axis=0).mean())


# ---------------------------------------------------------------------- text


def _read_text(img: np.ndarray) -> List[TextLine]:
    # Read at the image's own size. Enlarging first (1.5x, 2x) fixed a few
    # letters in tiny bold labels but merged words ("Wellnevershare..."),
    # which reads worse in a report; the tester can rename any box anyway.
    result, _ = _get_ocr()(img)
    lines = []
    for quad, text, conf in result or []:
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        text = " ".join(str(text).split())
        if text and float(conf) >= 0.5:
            lines.append(TextLine(Box(min(xs), min(ys), max(xs), max(ys)), text, float(conf)))
    return lines


def _paragraphs(lines: List[TextLine]) -> List[List[TextLine]]:
    """Merge lines stacked closely with similar height and left edge."""
    lines = sorted(lines, key=lambda t: (t.box.y0, t.box.x0))
    groups: List[List[TextLine]] = []
    for ln in lines:
        for g in groups:
            last = g[-1]
            gap = ln.box.y0 - last.box.y1
            same_size = abs(ln.box.h - last.box.h) <= 0.35 * max(ln.box.h, last.box.h)
            aligned = abs(ln.box.x0 - g[0].box.x0) <= 1.2 * last.box.h
            if 0 <= gap <= 0.9 * last.box.h and same_size and aligned:
                g.append(ln)
                break
        else:
            groups.append([ln])
    return groups


def _short(text: str, n: int = 40) -> str:
    text = text.strip(" .:|•·-")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _nav_row(lines: List[TextLine], median_h: float) -> bool:
    """Three or more short words side by side on one line."""
    if len(lines) < 3 or any(len(t.text.split()) > 3 for t in lines):
        return False
    ys = [t.box.y0 for t in lines]
    return max(ys) - min(ys) < 0.8 * median_h


# ---------------------------------------------------------------------- main


def _classify_box(img, box: Box, inside: List[TextLine], W, H, fold, median_h):
    """What a box is, from what is inside it. None = not an element itself."""
    filled = float(np.abs(_median_colour(img, box) - _ring_colour(img, box)).max()) > 40
    text_area = sum(t.box.inter(box) for t in inside)
    words = sum(len(t.text.split()) for t in inside)
    above = box.y0 < fold

    # A bar of short words across the top: navigation.
    if box.w > 0.4 * W and box.y0 < 0.25 * fold and box.h < 0.2 * fold and _nav_row(inside, median_h):
        words_ = ", ".join(t.text for t in sorted(inside, key=lambda t: t.box.x0)[:3])
        return "nav", "low", _short(f"Menu ({words_}…)", 48), 0.75, "a bar of short words across the top"

    # A solid coloured shape holding one short label: a button.
    if filled and len(inside) == 1 and words <= 5 and box.w <= 0.7 * W \
            and box.h <= 6 * inside[0].box.h and text_area > 0.03 * box.area:
        return "CTA", "high" if above else "medium", _short(inside[0].text), 0.8, \
            "a solid coloured shape around a short label"

    # A light, wide, short box with a small label/placeholder: an input field.
    light = float(_median_colour(img, box).mean()) > 200
    if not filled and light and box.w > 3 * box.h and box.h <= 6 * median_h and len(inside) <= 2:
        first = min(inside, key=lambda t: t.box.y0) if inside else None
        # a field's text starts at its left edge; centred text in a box is a
        # banner or a placeholder graphic, not an input
        left_aligned = first is not None and first.box.x0 - box.x0 < 0.12 * box.w
        second = max(inside, key=lambda t: t.box.y0) if len(inside) == 2 else None
        if second is not None and left_aligned and first.box.h <= 1.05 * second.box.h:
            # small label above its value (a heading above a line is not this)
            return "text", "medium", _short(first.text) + " field", 0.7, \
                "a light box with a small label above a value, like a form field"
        if left_aligned and len(inside) == 1 and _ink(img, inside[0].box) > 110:   # grey: placeholder
            return "text", "medium", _short(inside[0].text) + " field", 0.6, \
                "a light box with grey placeholder text, like a form field"

    # A big area with almost no text: an image (or a placeholder for one).
    if box.area > 0.015 * W * H and text_area < 0.08 * box.area and words <= 4:
        name = _short(inside[0].text) if len(inside) == 1 else "Image"
        imp = "medium" if above and box.area > 0.06 * W * H else "low"
        why = "a large area with little or no text" + \
            (" and lots of colour" if _colourfulness(img, box) > 28 else "")
        return "image", imp, name, 0.6, why

    if not inside:
        return None
    first = min(inside, key=lambda t: t.box.y0)
    heading = first.box.h >= 1.35 * median_h
    imp = "medium" if heading and above else "low"
    return "text", imp, _short(" ".join(t.text for t in sorted(inside, key=lambda t: (t.box.y0, t.box.x0)))), \
        0.6, "large text, like a heading" if heading else "a block of text"


def detect_elements(img_bgr: np.ndarray) -> List[dict]:
    """Image (BGR array) -> suggested elements, boxes as fractions [x, y, w, h]."""
    H0, W0 = img_bgr.shape[:2]
    scale = min(1.0, WORK_WIDTH / float(W0))
    if scale < 1.0:
        import cv2
        img = cv2.resize(img_bgr, (int(W0 * scale), int(H0 * scale)), interpolation=cv2.INTER_AREA)
    else:
        img = img_bgr
    H, W = img.shape[:2]
    fold = W * FOLD_ASPECT

    rects = _rects(img, _background(img))
    # Text is read from the full-size image (shrinking it first makes the
    # OCR drop spaces: "New test" -> "Newtest"), then scaled to match.
    lines = [TextLine(Box(t.box.x0 * scale, t.box.y0 * scale, t.box.x1 * scale, t.box.y1 * scale),
                      t.text, t.conf) for t in _read_text(img_bgr)]
    median_h = float(np.median([t.box.h for t in lines])) if lines else 16.0

    def lines_in(r: Box, slack: float = 0.6) -> List[TextLine]:
        return [t for t in lines if r.contains(t.box, slack)]

    def children(r: Box) -> List[Box]:
        return [o for o in rects if o is not r and r.contains(o, 0.95) and o.area < 0.9 * r.area]

    found: List[Detected] = []
    taken: List[Box] = []          # boxes already reported
    claimed: List[Box] = []        # areas whose insides are already explained
    nav_bars: List[Box] = []

    # Pass 1, largest first: containers that are really ONE thing.
    for r in sorted(rects, key=lambda b: -b.area):
        if any(c.contains(r, 0.9) for c in claimed) or not children(r):
            continue
        inside = lines_in(r)
        # A bar of short words across the top (each link may sit in its own
        # pill): one navigation element. Buttons inside it are kept.
        if r.w > 0.4 * W and r.y0 < 0.25 * fold and r.h < 0.2 * fold and _nav_row(inside, median_h):
            words = ", ".join(t.text for t in sorted(inside, key=lambda t: t.box.x0)[:3])
            found.append(Detected(r, "nav", "low", _short(f"Menu ({words}…)", 48), 0.75,
                                  "a bar of short words across the top"))
            taken.append(r)
            nav_bars.append(r)
            continue
        # A picture made of many small parts (a screenshot, a chart, a page
        # preview) with little readable text: one image, not its parts.
        text_area = sum(t.box.inter(r) for t in inside)
        parts = children(r)
        if (r.area > 0.015 * W * H and text_area < 0.1 * r.area and len(parts) >= 2
                and max(p.area for p in parts) < 0.6 * r.area):
            label = _short(inside[0].text) if len(inside) == 1 else "Image"
            found.append(Detected(r, "image", "medium" if r.y0 < fold and r.area > 0.06 * W * H else "low",
                                  label, 0.55, "a picture made of many small parts with little text"))
            taken.append(r)
            claimed.append(r)

    # Pass 2, smallest first: the boxes that are elements themselves.
    owned = set()
    for r in sorted(rects, key=lambda b: b.area):
        if any(c.contains(r, 0.9) for c in claimed) or any(t.contains(r, 0.9) and t not in nav_bars for t in taken):
            continue
        if children(r) and not any(r is n for n in nav_bars):
            continue                  # a card or section: its parts are reported instead
        if any(r is n for n in nav_bars):
            continue
        inside = [t for t in lines_in(r) if id(t) not in owned]
        kind = _classify_box(img, r, inside, W, H, fold, median_h)
        if kind is None:
            continue
        typ, imp, label, conf, why = kind
        if any(n.contains(r, 0.9) for n in nav_bars) and typ != "CTA":
            continue                  # a link inside the menu: the menu covers it
        found.append(Detected(r, typ, imp, label, conf, why))
        taken.append(r)
        owned.update(id(t) for t in inside)

    # Everything a reported box or the menu already covers is explained.
    covered = [d.box for d in found]
    owner = {i for i, t in enumerate(lines)
             if id(t) in owned or any(c.contains(t.box, 0.6) for c in covered)}

    # Text that sits on the page itself, outside any box.
    loose = [t for i, t in enumerate(lines) if i not in owner]
    for g in _paragraphs(loose):
        box = g[0].box
        for t in g[1:]:
            box = box.union(t.box)
        heading = len(g) <= 2 and g[0].box.h >= 1.35 * median_h
        found.append(Detected(box, "text", "medium" if heading and box.y0 < fold else "low",
                              _short(" ".join(t.text for t in g)),
                              round(float(np.mean([t.conf for t in g])) * 0.8, 2),
                              "large text, like a heading" if heading else "a block of text"))

    # A row of short items across the top with no visible bar around them
    # (a faint bar on a dark theme): one navigation element, buttons kept.
    if not nav_bars:
        top = [d for d in found if d.type == "text" and d.box.y1 < 0.2 * fold
               and len(d.label.split()) <= 3]
        rows: List[List[Detected]] = []
        for d in sorted(top, key=lambda d: d.box.y0):
            cy = (d.box.y0 + d.box.y1) / 2
            for row in rows:
                if abs((row[0].box.y0 + row[0].box.y1) / 2 - cy) < 0.8 * median_h:
                    row.append(d)
                    break
            else:
                rows.append([d])
        for row in rows:
            if len(row) >= 3:
                row.sort(key=lambda d: d.box.x0)
                box = row[0].box
                for d in row[1:]:
                    box = box.union(d.box)
                pad = 0.4 * median_h
                words = ", ".join(d.label for d in row[:3])
                found = [d for d in found if d not in row]
                found.append(Detected(Box(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad), "nav", "low",
                                      _short(f"Menu ({words}…)", 48), 0.7, "a row of short words across the top"))

    # Most useful first, then cap.
    rank = {"high": 0, "medium": 1, "low": 2}
    found = [d for d in found if d.box.w >= MIN_SIDE_PX and d.box.h >= MIN_SIDE_PX]
    found.sort(key=lambda d: (rank[d.importance], -d.box.area))
    found = found[:MAX_ELEMENTS]
    found.sort(key=lambda d: (d.box.y0, d.box.x0))

    # Every box gets its own name.
    seen: dict = {}
    out = []
    for d in found:
        n = seen.get(d.label, 0) + 1
        seen[d.label] = n
        label = d.label if n == 1 and d.label != "Image" else f"{d.label} {n}"
        x0, y0 = max(d.box.x0, 0), max(d.box.y0, 0)
        x1, y1 = min(d.box.x1, W), min(d.box.y1, H)
        out.append({
            "label": label[:60],
            "type": d.type,
            "importance": d.importance,
            "bbox": [round(x0 / W, 5), round(y0 / H, 5), round((x1 - x0) / W, 5), round((y1 - y0) / H, 5)],
            "confidence": d.confidence,
            "why": d.why,
        })
    return out


def detect_from_png(png: bytes) -> List[dict]:
    import cv2
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    return detect_elements(img)


__all__ = ["detect_elements", "detect_from_png"]
