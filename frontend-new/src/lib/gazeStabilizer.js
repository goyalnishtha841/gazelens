/**
 * Fixation-locked cursor smoothing for the live gaze dot.
 *
 * A webcam gaze estimate jumps around by roughly 50-100 px from one frame to
 * the next even while the eyes hold perfectly still, so a cursor that follows
 * every frame flutters. The eyes themselves don't drift: they hold still
 * (a fixation) and then jump (a saccade). This mirrors that:
 *
 *   - while new points land within `radius` of the current fixation, the
 *     cursor sits on the running median of that fixation and barely moves;
 *   - a single far-away point is treated as noise and ignored;
 *   - `confirm` far-away points in a row that agree with each other are a
 *     real eye movement, and the cursor jumps to them at once.
 *
 * Display only. The server keeps the raw stream for fixation detection.
 * Coordinates are normalised [0,1]; `aspect` (width / height of the stage)
 * makes the radius round on screen.
 */
export class GazeStabilizer {
  constructor({ radius = 0.1, window = 10, confirm = 2 } = {}) {
    this.radius = radius;
    this.window = window;
    this.confirm = confirm;
    this.reset();
  }

  reset() {
    this.cluster = [];
    this.pending = [];
    this.anchor = null;
  }

  _dist(a, b, aspect) {
    return Math.hypot((a.x - b.x) * aspect, a.y - b.y);
  }

  _median(points) {
    const xs = points.map((p) => p.x).sort((a, b) => a - b);
    const ys = points.map((p) => p.y).sort((a, b) => a - b);
    const m = Math.floor(xs.length / 2);
    return xs.length % 2
      ? { x: xs[m], y: ys[m] }
      : { x: (xs[m - 1] + xs[m]) / 2, y: (ys[m - 1] + ys[m]) / 2 };
  }

  /** Feed one raw point; returns { x, y, jumped }. */
  push(x, y, aspect = 16 / 9) {
    const p = { x, y };
    if (!this.anchor) {
      this.cluster = [p];
      this.anchor = p;
      return { ...p, jumped: true };
    }

    if (this._dist(p, this.anchor, aspect) <= this.radius) {
      this.pending = [];
      this.cluster.push(p);
      if (this.cluster.length > this.window) this.cluster.shift();
      this.anchor = this._median(this.cluster);
      return { ...this.anchor, jumped: false };
    }

    // Outside the fixation: wait for agreement before moving.
    const last = this.pending[this.pending.length - 1];
    if (last && this._dist(p, last, aspect) > this.radius * 1.5) this.pending = [];
    this.pending.push(p);
    if (this.pending.length >= this.confirm) {
      this.cluster = this.pending;
      this.pending = [];
      this.anchor = this._median(this.cluster);
      return { ...this.anchor, jumped: true };
    }
    return { ...this.anchor, jumped: false };
  }
}
