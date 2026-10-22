import { useMemo } from "react";

/**
 * The product's one recurring visual motif (see design brief): a gaze point
 * moving across a surface. Two modes share the same visual language --
 * "decorative" is ambient motion for empty/marketing surfaces, "data" plots
 * real fixation points.
 *
 * Dots are real DOM elements (border-radius circles), not SVG shapes, on
 * purpose: an SVG viewBox stretched with preserveAspectRatio="none" to fill
 * a non-square container (every card here is 16:9 or 16:10) scales X and Y
 * unevenly, which turns <circle> into a visibly squashed ellipse. Position
 * as a CSS percentage instead and the shape stays a circle no matter the
 * container's aspect ratio -- only the connecting line stays SVG, since a
 * stretched straight line is still a straight line.
 */

function wanderPath(seed, count) {
  let s = seed;
  const rand = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  const pts = [{ x: 15 + rand() * 20, y: 20 + rand() * 20 }];
  for (let i = 1; i < count; i++) {
    const prev = pts[i - 1];
    pts.push({
      x: Math.min(90, Math.max(10, prev.x + (rand() - 0.35) * 28)),
      y: Math.min(85, Math.max(15, prev.y + (rand() - 0.4) * 22)),
    });
  }
  return pts;
}

function toSvgPath(points) {
  return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
}

/** Ambient decoration: a dot drifting a slow wander path. No real data.
 * `large`: scales dots/stroke up for hero-scale use. `edgeToEdge`: pins the
 * first point to the left edge and the last to the right edge (for a thin
 * bar with no visible box around it -- SignIn/SignUp), and plays as a
 * back-and-forth sweep instead of a closed loop, so it doesn't need a
 * container boundary to read as intentional. */
export function GazeTrailDecorative({ seed = 7, points: count = 6, className = "", large = false, edgeToEdge = false }) {
  const points = useMemo(() => {
    const pts = wanderPath(seed, count);
    if (edgeToEdge) {
      pts[0] = { ...pts[0], x: 0 };
      pts[pts.length - 1] = { ...pts[pts.length - 1], x: 100 };
    }
    return pts;
  }, [seed, count, edgeToEdge]);
  const path = useMemo(() => toSvgPath(points), [points]);
  const name = `gaze-wander-${seed}-${count}${edgeToEdge ? "-edge" : ""}`;
  const duration = 6 + count * 1.5;

  // edgeToEdge sweeps left-to-right once and reverses (CSS alternate) rather
  // than closing the loop back to point 0 -- closing it would jump straight
  // across the full width every cycle instead of drifting back naturally.
  const sequence = edgeToEdge ? points : points.concat(points[0]);
  const steps = sequence
    .map((p, i, arr) => `${((i / (arr.length - 1)) * 100).toFixed(1)}% { left: ${p.x}%; top: ${p.y}%; }`)
    .join("\n");

  const dotSize = large ? "h-4 w-4" : "h-1.5 w-1.5";
  const headSize = large ? "h-7 w-7" : "h-2.5 w-2.5";
  const headGlow = large
    ? "shadow-[0_0_28px_6px_currentColor]"
    : "shadow-[0_0_12px_2px_currentColor]";
  const animationStyle = edgeToEdge
    ? { animation: `${name} ${duration}s ease-in-out infinite alternate` }
    : { animation: `${name} ${duration}s ease-in-out infinite` };

  return (
    <div className={`absolute inset-0 ${edgeToEdge ? "" : "overflow-hidden"} ${className}`} aria-hidden="true">
      <style>{`@keyframes ${name} { ${steps} }`}</style>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
        <path d={path} fill="none" stroke="currentColor" strokeWidth={large ? "0.5" : "0.3"} opacity="0.25" />
      </svg>
      {points.map((p, i) => (
        <span
          key={i}
          className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-current ${dotSize}`}
          style={{ left: `${p.x}%`, top: `${p.y}%`, opacity: 0.15 + (i / points.length) * 0.3 }}
        />
      ))}
      <span
        className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-current ${headSize} ${headGlow}`}
        style={animationStyle}
      />
    </div>
  );
}

/**
 * Real fixation points over a surface (screenshot, mockup). `points`:
 * [{ x, y, weight? }] normalised [0,1] to the container. First point is
 * dimmest (earliest), last is brightest (most recent) -- mirrors the report
 * PDF's own green-first/red-last gaze-path convention.
 */
export function GazePoints({ points, showPath = true, className = "" }) {
  if (!points?.length) return null;
  const pct = points.map((p) => ({ x: p.x * 100, y: p.y * 100, weight: p.weight ?? 1 }));
  const path = toSvgPath(pct);

  return (
    <div className={`absolute inset-0 ${className}`}>
      {showPath && (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
          <path d={path} fill="none" className="stroke-accent" strokeWidth="0.2" opacity="0.3" strokeDasharray="1 1.2" />
        </svg>
      )}
      {pct.map((p, i) => {
        const isLast = i === pct.length - 1;
        const size = 8 + p.weight * 8 + (isLast ? 4 : 0);
        return (
          <span
            key={i}
            className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent"
            style={{
              left: `${p.x}%`,
              top: `${p.y}%`,
              width: size,
              height: size,
              opacity: isLast ? 0.9 : 0.25 + (i / pct.length) * 0.35,
              boxShadow: isLast ? "0 0 14px 3px rgb(var(--color-accent) / 0.5)" : "none",
              animation: "gaze-appear 420ms ease-out both",
              animationDelay: `${i * 55}ms`,
            }}
          />
        );
      })}
    </div>
  );
}
