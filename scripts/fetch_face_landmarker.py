"""
fetch_face_landmarker.py

Downloads the MediaPipe face landmarker bundle that backend/cv needs for
live capture.

    python scripts/fetch_face_landmarker.py

~3.7MB, lands at models/face_landmarker.task. Gitignored, same as
models/*.pt -- model assets stay out of the repo.

Why this exists at all: MediaPipe's Tasks API (the only one still shipped --
`mp.solutions` has been removed) loads its model from an explicit file rather
than bundling it in the wheel. Without this asset, landmarking raises
LandmarkerUnavailable with a message pointing here.
"""

import urllib.request
from pathlib import Path

URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DEST = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"

# The published float16 bundle is ~3.7MB. Anything much smaller is almost
# certainly an error page saved with a .task extension, which would fail
# later and much less clearly.
MIN_PLAUSIBLE_BYTES = 1_000_000


def main() -> int:
    if DEST.exists():
        print(f"Already present: {DEST} ({DEST.stat().st_size:,} bytes)")
        return 0

    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL}\n        -> {DEST}")

    tmp = DEST.with_suffix(".task.partial")
    try:
        urllib.request.urlretrieve(URL, tmp)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        print(f"Download failed: {exc}")
        return 1

    size = tmp.stat().st_size
    if size < MIN_PLAUSIBLE_BYTES:
        tmp.unlink(missing_ok=True)
        print(f"Downloaded file is only {size:,} bytes -- that isn't the model. Aborting.")
        return 1

    # Rename only after the size check, so a failed run never leaves a
    # corrupt file that looks valid to the landmarker.
    tmp.replace(DEST)
    print(f"Done: {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
