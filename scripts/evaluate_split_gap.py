"""
evaluate_split_gap.py

Evaluates one trained detector TWICE -- on its own training data, and on
held-out subjects -- and reports the difference.

    python scripts/evaluate_split_gap.py --weights runs/subject_split/train/weights/best.pt

WHAT THIS ANSWERS
-----------------
The README's benchmark table was produced with configs/lpw.yaml, where `train`
and `val` point at the same folder. The question a reviewer will ask is not
"is that wrong" (it is) but "by how much".

Asserting "treat them as optimistic" is a guess. This measures it: same model,
same weights, same metric, two evaluation sets. The only variable is whether
the images were in training.

Both numbers come from the same run, so the gap is attributable to the split
and nothing else -- not to a different model, a different image size, or a
different Ultralytics version.

Writes runs/eval/split_gap.json and prints a table.
"""

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

METRICS = ("precision", "recall", "mAP50", "mAP50-95")


def _extract(results) -> dict:
    box = results.box
    return {
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "mAP50": round(float(box.map50), 4),
        "mAP50-95": round(float(box.map), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure the train==val inflation")
    ap.add_argument("--weights", default="runs/subject_split/train/weights/best.pt")
    ap.add_argument("--imgsz", type=int, default=416)
    ap.add_argument("--split", default="val",
                    help="'val' while tuning; 'test' once, for the final table")
    args = ap.parse_args()

    weights = Path(args.weights)
    if not weights.is_absolute():
        weights = REPO / weights
    if not weights.exists():
        print(f"No weights at {weights}.\n"
              f"Train first:  python scripts/make_lpw_split.py && "
              f"yolo train model=models/yolov8n.pt "
              f"data=configs/lpw_subject_split.yaml device=cpu")
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics is not installed -- pip install -r requirements.txt")
        return 1

    honest_cfg = REPO / "configs" / "lpw_subject_split.yaml"
    leaky_cfg = REPO / "configs" / "lpw_leaky.yaml"
    for cfg in (honest_cfg, leaky_cfg):
        if not cfg.exists():
            print(f"{cfg} missing -- run scripts/make_lpw_split.py first")
            return 1

    common = dict(imgsz=args.imgsz, device="cpu", workers=0, verbose=False,
                  plots=False, project=str(REPO / "runs" / "eval"))

    print("Evaluating on TRAINING data (reproduces the original setup) ...")
    leaky = _extract(YOLO(str(weights)).val(data=str(leaky_cfg), split="val",
                                            name="leaky", exist_ok=True, **common))

    print(f"Evaluating on HELD-OUT SUBJECTS ({args.split}) ...")
    honest = _extract(YOLO(str(weights)).val(data=str(honest_cfg), split=args.split,
                                             name=f"heldout_{args.split}",
                                             exist_ok=True, **common))

    manifest = json.loads((REPO / "runs" / "splits" / "split_manifest.json")
                          .read_text(encoding="utf-8"))

    print(f"\n{'metric':<12}{'train==val':>12}{'held-out':>12}{'change':>12}")
    print("-" * 48)
    rows = {}
    for m in METRICS:
        a, b = leaky[m], honest[m]
        delta = b - a
        pct = (delta / a * 100) if a else 0.0
        rows[m] = {"train_eq_val": a, "held_out": b,
                   "absolute_change": round(delta, 4),
                   "relative_change_pct": round(pct, 1)}
        print(f"{m:<12}{a:>12.4f}{b:>12.4f}{delta:>+12.4f}")

    out = {
        "weights": str(weights),
        "imgsz": args.imgsz,
        "held_out_split": args.split,
        "subjects": manifest["subjects"],
        "frames": manifest["counts"],
        "leaky_train_eq_val": leaky,
        "held_out_subjects": honest,
        "delta": rows,
        "interpretation":
            "Same weights, same metric, same image size. The only difference "
            "is whether the evaluated frames were in training. Any gap is the "
            "inflation the original configs/lpw.yaml introduced.",
    }
    out_path = REPO / "runs" / "eval" / "split_gap.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path.relative_to(REPO)}")
    print("\nQuote the held-out column. The train==val column exists only to "
          "show what the original config was measuring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
