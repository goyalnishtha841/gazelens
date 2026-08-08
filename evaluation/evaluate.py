"""
evaluate.py

Runs a trained detector (FRCNN or SSD) against the dataset and computes:
  - Precision / Recall / F1 at a fixed confidence threshold
  - mAP@0.5 -- a real precision-recall curve, not a single-point estimate
  - mAP@[0.5:0.95] -- the same curve re-scored at 10 IoU thresholds
    (0.50, 0.55, ..., 0.95) and averaged, COCO-style. mAP@0.5 alone credits
    a box that's roughly in the right place the same as one that's pixel-
    perfect; averaging across thresholds is what actually separates a
    detector that's approximately right from one that's precisely right,
    which matters for pupil localisation specifically -- a gaze estimate
    inherits the pupil box's imprecision directly.
  - Failure rate -- fraction of images with no acceptable detection at all
    (same condition as an FN at --conf-threshold/--iou-threshold). Not
    "accuracy is imperfect" (P/R/F1 already say that) but "on this fraction
    of frames the pipeline would report a blink or dropout, when a person
    was actually there" -- the number a live gaze stream's gap rate maps to.
  - FPS -- average inference speed (model forward pass only, GPU synced)

Saves a summary CSV to runs/eval/<model>_eval.csv so FRCNN, SSD, and
YOLO's own ultralytics-generated results (runs/detect/runs/yolo-2/results.csv)
can be pulled into one comparison table for the benchmark.

Preprocessing is matched EXACTLY to each model's own training script:
  - FRCNN: full-size images, no resize (matches training/train_frcnn.py)
  - SSD:   resized to 300x300 (matches training/train_ssd.py)
Getting this wrong would silently produce meaningless numbers -- the
model's predicted boxes and the ground-truth boxes must be in the same
coordinate space.

KNOWN LIMITATION (from configs/lpw.yaml):
    train: images
    val:   images
Both point at the same folder. These metrics are measured on data the
model already trained on, not a genuine held-out test set. State this
explicitly wherever these numbers are reported -- don't let it look like
an oversight.

Usage:
    python evaluation/evaluate.py --model frcnn --weights runs/frcnn/frcnn_final.pth
    python evaluation/evaluate.py --model ssd   --weights runs/ssd/ssd_final.pth
"""

import os
import sys
import time
import argparse
import csv

import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as T

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(__file__))

from metrics import precision, recall, f1  # reuse your existing formulas, don't duplicate them


# ── Dataset -- mirrors each model's own training preprocessing exactly ─────

class EvalDataset(Dataset):
    def __init__(self, images_dir, labels_dir, resize_to=None):
        self.images_dir = images_dir
        self.labels_dir = labels_dir
        self.resize_to = resize_to
        tfs = []
        if resize_to:
            tfs.append(T.Resize((resize_to, resize_to)))
        tfs.append(T.ToTensor())
        self.transforms = T.Compose(tfs)

        self.samples = []
        for img_file in sorted(os.listdir(images_dir)):
            if not img_file.lower().endswith(".jpg"):
                continue
            label_file = img_file.replace(".jpg", ".txt")
            if os.path.exists(os.path.join(labels_dir, label_file)):
                self.samples.append(img_file)

        print(f"Eval dataset: {len(self.samples)} samples")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_file = self.samples[idx]
        img_path = os.path.join(self.images_dir, img_file)
        label_path = os.path.join(self.labels_dir, img_file.replace(".jpg", ".txt"))

        img = Image.open(img_path).convert("RGB")
        orig_w, orig_h = img.size
        img_tensor = self.transforms(img)

        # The GT box must be expressed in whatever coordinate space the
        # model will actually predict in -- resize_to if we resized, else
        # the image's original size.
        W = self.resize_to if self.resize_to else orig_w
        H = self.resize_to if self.resize_to else orig_h

        with open(label_path, "r") as f:
            cls, xc, yc, bw, bh = map(float, f.readline().split())

        xc *= W; yc *= H; bw *= W; bh *= H
        x1, y1 = xc - bw / 2, yc - bh / 2
        x2, y2 = xc + bw / 2, yc + bh / 2

        gt_box = torch.tensor([x1, y1, x2, y2], dtype=torch.float32)
        return img_tensor, gt_box, img_file


def collate_fn(batch):
    imgs, gts, names = zip(*batch)
    return list(imgs), list(gts), list(names)


# ── IoU -- verified against hand-calculated cases before shipping ──────────

def box_iou(box1, box2):
    x1 = max(box1[0], box2[0]); y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2]); y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


# ── AP@0.5 -- standard all-points interpolated average precision ───────────
# (VOC/COCO-style). Verified against textbook perfect/worst/half-right cases
# before shipping -- see the test cases this was built against for the exact
# assertions, if you want to re-verify.

