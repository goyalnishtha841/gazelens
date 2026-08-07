"""
make_lpw_split.py

Builds a SUBJECT-WISE train/val/test split of LPW, and a deliberately leaky
train==val config to measure against.

    python scripts/make_lpw_split.py --dataset ../eye-gaze-lpw/dataset

WHY THIS EXISTS
---------------
configs/lpw.yaml points `train` and `val` at the same folder, so every number
in the README's benchmark table is measured on data the models trained on.

The obvious fix -- a random split of the 130,856 frames -- is barely better.
LPW is 22 subjects x 3 videos, so consecutive frames are near-duplicates of
each other: same eye, same lighting, same camera, milliseconds apart. A random
frame split puts frame 500 in train and frame 501 in val and calls that
generalisation. It measures interpolation between adjacent video frames, not
whether the detector works on a person it has never seen.

Splitting by SUBJECT is the only split that answers the question the paper
asks. Held-out subjects share no frames, no eye, no session with training.

Writes path-list files rather than copying images -- the dataset is 5GB and
Ultralytics reads a .txt of image paths directly.

OUTPUT
------
    configs/lpw_subject_split.yaml   the honest config
    configs/lpw_leaky.yaml           reproduces the current train==val setup,
                                     so the gap between them can be measured
    runs/splits/{train,val,test}.txt
    runs/splits/split_manifest.json  exactly which subjects went where
"""

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRAME_RE = re.compile(r"^(\d+)_(\d+)_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)

# 16/3/3 of 22 subjects. Test is held back entirely -- it should be touched
# once, for the final table, not while tuning.
DEFAULT_VAL_SUBJECTS = 3
DEFAULT_TEST_SUBJECTS = 3


def index_by_subject(images_dir: Path):
    by_subject = defaultdict(list)
    unparseable = 0
    for path in sorted(images_dir.iterdir()):
        m = FRAME_RE.match(path.name)
        if not m:
            unparseable += 1
            continue
        by_subject[m.group(1)].append(path)
    return by_subject, unparseable


def main() -> int:
    ap = argparse.ArgumentParser(description="Subject-wise LPW split")
    ap.add_argument("--dataset", default="../../eye-gaze-lpw/dataset",
                    help="folder containing images/ and labels/")
    ap.add_argument("--val-subjects", type=int, default=DEFAULT_VAL_SUBJECTS)
    ap.add_argument("--test-subjects", type=int, default=DEFAULT_TEST_SUBJECTS)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--limit-per-subject", type=int, default=0,
                    help="sample N frames per subject (0 = all). Use for a "
                         "CPU-feasible run; consecutive frames are nearly "
                         "identical so sampling loses little.")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    if not dataset.is_absolute():
        dataset = (REPO / dataset).resolve()
    images_dir = dataset / "images"
    labels_dir = dataset / "labels"

    if not images_dir.is_dir() or not labels_dir.is_dir():
        print(f"Expected {images_dir} and {labels_dir}. Point --dataset at the "
              f"folder holding images/ and labels/.")
        return 1

    by_subject, unparseable = index_by_subject(images_dir)
    if not by_subject:
        print(f"No frames matching <subject>_<video>_<frame>.jpg in {images_dir}")
        return 1

    subjects = sorted(by_subject, key=lambda s: int(s))
    n_val, n_test = args.val_subjects, args.test_subjects
    if n_val + n_test >= len(subjects):
        print(f"Only {len(subjects)} subjects; can't hold out {n_val + n_test}.")
        return 1

    rng = random.Random(args.seed)
    shuffled = subjects[:]
    rng.shuffle(shuffled)
    test_s = sorted(shuffled[:n_test], key=int)
    val_s = sorted(shuffled[n_test:n_test + n_val], key=int)
    train_s = sorted(shuffled[n_test + n_val:], key=int)

    def collect(subject_ids):
        out = []
        for s in subject_ids:
            frames = by_subject[s]
            if args.limit_per_subject and len(frames) > args.limit_per_subject:
                # Evenly spaced, not random: adjacent frames are near-identical,
                # so striding covers the whole session instead of clustering.
                step = len(frames) / args.limit_per_subject
                frames = [frames[int(i * step)] for i in range(args.limit_per_subject)]
            out.extend(frames)
        return out

    splits = {"train": collect(train_s), "val": collect(val_s), "test": collect(test_s)}

    out_dir = REPO / "runs" / "splits"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, paths in splits.items():
        (out_dir / f"{name}.txt").write_text(
            "\n".join(str(p.resolve()) for p in paths) + "\n", encoding="utf-8")

    # The honest config.
    #
    # The subject assignment is written into this file as comments, not just
    # into runs/splits/split_manifest.json: runs/ is gitignored, and "which
    # subjects were held out" is exactly what a reviewer needs to see. This
    # yaml is tracked, so the split survives in the repo even though the
    # 4,000-line path lists don't.
    (REPO / "configs" / "lpw_subject_split.yaml").write_text(
        "# Subject-wise LPW split -- train/val/test share NO subject.\n"
        "#\n"
        "# This is the config to quote numbers from. configs/lpw.yaml points\n"
        "# train and val at the same folder and measures memorisation.\n"
        "#\n"
        f"# SUBJECTS  train ({len(train_s)}): {', '.join(train_s)}\n"
        f"#           val   ({len(val_s)}): {', '.join(val_s)}\n"
        f"#           test  ({len(test_s)}): {', '.join(test_s)}\n"
        f"# FRAMES    train={len(splits['train'])} val={len(splits['val'])} "
        f"test={len(splits['test'])}"
        f"{f' (sampled {args.limit_per_subject}/subject)' if args.limit_per_subject else ''}\n"
        "#\n"
        "# `path` below is absolute and machine-specific -- the path lists live\n"
        "# under runs/, which is gitignored. Regenerate on any machine with:\n"
        f"#   python scripts/make_lpw_split.py --seed {args.seed}"
        f"{f' --limit-per-subject {args.limit_per_subject}' if args.limit_per_subject else ''}\n"
        "# Same seed + same dataset reproduces this exact split.\n"
        f"path: {out_dir.resolve().as_posix()}\n"
        "train: train.txt\n"
        "val: val.txt\n"
        "test: test.txt\n"
        "\nnc: 1\n"
        'names: ["pupil"]\n',
        encoding="utf-8")

    # The leaky config, for measuring the gap rather than asserting it.
    (REPO / "configs" / "lpw_leaky.yaml").write_text(
        "# DELIBERATELY LEAKY: val == train. Reproduces the original\n"
        "# configs/lpw.yaml so the inflation from evaluating on training data\n"
        "# can be MEASURED against lpw_subject_split.yaml rather than asserted.\n"
        "# Never quote numbers from this file.\n"
        f"path: {out_dir.resolve().as_posix()}\n"
        "train: train.txt\n"
        "val: train.txt\n"
        "\nnc: 1\n"
        'names: ["pupil"]\n',
        encoding="utf-8")

    manifest = {
        "seed": args.seed,
        "limit_per_subject": args.limit_per_subject or None,
        "split_by": "subject",
        "rationale": "LPW frames are consecutive video frames; a random frame "
                     "split puts near-duplicates in train and val. Only a "
                     "subject-wise split measures generalisation to a new person.",
        "subjects": {"train": train_s, "val": val_s, "test": test_s},
        "counts": {k: len(v) for k, v in splits.items()},
        "unparseable_filenames": unparseable,
    }
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2),
                                                 encoding="utf-8")

    print(f"subjects  train={len(train_s)} {train_s}")
    print(f"          val  ={len(val_s)} {val_s}")
    print(f"          test ={len(test_s)} {test_s}")
    print(f"frames    train={len(splits['train']):,}  val={len(splits['val']):,}  "
          f"test={len(splits['test']):,}")
    print(f"\nwrote {out_dir}/  and configs/lpw_subject_split.yaml + lpw_leaky.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
