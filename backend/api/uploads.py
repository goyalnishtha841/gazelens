"""
uploads.py

mode="image": test a screenshot or design mock-up the user uploads, with
element boxes they draw on it by hand.

An image has no DOM, so nothing can be detected from it -- the user says
where each element is and what it is. The result is shaped exactly like a
URL capture (backend/render): a full-page screenshot on disk, a
document-scope layout normalised to the whole image, and the capture_meta
keys pipeline.to_document_space and pipeline.page_screenshot read. From
there on an uploaded image is indistinguishable from a captured website:
the live stage scrolls it, gaze is translated by scroll offset, and the
report's heatmap is drawn over the real image.

Unlike a URL capture every box is authored, not guessed, so
low_confidence_fraction is 0 and the report says the boxes were drawn by
the tester.
"""

import base64
import binascii
import io
import re
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

# The image is decoded, checked and re-encoded as PNG before it is stored:
# nothing the client sent is written to disk byte for byte.
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_WIDTH = 320
MAX_WIDTH = 4000
MAX_HEIGHT = 20000
MAX_PIXELS = 40_000_000

# The stage the image is shown in during the test keeps a 16:9 window, the
# same as a captured website (render's default 1280x720 viewport); a taller
# image scrolls inside it. A shorter one is shown whole.
STAGE_ASPECT = 9 / 16

# Below this an element is too small for webcam gaze to say anything about.
MIN_BOX_PX = 12


class UploadError(ValueError):
    """The upload can't be used; the message is shown to the user."""


def decode_image(data: str) -> Tuple[bytes, Tuple[int, int]]:
    """base64 (raw or a data: URL) -> (PNG bytes, (width, height))."""
    from PIL import Image, UnidentifiedImageError

    if "," in data[:100] and data.startswith("data:"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UploadError("the image couldn't be read (invalid base64)") from exc
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadError(f"the image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            width, height = probe.size
        if fmt not in ALLOWED_FORMATS:
            raise UploadError("upload a PNG, JPEG or WebP image")
        if width * height > MAX_PIXELS:
            raise UploadError("the image has too many pixels")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="PNG", optimize=True)
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UploadError("the file isn't a readable image") from exc

    if width < MIN_WIDTH:
        raise UploadError(f"the image must be at least {MIN_WIDTH} px wide")
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise UploadError(f"the image must be at most {MAX_WIDTH} px wide "
                          f"and {MAX_HEIGHT} px tall")
    return out.getvalue(), (width, height)


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return (s or "element")[:40]


def build_layout(elements: List[dict], size: Tuple[int, int]) -> Dict[str, dict]:
    """Drawn boxes -> a layout in the attribution format, with unique ids."""
    width, height = size
    layout: Dict[str, dict] = {}
    for el in elements:
        x, y, w, h = el["bbox"]
        if w * width < MIN_BOX_PX or h * height < MIN_BOX_PX:
            raise UploadError(f"the box for {el['label']!r} is too small to measure; "
                              f"draw it at least {MIN_BOX_PX} px each way")
        base = _slug(el["label"])
        eid, n = base, 2
        while eid in layout:
            eid, n = f"{base}_{n}", n + 1
        layout[eid] = {
            "bbox": [round(x, 5), round(y, 5), round(w, 5), round(h, 5)],
            "type": el["type"],
            "importance": el["importance"],
            "label": el["label"],
        }
    return layout


def save_upload(png: bytes, size: Tuple[int, int], elements: List[dict],
                data_dir: Path, title: str) -> Tuple[dict, dict]:
    """Store the image; return (layout, capture_meta) for the session row."""
    layout = build_layout(elements, size)
    shots = Path(data_dir) / "captures"
    shots.mkdir(parents=True, exist_ok=True)
    path = shots / f"upload_{uuid.uuid4().hex}.png"
    path.write_bytes(png)

    width, height = size
    view_h = min(height, round(width * STAGE_ASPECT))
    meta = {
        "source": "upload",
        "title": title,
        "screenshot_path": str(path),
        "detected": len(layout),
        "kept": len(layout),
        "low_confidence_fraction": 0.0,
        "warnings": [],
        # Same three keys a URL capture carries; pipeline.to_document_space
        # needs them to line gaze up with boxes on a scrolled image.
        "scope": "document",
        "viewport": [width, view_h],
        "document_size": [width, height],
        "page_screens": round(height / view_h, 2),
    }
    return layout, meta


__all__ = ["UploadError", "decode_image", "build_layout", "save_upload",
           "MAX_UPLOAD_BYTES", "STAGE_ASPECT"]