def compute_ap(all_detections, num_gt, iou_threshold=0.5):
    """
    all_detections: list of (confidence, is_tp) tuples across the WHOLE
                     dataset, already matched against ground truth.
    """
    if not all_detections or num_gt == 0:
        return 0.0

    all_detections.sort(key=lambda d: d[0], reverse=True)
    tp_cum, fp_cum = 0, 0
    precisions, recalls = [], []
    for conf, is_tp in all_detections:
        if is_tp:
            tp_cum += 1
        else:
            fp_cum += 1
        precisions.append(tp_cum / (tp_cum + fp_cum))
        recalls.append(tp_cum / num_gt)

    precisions = [0.0] + precisions + [0.0]
    recalls = [0.0] + recalls + [1.0]
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])

    ap = 0.0
    for i in range(1, len(recalls)):
        ap += (recalls[i] - recalls[i - 1]) * precisions[i]
    return ap


# IoU thresholds compute_ap_range averages over -- 0.50, 0.55, ..., 0.95.
# Written as round(x, 2) rather than left as raw float arithmetic: summing
# 0.05 repeatedly drifts (0.7000000000000001), and a threshold that isn't
# exactly 0.70 would silently mis-bucket detections right at that boundary.
COCO_IOU_THRESHOLDS = [round(0.5 + 0.05 * i, 2) for i in range(10)]


