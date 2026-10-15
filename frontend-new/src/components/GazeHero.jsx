import { useEffect, useRef, useState } from "react";
import {
  AnimatePresence, animate, motion, useInView, useMotionValue, useReducedMotion, useTransform,
} from "framer-motion";
import IrisMark from "./IrisMark.jsx";

/**
 * The landing hero, coded rather than a picture: a participant's gaze
 * walking a product page, heat building where it dwells, the elements it
 * was attributed to, and the finding GazeLens draws from it.
 *
 * The finding is the one the real agent chain would produce for this path:
 * the "Add to cart" CTA is first looked at after the 5 s threshold
 * (agents/rules.py CTA_TTFF_DELAYED_THRESHOLD_SECONDS), which Agent 1 flags as
 * delayed discovery and the report calls "Primary action discovered late".
 *
 * Coordinates are percentages of the mock page (16:10).
 */

// Each fixation: where (x, y %), how long (s), which element, and how wide
// the gaze spread was there (blob radius, % of page width).
const SCANPATH = [
  { x: 67, y: 22, dur: 0.9, el: "Product title", r: 9 },
  { x: 26, y: 46, dur: 1.5, el: "Product photo", r: 13 },
  { x: 60, y: 33, dur: 0.6, el: "Price", r: 7 },
  { x: 31, y: 57, dur: 1.0, el: "Product photo", r: 11 },
  { x: 61, y: 45, dur: 0.5, el: "Colour options", r: 7 },
  { x: 68, y: 56, dur: 0.7, el: "Description", r: 8 },
  { x: 67, y: 72, dur: 0.6, el: "Add to cart", r: 8 },
];
const SACCADE_S = 0.15;           // simulated travel time between fixations
const CTA_STEP = SCANPATH.length - 1;
const CTA_TTFF = SCANPATH.slice(0, CTA_STEP).reduce((t, f) => t + f.dur + SACCADE_S, 0);
const TTFF_THRESHOLD = 5;

// Attributed elements (x, y, w, h in %), drawn as dashed AOI boxes at the end.
const AOIS = [
  { label: "Product photo", x: 5, y: 16, w: 42, h: 64 },
  { label: "Title", x: 53, y: 16, w: 40, h: 11 },
  { label: "Price", x: 53, y: 29, w: 18, h: 8 },
  { label: "Colour", x: 53, y: 40, w: 22, h: 9 },
  { label: "Add to cart", x: 53, y: 66, w: 30, h: 10 },
];

