import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * Full-page background: a faint grid of dots that heats up where attention
 * goes -- the product's own idea, as the backdrop.
 *
 *   - the visitor's pointer acts as a gaze: dots warm up around it, along
 *     the heatmap scale (blue -> teal -> amber -> coral), and cool down
 *   - two "virtual eyes" wander the page the way real eyes move: hold on a
 *     spot for a moment, then jump. They leave the same fading heat, so the
 *     page is alive on touch screens and before the mouse moves
 *
 * Fixed to the viewport behind every section. Heat is accumulated per grid
 * cell from a short trail of recent points, so the cost is the trail length
 * times a small neighbourhood, not the whole grid. Reduced motion: a still
 * grid with one soft hotspot.
 */

const SPACING = 30;          // px between dots
const SIGMA = 70;            // heat radius, px
const TRAIL_MS = 1600;       // how long heat lingers
const MAX_TRAIL = 90;
const EYES = 2;

function readTheme() {
  const cs = getComputedStyle(document.documentElement);
  const rgb = (name) => cs.getPropertyValue(name).trim().split(/\s+/).map(Number);
  return {
    dark: document.documentElement.classList.contains("dark"),
    base: rgb("--color-text-secondary"),
    ramp: [rgb("--color-cool"), rgb("--color-accent"), rgb("--color-amber"), rgb("--color-coral")],
  };
}

function rampColor(ramp, v) {
  const x = Math.min(0.999, Math.max(0, v)) * (ramp.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = ramp[i];
  const b = ramp[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

function newTarget(w, h) {
  return { x: w * (0.1 + Math.random() * 0.8), y: h * (0.12 + Math.random() * 0.76) };
}

export default function GazeField({ className = "" }) {
  const ref = useRef(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    let w = 0;
    let h = 0;
    let cols = 0;
    let rows = 0;
    let heat = new Float32Array(0);
    let theme = readTheme();
    let raf = 0;
    const trail = [];
    const eyes = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(w / SPACING) + 1;
      rows = Math.ceil(h / SPACING) + 1;
      heat = new Float32Array(cols * rows);
      eyes.length = 0;
      for (let i = 0; i < EYES; i += 1) {
        const p = newTarget(w, h);
        eyes.push({ ...p, tx: p.x, ty: p.y, holdUntil: 0 });
      }
    };

    const addPoint = (x, y, weight, now) => {
      trail.push({ x, y, weight, t: now });
      if (trail.length > MAX_TRAIL) trail.shift();
    };

    let lastPointer = 0;
    const onPointer = (e) => {
      const now = performance.now();
      if (now - lastPointer < 24) return;
      lastPointer = now;
      addPoint(e.clientX, e.clientY, 1, now);
    };

    const stepEyes = (now) => {
      for (const eye of eyes) {
        if (now > eye.holdUntil) {
          // saccade: pick a new spot, hold 0.4-1.4 s once there
          const t = newTarget(w, h);
          eye.tx = t.x;
          eye.ty = t.y;
          eye.holdUntil = now + 400 + Math.random() * 1000 + 350;
        }
        eye.x += (eye.tx - eye.x) * 0.18;
        eye.y += (eye.ty - eye.y) * 0.18;
        // tiny jitter while fixating, like a real eye
        const jx = (Math.random() - 0.5) * 6;
        const jy = (Math.random() - 0.5) * 6;
        if (Math.hypot(eye.tx - eye.x, eye.ty - eye.y) < 4 && Math.random() < 0.5) {
          addPoint(eye.x + jx, eye.y + jy, 0.45, now);
        }
      }
    };

    const draw = (now) => {
      heat.fill(0);
      const reach = Math.ceil((SIGMA * 2.6) / SPACING);
      const inv2s2 = 1 / (2 * SIGMA * SIGMA);
      for (let k = trail.length - 1; k >= 0; k -= 1) {
        const p = trail[k];
        const age = now - p.t;
        if (age > TRAIL_MS) {
          trail.splice(0, k + 1);
          break;
        }
        const fade = p.weight * (1 - age / TRAIL_MS) ** 2;
        const cx = Math.round(p.x / SPACING);
        const cy = Math.round(p.y / SPACING);
        for (let gy = Math.max(0, cy - reach); gy <= Math.min(rows - 1, cy + reach); gy += 1) {
          for (let gx = Math.max(0, cx - reach); gx <= Math.min(cols - 1, cx + reach); gx += 1) {
            const dx = gx * SPACING - p.x;
            const dy = gy * SPACING - p.y;
            heat[gy * cols + gx] += fade * Math.exp(-(dx * dx + dy * dy) * inv2s2) * 0.22;
          }
        }
      }

      ctx.clearRect(0, 0, w, h);
      const [br, bg, bb] = theme.base;
      const baseAlpha = theme.dark ? 0.16 : 0.2;
      ctx.fillStyle = `rgba(${br},${bg},${bb},${baseAlpha})`;
      for (let gy = 0; gy < rows; gy += 1) {
        for (let gx = 0; gx < cols; gx += 1) {
          if (heat[gy * cols + gx] < 0.02) ctx.fillRect(gx * SPACING - 0.75, gy * SPACING - 0.75, 1.5, 1.5);
        }
      }
      for (let gy = 0; gy < rows; gy += 1) {
        for (let gx = 0; gx < cols; gx += 1) {
          const v = Math.min(1, heat[gy * cols + gx]);
          if (v < 0.02) continue;
          const [r, g, b] = rampColor(theme.ramp, v);
          ctx.fillStyle = `rgba(${r | 0},${g | 0},${b | 0},${Math.min(1, 0.25 + v * (theme.dark ? 0.85 : 0.75))})`;
          ctx.beginPath();
          ctx.arc(gx * SPACING, gy * SPACING, 1 + v * 2.4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    const loop = (now) => {
      stepEyes(now);
      draw(now);
      raf = requestAnimationFrame(loop);
    };

    resize();
    if (reduce) {
      const now = performance.now();
      addPoint(w * 0.5, h * 0.35, 3, now);
      draw(now);
    } else {
      raf = requestAnimationFrame(loop);
      window.addEventListener("pointermove", onPointer, { passive: true });
    }
    window.addEventListener("resize", resize);
    const mo = new MutationObserver(() => {
      theme = readTheme();
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("resize", resize);
      mo.disconnect();
    };
  }, [reduce]);

  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none fixed inset-0 ${className}`} />;
}
