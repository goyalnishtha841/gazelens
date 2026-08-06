"""
synthetic.py

Fake calibration sessions, so this module can be built and tested without a
webcam, without models/pupil_yolo_final.pt, and without waiting for real
participants. Same pattern backend/agents used with mock_sessions.py, and
backend/cv used with StubPipeline.

The important design choice: this does NOT hand-roll calibration's storage
format. It builds real `CalibrationSample` and `CalibrationSession` objects
from backend/calibration and lets them serialise themselves. So a synthetic
session is byte-identical in shape to a real one, and the tests that run
against it genuinely prove schema compatibility -- rather than proving this
module can read a format it invented for itself.

THE GROUND-TRUTH MAPPING
------------------------
Real webcam gaze has a pupil-to-screen relationship that is close to linear
but not linear: the pupil's apparent position within the eye compresses
towards the edges (the eyeball is a sphere seen in projection), the two eyes
sit at slightly different offsets, and the head drifts over the minute or so
a calibration takes.

`GazeGeometry` encodes exactly that, so a test can ask a fair question: given
noisy observations of a KNOWN mapping, does the fitted model recover it to
within the noise floor? A purely linear generator would let a degree-1 model
look perfect and tell us nothing.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from calibration import generate_points
from calibration.session import CalibrationSample, CalibrationSession


@dataclass
class GazeGeometry:
    """The true pupil <- screen relationship a synthetic participant has.

    Deliberately not exposed to the model under test: it exists so tests can
    compare recovered accuracy against the noise that was actually injected.
    """

    # How far the pupil travels across its eye box for a full-screen gaze
    # sweep. ~0.5 means the pupil covers half the eye box corner to corner.
    gain_x: float = 0.52
    gain_y: float = 0.38

    # Spherical-projection compression towards the edges. This is the term a
    # degree-1 model cannot capture and a degree-2 model can.
    curvature_x: float = -0.18
    curvature_y: float = -0.12

    # Slight shear -- the camera is rarely square to the face.
    cross_term: float = 0.05

    # Per-eye resting offsets within their own eye boxes.
    left_offset: Tuple[float, float] = (0.50, 0.50)
    right_offset: Tuple[float, float] = (0.48, 0.51)

    # Vergence: the eyes converge slightly, so they don't move identically.
    vergence: float = 0.03

    def pupil_for(self, tx: float, ty: float, side: str) -> Tuple[float, float]:
        """Screen target (normalised) -> that eye's pupil position, noise-free."""
        u, v = tx - 0.5, ty - 0.5
        ox, oy = self.left_offset if side == "left" else self.right_offset
        sign = 1.0 if side == "left" else -1.0

        x = ox + self.gain_x * u + self.curvature_x * u * abs(u) + self.cross_term * v
        x += sign * self.vergence * u
        y = oy + self.gain_y * v + self.curvature_y * v * abs(v)
        return x, y


@dataclass
class SessionProfile:
    """How well this synthetic sitting went.

    Defaults describe a cooperative participant in decent light. The presets
    below cover the cases that actually break things.
    """

    noise_std: float = 0.012          # per-frame detector jitter, eye-box units
    head_drift: float = 0.010         # slow drift over the whole session
    blink_rate: float = 0.05          # frames with no pupil at all
    one_eye_rate: float = 0.06        # frames where only one eye is found
    confidence_mean: float = 0.88
    confidence_std: float = 0.05
    outlier_rate: float = 0.01        # frames where the detector is just wrong
    outlier_scale: float = 0.15


GOOD_SESSION = SessionProfile()
NOISY_SESSION = SessionProfile(
    noise_std=0.030, head_drift=0.035, blink_rate=0.15,
    one_eye_rate=0.15, confidence_mean=0.62, outlier_rate=0.05,
)
PRISTINE_SESSION = SessionProfile(
    noise_std=0.0, head_drift=0.0, blink_rate=0.0,
    one_eye_rate=0.0, outlier_rate=0.0, confidence_mean=0.99, confidence_std=0.0,
)


