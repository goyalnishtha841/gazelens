"""
evaluate_gaze_sessions.py

Which gaze model generalises best? Retrains every variant on each saved
session's calibration and scores it on that session's accuracy-check dots.
See backend/gaze_estimation/offline_eval.py for what the variants are.

    python scripts/evaluate_gaze_sessions.py                  # all sessions
    python scripts/evaluate_gaze_sessions.py --sessions cal_99bf6b5aa172
    python scripts/evaluate_gaze_sessions.py --csv runs/gaze_eval.csv

Only sessions recorded after the accuracy check started saving frames
(gaze_models/<id>.validation.jsonl) can be scored.

Columns:
  median/p90/max  check-dot error in px, pooled over all dots
  dx/dy           mean signed error: +dx = predicted right, +dy = predicted low
  gain x/y        slope of predicted vs true position; 1.00 = full range,
                  below 1 = predictions squeezed towards the centre
"""

import argparse
import csv
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from gaze_estimation.offline_eval import (  # noqa: E402
    AUTO,
    evaluate,
    find_sessions,
    summarise,
)

# Below this, a ranking is mostly noise -- say so instead of implying a winner.
MIN_DOTS_TO_RANK = 15


def _fmt_gain(g):
    return "  -  " if g is None else f"{g:5.2f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sessions", nargs="*", help="calibration ids (default: all with check frames)")
    parser.add_argument("--feature-sets", nargs="*", help="limit to these feature sets")
    parser.add_argument("--ridge", type=float, default=1e-2, help="ridge for fixed variants")
    parser.add_argument("--csv", type=Path, help="write every dot result here")
    args = parser.parse_args(argv)

    sessions = args.sessions or find_sessions()
    if not sessions:
        print("No sessions with saved accuracy-check frames yet. Calibrate (with the "
              "accuracy check) at least once, then rerun.")
        return 1

    results = evaluate(sessions, feature_sets=args.feature_sets, ridge=args.ridge)
    summaries = [s for s in (summarise(v, d) for v, d in results.items()) if s]
    summaries.sort(key=lambda s: (s.median_px, s.p90_px))

    print(f"{len(sessions)} session(s): {', '.join(sessions)}\n")
    header = f"{'variant':26s} {'sess':>4s} {'dots':>4s} {'median':>7s} {'p90':>6s} {'max':>6s} " \
             f"{'dx':>6s} {'dy':>6s} {'gain x':>6s} {'gain y':>6s}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        mark = " <- shipped" if s.variant == AUTO else ""
        print(f"{s.variant:26s} {s.sessions:4d} {s.dots:4d} {s.median_px:7.0f} {s.p90_px:6.0f} "
              f"{s.max_px:6.0f} {s.mean_dx_px:+6.0f} {s.mean_dy_px:+6.0f} "
              f"{_fmt_gain(s.gain_x):>6s} {_fmt_gain(s.gain_y):>6s}{mark}")

    if len(sessions) > 1:
        print("\nper-session median error (px):")
        top = summaries[: min(6, len(summaries))]
        print(f"{'session':18s}" + "".join(f"{s.variant[:16]:>18s}" for s in top))
        for sid in sessions:
            print(f"{sid:18s}" + "".join(
                f"{s.per_session_median_px[sid]:18.0f}" if sid in s.per_session_median_px else f"{'-':>18s}"
                for s in top))

    total_dots = max((s.dots for s in summaries), default=0)
    if total_dots < MIN_DOTS_TO_RANK:
        print(f"\nOnly {total_dots} check dots: too few to pick a winner. Differences "
              f"this small can flip with the next session; aim for {MIN_DOTS_TO_RANK}+ "
              f"(3+ sessions).")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = None
            for variant, dots in results.items():
                for d in dots:
                    row = {"variant": variant, **asdict(d)}
                    if writer is None:
                        writer = csv.DictWriter(fh, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
        print(f"\nper-dot results written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
