"""
compare_models.py

Pulls FRCNN and SSD results from runs/eval/*.csv (produced by evaluate.py)
plus YOLO's numbers (fill in from `yolo val ...` output -- see below) into
one final benchmark table for the paper/report.

YOLO's numbers aren't auto-read from a file because its output format
differs from evaluate.py's -- filling them in from the `yolo val` console
output is more reliable than parsing yet another format blind. Run this
first:

    yolo val model=runs/detect/runs/yolo-2/weights/best.pt data=configs/lpw.yaml

Then fill in YOLO_PRECISION / YOLO_RECALL / YOLO_MAP50 / YOLO_FPS below
from what it prints, and run this script.

Usage:
    python evaluation/compare_models.py
"""

import csv
import os

# ── Fill these in from your `yolo val` output ───────────────────────────────
YOLO_PRECISION = 0.972
YOLO_RECALL = 0.944
YOLO_MAP50 = 0.972
# ultralytics prints this natively as "mAP50-95" in the same val table as
# precision/recall/mAP50 -- no separate run needed, just read the column.
YOLO_MAP50_95 = None
YOLO_INFERENCE_MS = 1.6
# ultralytics' val output doesn't report this in the same terms evaluate.py
# does (its "no detection" accounting is per-class, not per-image-has-a-
# pupil); leave None to print "n/a" in the table rather than guess a number.
YOLO_FAILURE_RATE = None
# ─────────────────────────────────────────────────────────────────────────────

EVAL_DIR = "runs/eval"


def read_eval_csv(path):
    with open(path, newline="") as f:
        row = next(csv.DictReader(f))
    return row


def main():
    if YOLO_PRECISION is None:
        print("Fill in the YOLO_* constants at the top of this script first --")
        print("run `yolo val model=runs/detect/runs/yolo-2/weights/best.pt data=configs/lpw.yaml`")
        print("and copy the P / R / mAP50 / inference-ms values in.")
        return

    frcnn_path = os.path.join(EVAL_DIR, "frcnn_eval.csv")
    ssd_path = os.path.join(EVAL_DIR, "ssd_eval.csv")

    if not os.path.exists(frcnn_path) or not os.path.exists(ssd_path):
        print(f"Missing {frcnn_path} or {ssd_path} -- run evaluate.py for both models first.")
        return

    frcnn = read_eval_csv(frcnn_path)
    ssd = read_eval_csv(ssd_path)

    rows = [
        {
            "model": "YOLOv8n",
            "precision": YOLO_PRECISION,
            "recall": YOLO_RECALL,
            "map50": YOLO_MAP50,
            "map50_95": YOLO_MAP50_95,
            "failure_rate": YOLO_FAILURE_RATE,
            "fps": round(1000 / YOLO_INFERENCE_MS, 2) if YOLO_INFERENCE_MS else None,
        },
        {
            "model": "Faster R-CNN",
            "precision": float(frcnn["precision"]),
            "recall": float(frcnn["recall"]),
            "map50": float(frcnn["map50"]),
            "map50_95": float(frcnn["map50_95"]) if "map50_95" in frcnn else None,
            "failure_rate": float(frcnn["failure_rate"]) if "failure_rate" in frcnn else None,
            "fps": float(frcnn["fps"]),
        },
        {
            "model": "SSD300",
            "precision": float(ssd["precision"]),
            "recall": float(ssd["recall"]),
            "map50": float(ssd["map50"]),
            "map50_95": float(ssd["map50_95"]) if "map50_95" in ssd else None,
            "failure_rate": float(ssd["failure_rate"]) if "failure_rate" in ssd else None,
            "fps": float(ssd["fps"]),
        },
    ]

    def fmt(v):
        return f"{v:.4f}" if v is not None else "n/a"

    # Print a clean table
    print(f"\n{'Model':<15}{'Precision':<11}{'Recall':<11}{'mAP@0.5':<11}{'mAP@[.5:.95]':<14}{'Fail rate':<11}{'FPS':<10}")
    print("-" * 83)
    for r in rows:
        print(f"{r['model']:<15}{fmt(r['precision']):<11}{fmt(r['recall']):<11}{fmt(r['map50']):<11}"
              f"{fmt(r['map50_95']):<14}{fmt(r['failure_rate']):<11}{r['fps']:<10.2f}")

    # Save it
    os.makedirs(EVAL_DIR, exist_ok=True)
    out_path = os.path.join(EVAL_DIR, "final_comparison.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "precision", "recall", "map50", "map50_95",
                                               "failure_rate", "fps"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved -> {out_path}")

    fastest = max(rows, key=lambda r: r["fps"])
    most_accurate = max(rows, key=lambda r: r["map50"])
    print(f"\nFastest: {fastest['model']} ({fastest['fps']:.1f} FPS)")
    print(f"Highest mAP@0.5: {most_accurate['model']} ({most_accurate['map50']:.4f})")
    print(
        "\nNote: robustness under varied lighting/glasses hasn't been separately "
        "tested -- these numbers are speed + accuracy only. Also remember: "
        "train/val point at the same folder in configs/lpw.yaml, so treat all "
        "three numbers as optimistic vs. a genuine held-out test."
    )


if __name__ == "__main__":
    main()