const PLAY_SPEED = 1.15;          // real seconds per simulated second
const HOLD_FINDING_MS = 4200;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function GazeHero() {
  const reduce = useReducedMotion();
  const rootRef = useRef(null);
  const inView = useInView(rootRef, { margin: "-10% 0px" });
  const x = useMotionValue(SCANPATH[0].x);
  const y = useMotionValue(SCANPATH[0].y);
  const left = useTransform(x, (v) => `${v}%`);
  const top = useTransform(y, (v) => `${v}%`);
  const [visited, setVisited] = useState(reduce ? SCANPATH.length : 0);
  const [phase, setPhase] = useState(reduce ? "done" : "tracking"); // tracking | attribute | done
  const [clock, setClock] = useState(0);

  useEffect(() => {
    if (reduce || !inView) return undefined;
    let cancelled = false;

    async function run() {
      while (!cancelled) {
        setVisited(0);
        setPhase("tracking");
        setClock(0);
        x.set(50);
        y.set(50);
        await wait(500);
        let t = 0;
        for (let i = 0; i < SCANPATH.length && !cancelled; i += 1) {
          const f = SCANPATH[i];
          const opts = { type: "spring", stiffness: 140, damping: 18, mass: 0.6 };
          animate(x, f.x, opts);
          await animate(y, f.y, opts);
          if (cancelled) return;
          t += i === 0 ? 0 : SACCADE_S;
          setClock(t);
          setVisited(i + 1);
          await wait(f.dur * 1000 * PLAY_SPEED);
          t += f.dur;
          setClock(t);
        }
        if (cancelled) return;
        setPhase("attribute");
        await wait(1100);
        if (cancelled) return;
        setPhase("done");
        await wait(HOLD_FINDING_MS);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [reduce, inView, x, y]);

  const current = visited > 0 ? SCANPATH[visited - 1] : null;
  const showAois = phase !== "tracking";

  return (
    <div ref={rootRef} className="relative">
      {/* soft heat glow behind the frame */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-10 -z-10 opacity-60 blur-3xl"
        style={{
          background:
            "radial-gradient(40% 45% at 30% 40%, rgb(var(--color-accent) / 0.22), transparent 70%), radial-gradient(35% 40% at 75% 70%, rgb(var(--color-amber) / 0.18), transparent 70%)",
        }}
      />

      <div className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-[0_24px_60px_-20px_rgba(0,0,0,0.55)]">
        {/* browser chrome */}
        <div className="flex items-center gap-3 border-b border-border bg-raised px-4 py-2.5">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-text-secondary/30" />
            <span className="h-2.5 w-2.5 rounded-full bg-text-secondary/30" />
            <span className="h-2.5 w-2.5 rounded-full bg-text-secondary/30" />
          </div>
          <div className="min-w-0 flex-1 truncate rounded-md bg-bg/60 px-3 py-1 font-mono text-[11px] text-text-secondary">
            shop.example.com/trail-headphones
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-coral/40 px-2.5 py-0.5 font-mono text-[10px] text-coral">
            <span className={`h-1.5 w-1.5 rounded-full bg-coral ${phase === "tracking" && !reduce ? "animate-pulse" : ""}`} />
            {phase === "tracking" && !reduce ? "REC" : "DONE"} {clock.toFixed(1).padStart(4, "0")}s
          </div>
        </div>

        {/* the page being tested: a believable store, in a light or dark
            version to match the theme around it */}
        <div
          role="img"
          aria-label="Animated example: someone's eyes move over a product page, colour builds up where they looked, and GazeLens points out that the Add to cart button was noticed late."
          className="relative aspect-[16/10] w-full select-none overflow-hidden bg-[#F7F5F0] text-[#1d232b] dark:bg-[#111A26] dark:text-[#E6EDF5]"
          style={{ containerType: "inline-size" }}
        >
          <MockProductPage />

          {/* heat: one blob per fixation, strength from dwell time */}
          <div className="pointer-events-none absolute inset-0">
            {SCANPATH.slice(0, visited).map((f, i) => (
              <motion.div
                key={i}
                // multiply darkens on the light page; screen makes the heat
                // glow on the dark one
                className="absolute rounded-full mix-blend-multiply dark:mix-blend-screen"
                initial={{ opacity: 0, scale: 0.4 }}
                animate={{ opacity: Math.min(0.9, 0.3 + f.dur * 0.38), scale: 1 }}
                transition={{ duration: reduce ? 0 : f.dur * PLAY_SPEED, ease: "easeOut" }}
                style={{
                  left: `${f.x - f.r}%`,
                  top: `${f.y - f.r * 1.6}%`,
                  width: `${f.r * 2}%`,
                  height: `${f.r * 3.2}%`,
                  background:
                    "radial-gradient(closest-side, rgba(255,107,90,0.85), rgba(255,181,71,0.6) 35%, rgba(46,230,197,0.35) 62%, rgba(91,140,255,0.15) 80%, transparent)",
                }}
              />
            ))}
          </div>

          {/* scanpath: numbered fixations joined in order */}
          <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 160 100" aria-hidden="true">
            {SCANPATH.slice(1, visited).map((f, i) => {
              const prev = SCANPATH[i];
              return (
                <motion.line
                  key={`l${i}`}
                  x1={prev.x * 1.6} y1={prev.y} x2={f.x * 1.6} y2={f.y}
                  className="stroke-[#0A0E14] dark:stroke-[#E8EEF5]"
                  strokeOpacity="0.55" strokeWidth="0.45" strokeDasharray="1.6 1.2"
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: reduce ? 0 : 0.25 }}
                />
              );
            })}
            {SCANPATH.slice(0, visited).map((f, i) => (
              <motion.g
                key={`n${i}`}
                initial={{ opacity: 0, scale: 0.3 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 22 }}
                style={{ transformOrigin: `${f.x * 1.6}px ${f.y}px` }}
              >
                <circle cx={f.x * 1.6} cy={f.y} r="2.6" className="fill-[#0A0E14] dark:fill-[#2EE6C5]" />
                <text x={f.x * 1.6} y={f.y + 0.95} textAnchor="middle" fontSize="2.6" fontWeight="700" fontFamily="Outfit, sans-serif" className="fill-[#2EE6C5] dark:fill-[#0A0E14]">
                  {i + 1}
                </text>
              </motion.g>
            ))}
          </svg>

          {/* attributed elements */}
          <AnimatePresence>
            {showAois && AOIS.map((a, i) => (
              <motion.div
                key={a.label}
                className="pointer-events-none absolute rounded-[3px] border border-dashed border-[#0E9F88]"
                style={{ left: `${a.x}%`, top: `${a.y}%`, width: `${a.w}%`, height: `${a.h}%` }}
                initial={{ opacity: 0, scale: 1.04 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ delay: reduce ? 0 : i * 0.08, duration: 0.3 }}
              >
                <span
                  className="absolute -top-[1px] left-[-1px] -translate-y-full rounded-t-[3px] bg-[#0E9F88] px-1.5 py-[1px] font-mono text-white"
                  style={{ fontSize: "1.25cqw" }}
                >
                  {a.label}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* the live gaze cursor */}
          {!reduce && phase === "tracking" && (
            <motion.div
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2 text-[#0E9F88]"
              style={{ left, top }}
            >
              <div className="rounded-full bg-[#2EE6C5]/15 p-0.5 shadow-[0_0_18px_4px_rgba(46,230,197,0.45)]">
                <IrisMark size={30} />
              </div>
            </motion.div>
          )}

          {/* live readout */}
          <div className="absolute bottom-[4%] left-[2.5%] z-10 rounded-md bg-[#0A0E14]/85 px-2 py-1 font-mono text-white backdrop-blur" style={{ fontSize: "1.3cqw" }}>
            {phase === "tracking"
              ? current ? <>looking at <span className="text-[#2EE6C5]">{current.el}</span></> : "watching where you look"
              : <>7 places looked at · <span className="text-[#2EE6C5]">5 parts of the page</span></>}
          </div>
        </div>
      </div>

      {/* the finding it leads to */}
      <AnimatePresence>
        {phase === "done" && (
          <motion.div
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ type: "spring", stiffness: 260, damping: 24 }}
            className="absolute -bottom-8 right-3 z-20 w-[min(330px,85%)] rounded-card border border-amber/40 bg-raised p-3.5 shadow-[0_18px_40px_-12px_rgba(0,0,0,0.6)] sm:-right-6"
          >
            <div className="flex items-center gap-2 text-[12px] font-semibold text-amber">
              <span className="h-1.5 w-1.5 rounded-full bg-amber" /> Worth fixing
            </div>
            <p className="mt-1 text-[15px] font-semibold leading-snug text-text-primary">
              The “Add to cart” button was noticed late
            </p>
            <p className="mt-1 text-[13px] leading-snug text-text-secondary">
              People first looked at it after {CTA_TTFF.toFixed(1)} seconds. Under {TTFF_THRESHOLD} is better.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* measurement-quality chip */}
      <div className="absolute -left-4 bottom-[18%] z-20 hidden rounded-full border border-accent/40 bg-raised px-3.5 py-1.5 text-[12px] font-medium text-text-primary shadow-lg sm:block">
        <span className="text-accent">●</span> tracking accuracy: good
      </div>
    </div>
  );
}

/** The page under test: a plain, believable product page. */
function MockProductPage() {
  const fs = (cqw) => ({ fontSize: `${cqw}cqw` });
  return (
    <div className="absolute inset-0" aria-hidden="true">
      {/* site nav */}
      <div className="absolute inset-x-0 top-0 flex h-[10%] items-center justify-between bg-white px-[5%] shadow-[0_1px_0_#e7e3da] dark:bg-[#0D141E] dark:shadow-[0_1px_0_#1f2a3a]">
        <span className="font-semibold tracking-tight" style={fs(1.9)}>Trailhead</span>
        <span className="flex gap-[3cqw] text-[#5b636d] dark:text-[#9AA9BC]" style={fs(1.35)}>
          <span>Audio</span><span>Outdoor</span><span>Deals</span><span>Cart (0)</span>
        </span>
      </div>

      {/* product photo */}
      <div className="absolute left-[5%] top-[16%] flex h-[64%] w-[42%] items-center justify-center rounded-[1cqw] bg-gradient-to-br from-[#e9e4da] to-[#d9d2c4] dark:from-[#1c2738] dark:to-[#141e2c]">
        <svg viewBox="0 0 120 100" className="w-[62%]">
          <path d="M22 62 C22 25 98 25 98 62" fill="none" className="stroke-[#2b3138] dark:stroke-[#c9d3df]" strokeWidth="7" strokeLinecap="round" />
          <rect x="12" y="55" width="22" height="32" rx="9" className="fill-[#2b3138] dark:fill-[#c9d3df]" />
          <rect x="86" y="55" width="22" height="32" rx="9" className="fill-[#2b3138] dark:fill-[#c9d3df]" />
          <rect x="17" y="60" width="12" height="22" rx="5" className="fill-[#4a7c74] dark:fill-[#2b8f80]" />
          <rect x="91" y="60" width="12" height="22" rx="5" className="fill-[#4a7c74] dark:fill-[#2b8f80]" />
        </svg>
      </div>

      {/* details */}
      <div className="absolute left-[53%] top-[17%] w-[40%]">
        <div className="text-[#7a828c] dark:text-[#8A9BB0]" style={fs(1.2)}>TRAILHEAD AUDIO</div>
        <div className="mt-[0.4cqw] font-semibold leading-tight tracking-tight" style={fs(2.5)}>Wireless Trail Headphones</div>
      </div>
      <div className="absolute left-[53%] top-[30%] flex items-baseline gap-[1.2cqw]">
        <span className="font-semibold" style={fs(2.1)}>$129.00</span>
        <span className="text-[#c98a1b]" style={fs(1.3)}>★★★★☆</span>
        <span className="text-[#7a828c] dark:text-[#8A9BB0]" style={fs(1.15)}>212 reviews</span>
      </div>
      <div className="absolute left-[53%] top-[41%]">
        <div className="text-[#5b636d] dark:text-[#9AA9BC]" style={fs(1.2)}>Colour</div>
        <div className="mt-[0.6cqw] flex gap-[0.9cqw]">
          {["#2b3138", "#4a7c74", "#c9b79a"].map((c, i) => (
            <span key={c} className={`rounded-full ${i === 0 ? "ring-[0.2cqw] ring-[#2b3138] ring-offset-[0.25cqw] ring-offset-[#F7F5F0] dark:ring-[#c9d3df] dark:ring-offset-[#111A26]" : ""}`} style={{ background: c, width: "2.4cqw", height: "2.4cqw" }} />
          ))}
        </div>
      </div>
      <div className="absolute left-[53%] top-[52%] w-[38%] space-y-[0.8cqw]">
        {[100, 92, 70].map((w) => (
          <div key={w} className="rounded-full bg-[#ddd8ce] dark:bg-[#243247]" style={{ width: `${w}%`, height: "0.9cqw" }} />
        ))}
      </div>
      <div className="absolute left-[53%] top-[66%] flex h-[10%] w-[30%] items-center justify-center rounded-[0.8cqw] bg-[#1f3a5f] font-medium text-white dark:bg-[#3567d6]" style={fs(1.55)}>
        Add to cart
      </div>
      <div className="absolute left-[85%] top-[69%] text-[#5b636d] underline dark:text-[#9AA9BC]" style={fs(1.3)}>Save</div>
      <div className="absolute left-[53%] top-[82%] text-[#7a828c] dark:text-[#8A9BB0]" style={fs(1.15)}>Free returns · Ships in 2 days</div>
    </div>
  );
}
