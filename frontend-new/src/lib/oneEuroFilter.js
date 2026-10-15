/**
 * One-Euro filter (Casiez, Roussel & Vogel, CHI 2012) for the on-screen gaze
 * cursor. Heavy smoothing while the eyes are still (kills landmark jitter
 * during a fixation), light smoothing during fast movement (keeps saccades
 * from lagging). Display only: the server stores the raw stream, because
 * fixation detection needs real saccade timing.
 *
 *   minCutoff -- Hz; lower = steadier at rest, laggier
 *   beta      -- how quickly smoothing relaxes as speed rises
 */
function alpha(cutoff, dt) {
  const tau = 1 / (2 * Math.PI * cutoff);
  return 1 / (1 + tau / dt);
}

class OneEuro1D {
  constructor(minCutoff, beta, dCutoff) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    this.reset();
  }

  reset() {
    this.x = null;
    this.dx = 0;
    this.t = null;
  }

  filter(value, t) {
    if (this.x === null) {
      this.x = value;
      this.t = t;
      return value;
    }
    const dt = Math.max(1e-3, t - this.t);
    this.t = t;
    const dxRaw = (value - this.x) / dt;
    this.dx += alpha(this.dCutoff, dt) * (dxRaw - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x += alpha(cutoff, dt) * (value - this.x);
    return this.x;
  }
}

export class OneEuroFilter2D {
  constructor({ minCutoff = 1.0, beta = 0.6, dCutoff = 1.0 } = {}) {
    this.fx = new OneEuro1D(minCutoff, beta, dCutoff);
    this.fy = new OneEuro1D(minCutoff, beta, dCutoff);
  }

  reset() {
    this.fx.reset();
    this.fy.reset();
  }

  /** x, y in normalised [0,1] coordinates; t in seconds. */
  filter(x, y, t) {
    return { x: this.fx.filter(x, t), y: this.fy.filter(y, t) };
  }
}
