"""
webcam_demo.py

Visual sanity check for the live loop. Not part of the API -- this is the
"is the detector actually finding my pupils" tool.

    cd backend/cv
    python3 webcam_demo.py                    # default camera, default weights
    python3 webcam_demo.py --camera 1 --conf 0.4
    python3 webcam_demo.py --headless         # no window, just FPS + hit rate

Press q to quit.

Requires the real stack: opencv-python, ultralytics, mediapipe, and
models/pupil_yolo_final.pt copied in from Drive.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cv.frame_source import webcam_frames                                  # noqa: E402
from cv.pupil_detector import DEFAULT_CONF, DetectorUnavailable, PupilDetector  # noqa: E402
from cv.landmarks import EyeLandmarker, LandmarkerUnavailable              # noqa: E402


def _draw(frame, result):
    import cv2

    for region in result.eye_regions.values():
        cv2.rectangle(frame, (region.x1, region.y1), (region.x2, region.y2), (90, 90, 90), 1)

    for pupil in result.pupils.values():
        cv2.circle(frame, (int(pupil.x_px), int(pupil.y_px)), 3, (0, 255, 0), -1)
        cv2.putText(
            frame, f"{pupil.side} {pupil.confidence:.2f}",
            (int(pupil.x_px) - 30, int(pupil.y_px) - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1,
        )

    if result.note:
        cv2.putText(frame, result.note, (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Live pupil detection preview")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--conf", type=float, default=DEFAULT_CONF)
    parser.add_argument("--weights", default=None, help="override models/pupil_yolo_final.pt")
    parser.add_argument("--headless", action="store_true", help="no preview window")
    args = parser.parse_args()

    # video_mode: a webcam really is one continuous ordered stream, so
    # tracking between frames is both safe and faster here. The HTTP path
    # deliberately doesn't do this -- see landmarks.EyeLandmarker.
    detector = PupilDetector(
        weights_path=args.weights,
        conf=args.conf,
        landmarker=EyeLandmarker(video_mode=True),
    )

    frames = 0
    hits = 0
    started = time.time()

    try:
        for frame in webcam_frames(args.camera):
            result = detector.detect(frame)
            frames += 1
            if result.has_any_pupil:
                hits += 1

            if not args.headless:
                import cv2

                cv2.imshow("GazeLens -- pupil detection", _draw(frame, result))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            elif frames % 30 == 0:
                elapsed = time.time() - started
                print(f"{frames} frames  {frames / elapsed:5.1f} fps  "
                      f"hit rate {hits / frames:.1%}")
    except (DetectorUnavailable, LandmarkerUnavailable) as exc:
        print(f"Cannot run live detection: {exc}")
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        detector.close()
        if not args.headless:
            try:
                import cv2

                cv2.destroyAllWindows()
            except ImportError:
                pass

    if frames:
        elapsed = time.time() - started
        print(f"\n{frames} frames in {elapsed:.1f}s  --  {frames / elapsed:.1f} fps, "
              f"pupil found in {hits / frames:.1%} of frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