def generate_calibration_session(
    participant_id: str = "synthetic_p001",
    pattern: int = 16,
    samples_per_point: int = 15,
    screen_width: int = 1920,
    screen_height: int = 1080,
    geometry: Optional[GazeGeometry] = None,
    profile: Optional[SessionProfile] = None,
    seed: int = 0,
) -> CalibrationSession:
    """A complete synthetic session, in backend/calibration's own objects.

    Seeded, so a failing test is reproducible rather than a coin flip.
    """
    geometry = geometry or GazeGeometry()
    profile = profile or GOOD_SESSION
    rng = random.Random(seed)

    session = CalibrationSession.create(
        participant_id=participant_id,
        pattern=pattern,
        screen_width=screen_width,
        screen_height=screen_height,
        samples_per_point=samples_per_point,
    )

    points = generate_points(pattern)
    total_frames = len(points) * samples_per_point
    frame_no = 0
    t0 = 1_700_000_000.0

    for point in points:
        for _ in range(samples_per_point):
            frame_no += 1
            progress = frame_no / total_frames

            # Head drift accumulates through the sitting -- the participant
            # settles into their chair. This is the effect that makes
            # eye-normalised coordinates worth using over frame coordinates.
            drift_x = profile.head_drift * progress
            drift_y = profile.head_drift * 0.6 * progress

            if rng.random() < profile.blink_rate:
                session.record_rejection()
                continue

            drop_side = None
            if rng.random() < profile.one_eye_rate:
                drop_side = rng.choice(("left", "right"))

            eyes: Dict[str, Tuple[float, float]] = {}
            for side in ("left", "right"):
                if side == drop_side:
                    continue
                px, py = geometry.pupil_for(point.x, point.y, side)
                px += drift_x + rng.gauss(0.0, profile.noise_std)
                py += drift_y + rng.gauss(0.0, profile.noise_std)
                if rng.random() < profile.outlier_rate:
                    px += rng.gauss(0.0, profile.outlier_scale)
                    py += rng.gauss(0.0, profile.outlier_scale)
                # The detector can only ever report a position inside the eye
                # box it cropped, so clamping here is physical, not cosmetic.
                eyes[side] = (min(max(px, 0.0), 1.0), min(max(py, 0.0), 1.0))

            if not eyes:
                session.record_rejection()
                continue

            left = eyes.get("left")
            right = eyes.get("right")
            confidence = min(max(
                rng.gauss(profile.confidence_mean, profile.confidence_std), 0.05), 1.0)

            session.add_sample(CalibrationSample(
                sample_id=f"syn_{frame_no:06d}",
                point_index=point.index,
                target_x=point.x,
                target_y=point.y,
                left_x_eye=left[0] if left else None,
                left_y_eye=left[1] if left else None,
                right_x_eye=right[0] if right else None,
                right_y_eye=right[1] if right else None,
                # Frame coordinates are what a real detector would also
                # report: eye position in the frame, shifted by head drift.
                left_x_frame=0.35 + drift_x + (left[0] - 0.5) * 0.05 if left else None,
                left_y_frame=0.45 + drift_y + (left[1] - 0.5) * 0.03 if left else None,
                right_x_frame=0.65 + drift_x + (right[0] - 0.5) * 0.05 if right else None,
                right_y_frame=0.45 + drift_y + (right[1] - 0.5) * 0.03 if right else None,
                confidence=confidence,
                head_proxy={
                    "interocular_norm": 0.30 - drift_x * 0.1,
                    "eye_mid_x": 0.5 + drift_x,
                    "eye_mid_y": 0.45 + drift_y,
                    "roll_norm": 0.0,
                    "nose_x": 0.5 + drift_x,
                    "nose_y": 0.55 + drift_y,
                },
                frame_width=640,
                frame_height=480,
                timestamp=t0 + frame_no * 0.033,
                eyes_detected=len(eyes),
            ))

    return session


def generate_training_rows(**kwargs) -> List[Dict]:
    """Shortcut: synthetic session -> the flat rows this module trains on."""
    return generate_calibration_session(**kwargs).training_rows()


def synthetic_gaze_stream(
    geometry: Optional[GazeGeometry] = None,
    path: Optional[List[Tuple[float, float]]] = None,
    samples_per_stop: int = 10,
    noise_std: float = 0.012,
    seed: int = 7,
) -> List[Dict]:
    """A fake LIVE stream: where the eye was, and where it was really looking.

    Distinct from calibration data -- these are the frames that arrive after
    calibration is done, the ones inference runs on. Each entry carries the
    pupil positions to feed the model plus the `true_x`/`true_y` the model is
    supposed to recover, so a test can measure live accuracy rather than just
    checking the call doesn't crash.

    Also the shape backend/attribution will eventually consume, one step
    further along -- see CONTRACT.md.
    """
    geometry = geometry or GazeGeometry()
    rng = random.Random(seed)
    path = path or [
        (0.20, 0.20), (0.80, 0.20), (0.50, 0.50), (0.20, 0.80), (0.80, 0.80),
    ]

    stream: List[Dict] = []
    t = 1_700_001_000.0
    for tx, ty in path:
        for _ in range(samples_per_stop):
            t += 0.033
            eyes = {}
            for side in ("left", "right"):
                px, py = geometry.pupil_for(tx, ty, side)
                eyes[side] = (
                    min(max(px + rng.gauss(0, noise_std), 0.0), 1.0),
                    min(max(py + rng.gauss(0, noise_std), 0.0), 1.0),
                )
            stream.append({
                "timestamp": t,
                "left": eyes["left"],
                "right": eyes["right"],
                "true_x": tx,
                "true_y": ty,
            })
    return stream


__all__ = [
    "GazeGeometry",
    "SessionProfile",
    "GOOD_SESSION",
    "NOISY_SESSION",
    "PRISTINE_SESSION",
    "generate_calibration_session",
    "generate_training_rows",
    "synthetic_gaze_stream",
]
