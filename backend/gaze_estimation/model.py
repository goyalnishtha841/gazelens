"""
model.py

The regression: pupil position -> screen coordinate, fit per session.

WHY A POLYNOMIAL AND NOT A NETWORK
----------------------------------
A calibration session has 9 or 16 points. It has ~15 rows per point, but
those rows differ only by detector noise -- the participant was staring at
one target the whole time -- so the effective sample size is 9 or 16, not
~240.

At that size a 2-layer MLP has more parameters than it has independent
observations, and brings seeds, learning rates and stopping criteria that
all have to be defended in the paper. A low-order polynomial is the
classical pupil->screen mapping in the eye-tracking literature, has 3-10
parameters, and solves in closed form in microseconds on CPU.

The degree is not assumed: model selection (evaluation.py) cross-validates
degrees 1-3 against held-out POINTS and reports which won, so "degree 2 was
enough" is a measured result rather than an article of faith. If a session
ever selects degree 3 and still shows large error, that is the evidence
that would justify reaching for more capacity.

FITTING
-------
Ridge-regularised least squares, solved directly:

    w = (A'A + lambda*P)^-1 A'y

A is the polynomial design matrix, P penalises everything except the
intercept (shrinking the intercept would bias the whole mapping towards the
screen's origin). Features are standardised first so a single lambda means
the same thing across sessions and degrees. x and y are fitted as two
independent columns of the same solve -- there's no cross-coupling to
exploit, and one solve is cheaper than two.
"""

import json
import time
from dataclasses import dataclass, field
from itertools import combinations_with_replacement
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .features import FEATURE_DIMS, features_from_pupils

MODEL_FORMAT_VERSION = 1

# Small by default: this is here to keep the fit numerically stable and to
# stop a high-degree term exploding on a sparse session, not to do heavy
# shrinkage. Model selection tries a range around it.
DEFAULT_RIDGE = 1e-4


def _exponents(n_features: int, degree: int) -> List[Tuple[int, ...]]:
    """Exponent tuples for every monomial up to `degree`, bias term first.

    For 2 features at degree 2: 1, x, y, x^2, xy, y^2.
    """
    terms: List[Tuple[int, ...]] = []
    for total in range(degree + 1):
        for combo in combinations_with_replacement(range(n_features), total):
            exps = [0] * n_features
            for i in combo:
                exps[i] += 1
            terms.append(tuple(exps))
    return terms


def n_terms(n_features: int, degree: int) -> int:
    """How many parameters a (features, degree) pair costs, per output axis."""
    return len(_exponents(n_features, degree))


def design_matrix(Z: np.ndarray, exponents: Sequence[Tuple[int, ...]]) -> np.ndarray:
    """Standardised features -> polynomial design matrix."""
    Z = np.atleast_2d(Z)
    A = np.empty((Z.shape[0], len(exponents)), dtype=float)
    for j, exps in enumerate(exponents):
        col = np.ones(Z.shape[0], dtype=float)
        for i, e in enumerate(exps):
            if e:
                col = col * (Z[:, i] ** e)
        A[:, j] = col
    return A