def compute_ap_range(match_records, num_gt, iou_thresholds=COCO_IOU_THRESHOLDS):
    """mAP@[0.5:0.95]: compute_ap re-scored at each threshold, then averaged.

    match_records: list of (confidence, is_best_match, best_iou) -- the
    per-detection match info BEFORE thresholding, so TP/FP can be re-derived
    at any IoU cutoff without re-running the model. `is_best_match` mirrors
    the single-object-per-image assumption the rest of this file makes: only
    the highest-IoU prediction for an image can ever be a TP, regardless of
    threshold; every other prediction is a FP at every threshold.

    Returns (mean_ap, {threshold: ap}) -- the per-threshold breakdown is
    kept because a curve that's flat across thresholds means "localises
    precisely, not just roughly", which is worth being able to show
    directly rather than only the single averaged number.
    """
    per_threshold = {}
    for thresh in iou_thresholds:
        detections_at_thresh = [
            (conf, is_best and best_iou >= thresh)
            for conf, is_best, best_iou in match_records
        ]
        per_threshold[thresh] = compute_ap(detections_at_thresh, num_gt, thresh)
    mean_ap = sum(per_threshold.values()) / len(per_threshold) if per_threshold else 0.0
    return mean_ap, per_threshold


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["frcnn", "ssd"], required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--images", default="dataset/images")
    parser.add_argument("--labels", default="dataset/labels")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument(
        "--conf-threshold", type=float, default=0.5,
        help="Confidence threshold used for the reported precision/recall/F1 operating point",
    )
    parser.add_argument(
        "--batch-size", type=int, default=8,
        help="Images per GPU forward pass. Higher = faster on a capable GPU, but uses more VRAM. Try 8, raise to 16 if you have headroom.",
    )
    parser.add_argument(
        "--num-workers", type=int, default=8,
        help="Parallel CPU processes for loading/decoding images, overlapped with GPU compute. Matches the value already used successfully in train_frcnn.py on this machine.",
    )
    parser.add_argument("--output-dir", default="runs/eval")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Evaluate only the first N images -- use this for a quick smoke test before committing to a full run",
    )
    parser.add_argument(
        "--print-every", type=int, default=500,
        help="Print a progress line every N images (0 disables)",
    )
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if args.model == "frcnn":
        from models.frcnn import get_model
        resize_to = None  # FRCNN trained on full-size images -- see train_frcnn.py
    else:
        from models.ssd import get_model
        resize_to = 300  # SSD trained on 300x300 -- see train_ssd.py

    model = get_model().to(device)
    state_dict = torch.load(args.weights, map_location=device)
    # runs/frcnn/frcnn_epoch*.pth are wrapped {"model": ..., "optimizer": ...},
    # but frcnn_final.pth / ssd_final.pth are raw state_dicts. Handle both so
    # this doesn't silently break if pointed at the wrong checkpoint.
    if isinstance(state_dict, dict) and "model" in state_dict:
        print("Detected wrapped checkpoint (epoch save) -- unwrapping 'model' key")
        state_dict = state_dict["model"]
    model.load_state_dict(state_dict)
    model.eval()

    dataset = EvalDataset(args.images, args.labels, resize_to=resize_to)
    if args.limit:
        dataset.samples = dataset.samples[: args.limit]
        print(f"--limit set: evaluating only the first {len(dataset)} images")
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_fn,
        num_workers=args.num_workers,
        pin_memory=(device.type == "cuda"),
    )
    print(f"Batch size: {args.batch_size}, num_workers: {args.num_workers}")

    # (confidence, is_best_match, best_iou) per detection -- kept unthresholded
    # so compute_ap_range can re-derive TP/FP at every IoU cutoff without a
    # second pass over the model.
    match_records = []
    tp_at_threshold = fp_at_threshold = fn_at_threshold = 0
    total_inference_time = 0.0
    num_gt = len(dataset)
    wall_start = time.time()
    processed = 0

    with torch.no_grad():
        for images, gt_boxes, names in loader:
            images = [img.to(device, non_blocking=True) for img in images]

            start = time.time()
            predictions = model(images)  # list of one dict per image in this batch
            if device.type == "cuda":
                torch.cuda.synchronize()
            total_inference_time += time.time() - start

            # Per-image logic below is UNCHANGED from the single-image version
            # that was already validated against your real run (0.91 P/R/F1,
            # 0.9737 mAP@0.5) -- only the outer loop now covers a batch
            # instead of always exactly one image.
            for pred, gt_box_tensor in zip(predictions, gt_boxes):
                gt_box = gt_box_tensor.tolist()
                pred_boxes = pred["boxes"].cpu().tolist()
                pred_scores = pred["scores"].cpu().tolist()

                best_iou, best_idx = 0.0, -1
                for i, pbox in enumerate(pred_boxes):
                    iou = box_iou(pbox, gt_box)
                    if iou > best_iou:
                        best_iou, best_idx = iou, i

                for i, score in enumerate(pred_scores):
                    match_records.append((score, i == best_idx, best_iou))

                if best_idx != -1 and pred_scores[best_idx] >= args.conf_threshold and best_iou >= args.iou_threshold:
                    tp_at_threshold += 1
                else:
                    fn_at_threshold += 1
                fp_at_threshold += sum(
                    1 for i, s in enumerate(pred_scores) if s >= args.conf_threshold and i != best_idx
                )

                processed += 1

            if args.print_every and processed % args.print_every < args.batch_size:
                elapsed = time.time() - wall_start
                rate = processed / elapsed
                remaining = (num_gt - processed) / rate if rate > 0 else float("inf")
                print(
                    f"  [{processed}/{num_gt}] "
                    f"{rate:.1f} img/s wall-clock, "
                    f"~{remaining / 60:.1f} min remaining"
                )

    p = precision(tp_at_threshold, fp_at_threshold)
    r = recall(tp_at_threshold, fn_at_threshold)
    f = f1(p, r)
    map_range, ap_per_iou = compute_ap_range(match_records, num_gt)
    ap50 = ap_per_iou.get(round(args.iou_threshold, 2), map_range)
    # Same condition as an FN above: no prediction cleared both the
    # confidence and IoU bars. Named and reported on its own because "the
    # detector was wrong about this frame" and "the detector said nothing
    # usable about this frame" are different failure modes for a live gaze
    # stream -- the second is a gap, and gaps are what attribution's dwell
    # time and fixation counts are most sensitive to.
    failure_rate = fn_at_threshold / num_gt if num_gt > 0 else 0.0
    fps = len(dataset) / total_inference_time if total_inference_time > 0 else 0.0

    print(f"\n{'=' * 50}")
    print(f"Model: {args.model}")
    print(f"Precision@{args.conf_threshold}: {p:.4f}")
    print(f"Recall@{args.conf_threshold}:    {r:.4f}")
    print(f"F1@{args.conf_threshold}:        {f:.4f}")
    print(f"mAP@{args.iou_threshold}:        {ap50:.4f}")
    print(f"mAP@[0.5:0.95]:         {map_range:.4f}")
    print(f"Failure rate:           {failure_rate:.4f} ({fn_at_threshold}/{num_gt} images)")
    print(f"FPS:                    {fps:.2f}")
    print(f"{'=' * 50}")
    print("mAP by IoU threshold (for the gap between mAP@0.5 and mAP@[0.5:0.95] -- ")
    print("a big drop-off means boxes are roughly right but not tightly localised):")
    for thresh, ap in sorted(ap_per_iou.items()):
        print(f"  {thresh:.2f}: {ap:.4f}")
    print(f"{'=' * 50}\n")

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"{args.model}_eval.csv")
    with open(out_path, "w", newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["model", "precision", "recall", "f1", "map50", "map50_95", "failure_rate",
                         "fps", "conf_threshold", "iou_threshold", "num_images"])
        writer.writerow([args.model, f"{p:.4f}", f"{r:.4f}", f"{f:.4f}", f"{ap50:.4f}", f"{map_range:.4f}",
                         f"{failure_rate:.4f}", f"{fps:.2f}", args.conf_threshold, args.iou_threshold, len(dataset)])

    print(f"Saved results -> {out_path}")


if __name__ == "__main__":
    main()
