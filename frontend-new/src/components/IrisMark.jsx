import { motion, useReducedMotion } from "framer-motion";

/**
 * The GazeLens mark: a lens ring with an off-centre pupil -- an eye that is
 * looking somewhere. Doubles as the logo, the gaze cursor and a loader.
 *
 * `wander` lets the pupil drift between a few gaze directions, slowly,
 * as if reading. Off for reduced-motion users.
 */
export default function IrisMark({ size = 28, wander = false, className = "" }) {
  const reduce = useReducedMotion();
  // a transform, not cx/cy: cheaper, and SVG attribute keyframes come
  // through as undefined in this framer-motion version
  const animate = wander && !reduce
    ? { x: [0, -2, -3.5, -1, 0], y: [0, 1.5, 0.3, 3.5, 0] }
    : undefined;
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="12" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
      <motion.circle
        cx="19" cy="13.5" r="3.6" fill="currentColor"
        animate={animate}
        transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
      />
    </svg>
  );
}

/** Logo lockup: mark + wordmark. `large` is the landing-page size, where
 *  the name is the first thing people should read. */
export function Wordmark({ className = "", large = false }) {
  return (
    <span className={`inline-flex items-center ${large ? "gap-2.5" : "gap-2"} ${className}`}>
      <span className={large ? "rounded-full drop-shadow-[0_0_12px_rgb(var(--color-accent)/0.55)]" : ""}>
        <IrisMark size={large ? 30 : 26} wander className="text-accent" />
      </span>
      <span className={`font-display font-extrabold tracking-[-0.02em] text-text-primary ${large ? "text-[22px]" : "text-[19px]"}`}>
        Gaze
        <span className={`text-accent ${large ? "drop-shadow-[0_0_14px_rgb(var(--color-accent)/0.55)]" : ""}`}>Lens</span>
      </span>
    </span>
  );
}