@dataclass
class GazeModel:
    """A fitted per-session mapping. Cheap to call, trivial to serialise."""

    feature_set: str
    degree: int
    ridge: float
    coef: np.ndarray                    # (n_terms, 2) -> [target_x, target_y]
    mean: np.ndarray                    # (d,) feature standardisation
    scale: np.ndarray                   # (d,)

    screen_width: int
    screen_height: int

    session_id: str = ""
    participant_id: str = ""
    n_points: int = 0
    n_samples: int = 0

    # Held-out accuracy from evaluation.py. Attached to the model rather than
    # kept beside it so a loaded model always knows how good it is -- a model
    # that can't state its own error is one nobody can decide whether to trust.
    metrics: Dict = field(default_factory=dict)
    selection: Dict = field(default_factory=dict)

    trained_at: float = field(default_factory=time.time)
    format_version: int = MODEL_FORMAT_VERSION

    # ------------------------------------------------------------------

    @property
    def n_features(self) -> int:
        return int(self.mean.shape[0])

    @property
    def exponents(self) -> List[Tuple[int, ...]]:
        return _exponents(self.n_features, self.degree)

    # ------------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        X: np.ndarray,
        y: np.ndarray,
        feature_set: str,
        degree: int,
        ridge: float = DEFAULT_RIDGE,
        screen_width: int = 1920,
        screen_height: int = 1080,
        **meta,
    ) -> "GazeModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)

        mean = X.mean(axis=0)
        scale = X.std(axis=0)
        # A feature with zero variance carries no information; leaving its
        # scale at 0 would divide by zero. 1.0 makes it a constant column
        # that the ridge penalty then flattens harmlessly.
        scale = np.where(scale < 1e-12, 1.0, scale)

        exps = _exponents(X.shape[1], degree)
        A = design_matrix((X - mean) / scale, exps)

        penalty = np.eye(A.shape[1])
        penalty[0, 0] = 0.0             # never shrink the intercept
        gram = A.T @ A + ridge * penalty
        try:
            coef = np.linalg.solve(gram, A.T @ y)
        except np.linalg.LinAlgError:
            # Can happen inside a cross-validation fold that leaves a
            # degenerate point layout (e.g. the held-out point was the only
            # one off a straight line). Least-squares gives the minimum-norm
            # answer instead of failing the whole selection run.
            coef = np.linalg.lstsq(gram, A.T @ y, rcond=None)[0]

        return cls(
            feature_set=feature_set,
            degree=degree,
            ridge=ridge,
            coef=coef,
            mean=mean,
            scale=scale,
            screen_width=screen_width,
            screen_height=screen_height,
            n_samples=int(X.shape[0]),
            **meta,
        )

    # ------------------------------------------------------------------

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Features -> normalised screen coords, (n, 2), unclipped."""
        X = np.atleast_2d(np.asarray(X, dtype=float))
        A = design_matrix((X - self.mean) / self.scale, self.exponents)
        return A @ self.coef

    def predict_one(
        self,
        left: Optional[Tuple[float, float]],
        right: Optional[Tuple[float, float]],
        clip: bool = True,
    ) -> Optional[Tuple[float, float, bool]]:
        """One frame's pupils -> (x_norm, y_norm, in_bounds), or None.

        This is the live path. It is a feature build, a small matrix
        multiply, and a clamp -- no allocation of consequence, no retraining,
        nothing that scales with session length.

        Returns None when neither eye was usable this frame, which is the
        caller's cue to emit an invalid GazePoint rather than to guess.

        `in_bounds` is reported separately from the clipped value on purpose:
        a prediction off the edge of the screen is a real signal (the
        participant looked away, or calibration has drifted), and silently
        clamping it to the border would disguise that as a genuine fixation
        on whatever UI element happens to live at the screen edge.
        """
        feats = features_from_pupils(left, right, self.feature_set)
        if feats is None:
            return None

        raw = self.predict(np.asarray([feats], dtype=float))[0]
        in_bounds = bool(0.0 <= raw[0] <= 1.0 and 0.0 <= raw[1] <= 1.0)
        x, y = (float(np.clip(raw[0], 0.0, 1.0)), float(np.clip(raw[1], 0.0, 1.0))) \
            if clip else (float(raw[0]), float(raw[1]))
        return x, y, in_bounds

    # ------------------------------------------------------------------
    # persistence -- plain JSON, so a model is inspectable and diffable

    def to_dict(self) -> Dict:
        return {
            "format_version": self.format_version,
            "feature_set": self.feature_set,
            "degree": self.degree,
            "ridge": self.ridge,
            "coef": self.coef.tolist(),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "n_points": self.n_points,
            "n_samples": self.n_samples,
            "metrics": self.metrics,
            "selection": self.selection,
            "trained_at": self.trained_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "GazeModel":
        version = d.get("format_version", 0)
        if version != MODEL_FORMAT_VERSION:
            raise ValueError(
                f"gaze model format v{version}, this build reads "
                f"v{MODEL_FORMAT_VERSION} -- retrain the session"
            )
        return cls(
            feature_set=d["feature_set"],
            degree=d["degree"],
            ridge=d["ridge"],
            coef=np.asarray(d["coef"], dtype=float),
            mean=np.asarray(d["mean"], dtype=float),
            scale=np.asarray(d["scale"], dtype=float),
            screen_width=d["screen_width"],
            screen_height=d["screen_height"],
            session_id=d.get("session_id", ""),
            participant_id=d.get("participant_id", ""),
            n_points=d.get("n_points", 0),
            n_samples=d.get("n_samples", 0),
            metrics=d.get("metrics", {}),
            selection=d.get("selection", {}),
            trained_at=d.get("trained_at", 0.0),
            format_version=version,
        )

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "GazeModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def max_degree_for(feature_set: str, n_points: int) -> int:
    """Highest degree whose parameter count stays safely under n_points.

    The cap is n_points - 2. At n_terms == n_points the fit interpolates the
    calibration targets exactly and its training error is zero regardless of
    how wrong it is everywhere else; the margin keeps the system genuinely
    over-determined. This is why a 9-point session gets a lower ceiling than
    a 16-point one, automatically.
    """
    d = FEATURE_DIMS[feature_set]
    budget = n_points - 2
    best = 0
    for degree in range(1, 4):
        if n_terms(d, degree) <= budget:
            best = degree
    return best


__all__ = [
    "GazeModel",
    "DEFAULT_RIDGE",
    "MODEL_FORMAT_VERSION",
    "design_matrix",
    "n_terms",
    "max_degree_for",
]
