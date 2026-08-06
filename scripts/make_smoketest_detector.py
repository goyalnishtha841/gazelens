"""
make_smoketest_detector.py

Builds models/pupil_smoketest.pt -- a small pupil detector trained on
SYNTHETIC eye images, so the live pipeline can be run end to end on a machine
that doesn't have the real weights.

    python scripts/make_smoketest_detector.py

=============================================================================
THIS IS NOT THE BENCHMARKED DETECTOR. DO NOT REPORT NUMBERS FROM IT.
=============================================================================

The real detector is models/pupil_yolo_final.pt -- YOLOv8n trained on LPW
(130,856 images), the model behind the precision/recall/mAP table in the
README. It is gitignored and kept in Drive. Nothing here replaces it.

What this exists for: models/*.pt is gitignored, so a fresh clone cannot run
backend/cv at all -- webcam_demo.py won't start and test_cv.py skips its
end-to-end check. That leaves the integration between MediaPipe landmarking,
cropping, YOLO inference and coordinate mapping unexercised on any machine
without Drive access. This produces weights good enough to prove that
plumbing works. It is a smoke test, not a measurement.

Trained on drawn ellipses, so it detects dark blobs on light backgrounds. It
will be mediocre on real eyes and worse on some faces than others -- that is
expected and is exactly why it must not appear in any result.
"""

import argparse
import random
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "models"
BASE_WEIGHTS = MODELS / "yolov8n.pt"
OUTPUT = MODELS / "pupil_smoketest.pt"

IMG = 96                    # training image size, square


def _draw_eye(rng, size=IMG):
    """One synthetic eye crop + the pupil's YOLO bbox.

    Rough imitation of what backend/cv actually feeds the detector: a tight
    crop around one eye, so the model sees the same framing at inference.
    """
    import numpy as np

    # skin/sclera base with a lighting gradient, so the model can't just
    # learn "darkest pixel" against a flat field
    base = rng.randint(150, 235)
    img = np.full((size, size, 3), base, dtype=np.int16)
    gx = np.linspace(rng.uniform(-40, 0), rng.uniform(0, 40), size)
    img += gx[None, :, None].astype(np.int16)
    img += rng.randint(-12, 12)

    yy, xx = np.mgrid[0:size, 0:size]

    # eye opening (lighter, almond), keeps the pupil from sitting on skin
    ecx, ecy = size / 2 + rng.uniform(-6, 6), size / 2 + rng.uniform(-5, 5)
    erx, ery = rng.uniform(size * 0.34, size * 0.46), rng.uniform(size * 0.18, size * 0.28)
    eye = ((xx - ecx) / erx) ** 2 + ((yy - ecy) / ery) ** 2 <= 1.0
    img[eye] = np.clip(img[eye] + rng.randint(10, 40), 0, 255)

    # iris, then pupil inside it
    irx = rng.uniform(size * 0.13, size * 0.20)
    pcx = ecx + rng.uniform(-erx * 0.42, erx * 0.42)
    pcy = ecy + rng.uniform(-ery * 0.30, ery * 0.30)
    iris = ((xx - pcx) ** 2 + (yy - pcy) ** 2) <= irx ** 2
    img[iris] = rng.randint(60, 120)

    prx = irx * rng.uniform(0.42, 0.62)
    pupil = ((xx - pcx) ** 2 + (yy - pcy) ** 2) <= prx ** 2
    img[pupil] = rng.randint(8, 42)

    # specular highlight -- real pupils almost always have one, and it's the
    # main thing that breaks naive "darkest region" detection
    if rng.random() < 0.85:
        hx = pcx + rng.uniform(-prx * 0.5, prx * 0.5)
        hy = pcy + rng.uniform(-prx * 0.5, prx * 0.5)
        hr = max(1.0, prx * rng.uniform(0.15, 0.32))
        img[((xx - hx) ** 2 + (yy - hy) ** 2) <= hr ** 2] = rng.randint(200, 255)

    # eyelid occlusion from above
    if rng.random() < 0.5:
        lid = yy < (ecy - ery * rng.uniform(0.25, 0.95))
        img[lid] = np.clip(img[lid] - rng.randint(20, 60), 0, 255)

    img = np.clip(img + np.random.default_rng(rng.randint(0, 10**9))
                  .normal(0, rng.uniform(2, 11), img.shape), 0, 255).astype("uint8")

    # YOLO label: class 0, normalised centre + size
    box = 2 * prx
    return img, (pcx / size, pcy / size, box / size, box / size)


def build_dataset(root: Path, n_train: int, n_val: int, seed: int) -> Path:
    import cv2

    rng = random.Random(seed)
    if root.exists():
        shutil.rmtree(root)

    for split, count in (("train", n_train), ("val", n_val)):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for i in range(count):
            img, (cx, cy, w, h) = _draw_eye(rng)
            cv2.imwrite(str(root / "images" / split / f"{i:05d}.png"), img)
            (root / "labels" / split / f"{i:05d}.txt").write_text(
                f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n", encoding="utf-8"
            )

    data_yaml = root / "data.yaml"
    data_yaml.write_text(
        f"path: {root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 1\n"
        "names: [pupil]\n",
        encoding="utf-8",
    )
    return data_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("=====")[0])
    parser.add_argument("--train", type=int, default=400)
    parser.add_argument("--val", type=int, default=80)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--keep-dataset", action="store_true")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics is not installed -- pip install -r requirements.txt")
        return 1

    if not BASE_WEIGHTS.exists():
        print(f"Need a YOLOv8n starting point at {BASE_WEIGHTS}.")
        print("Fetch it with:\n  curl -L -o models/yolov8n.pt \\\n"
              "    https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt")
        return 1

    workdir = REPO / "runs" / "smoketest"
    dataset = workdir / "dataset"
    print(f"Generating {args.train} train / {args.val} val synthetic eyes ...")
    data_yaml = build_dataset(dataset, args.train, args.val, args.seed)

    print(f"Fine-tuning {BASE_WEIGHTS.name} for {args.epochs} epochs on CPU ...")
    model = YOLO(str(BASE_WEIGHTS))
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=IMG,
        batch=32,
        device="cpu",
        workers=0,              # Windows-safe
        project=str(workdir),
        name="train",
        exist_ok=True,
        verbose=False,
        plots=False,
        seed=args.seed,
    )

    best = workdir / "train" / "weights" / "best.pt"
    if not best.exists():
        print(f"Training finished but {best} is missing.")
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, OUTPUT)
    if not args.keep_dataset:
        shutil.rmtree(dataset, ignore_errors=True)

    print(f"\nWrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    print("\n" + "=" * 70)
    print("SMOKE TEST ONLY. This is not models/pupil_yolo_final.pt and its")
    print("accuracy is meaningless -- it was trained on drawn ellipses.")
    print("Never quote numbers from it. Get the real weights from Drive.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
