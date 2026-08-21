/** Shared visual primitives -- see design brief §14. Thin border, tiny
 * radius, almost no shadow, lots of internal breathing room. */

import { useEffect, useRef, useState } from "react";

/** Animates a number from 0 up to `target` with an ease-out curve. Used by
 * Stat (below) and the Critic confidence score on SessionReport -- both are
 * headline numbers a report/dashboard wants to feel "counted," not just
 * appear. Returns `target` unchanged on the very first paint's initial
 * value so non-numeric callers (a string value passed into Stat) can skip
 * this entirely rather than showing a meaningless 0. */
export function useCountUp(target, durationMs = 900) {
  const [value, setValue] = useState(0);
  const targetRef = useRef(target);
  targetRef.current = target;

  useEffect(() => {
    if (typeof target !== "number" || Number.isNaN(target)) return;
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(targetRef.current * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return value;
}

export function Card({ children, className = "", ...rest }) {
  return (
    <div
      className={`group rounded-card border border-border bg-surface p-6 transition-shadow duration-300 hover:border-accent/30 hover:shadow-[0_0_0_1px_rgb(var(--color-accent)/0.12),0_0_28px_-10px_rgb(var(--color-accent)/0.45)] ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

/** Small uppercase technical label -- does a lot of the typographic work
 * described in the brief (§5) instead of decorative icons. */
export function Label({ children, className = "" }) {
  return (
    <span
      className={`font-mono text-[11px] uppercase tracking-label text-text-secondary ${className}`}
    >
      {children}
    </span>
  );
}

/** One statistic, editorial style -- big number, small label underneath,
 * thin rule. Used across Dashboard/Analytics rather than a chart-heavy card.
 *
 * `value` isn't always a short number -- SessionReport passes element IDs
 * like "chart_widget" too. A grid item won't shrink below its content's
 * intrinsic width by default, so a long unbroken string at 40px used to
 * overflow its column and visually smear into the next one. `min-w-0` lets
 * the column actually shrink; the size step and `truncate` (with a `title`
 * fallback) keep long values legible instead of overlapping regardless of
 * what gets passed in. */
export function Stat({ value, label, accent = false, delay = 0 }) {
  const isNumber = typeof value === "number";
  const counted = useCountUp(isNumber ? value : 0);
  const displayValue = isNumber ? counted : value;
  const text = String(value);
  const sizeClass = text.length > 8 ? "text-[22px]" : "text-[40px]";
  return (
    <div className="min-w-0" style={{ animation: "count-up-fade 420ms ease-out both", animationDelay: `${delay}ms` }}>
      <div
        title={text.length > 8 ? text : undefined}
        className={`truncate font-sans ${sizeClass} font-semibold leading-tight tracking-tight tabular-nums ${accent ? "text-accent" : "text-text-primary"}`}
      >
        {displayValue}
      </div>
      <div className="mt-3 border-t border-border pt-2">
        <Label>{label}</Label>
      </div>
    </div>
  );
}

export function SectionLabel({ index, children }) {
  return (
    <div className="mb-4 flex items-center gap-2">
      <Label>
        {index != null ? `${String(index).padStart(2, "0")} / ` : ""}
        {children}
      </Label>
    </div>
  );
}
