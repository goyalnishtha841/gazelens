import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion, useScroll, useTransform } from "framer-motion";
import IrisMark from "./IrisMark.jsx";
import { CheckIcon, CrossIcon, MiniHeatmap, MissedList } from "./LandingVisuals.jsx";

/**
 * The story in three cards that stack as you scroll: each card sticks to the
 * screen, the next one slides up over it, and the ones underneath shrink
 * back slightly -- the effect on cairn's landing page.
 *
 * Desktop only: on small screens a card can be taller than the screen, which
 * breaks sticky stacking, so there they simply follow one another.
 */

const TONES = {
  coral: { pill: "bg-coral/10 text-coral", border: "border-coral/25", glow: "rgb(var(--color-coral) / 0.16)" },
  accent: { pill: "bg-accent/10 text-accent", border: "border-accent/30", glow: "rgb(var(--color-accent) / 0.16)" },
  amber: { pill: "bg-amber/10 text-amber", border: "border-amber/30", glow: "rgb(var(--color-amber) / 0.16)" },
};

const CARDS = [
  {
    tone: "coral",
    pill: "Without GazeLens",
    title: <>You're <Accent className="text-coral">guessing</Accent> what people see.</>,
    text: "Surveys and click data only tell part of the story. People can't remember what they looked at, and eye-tracking labs are expensive and slow to book.",
    points: ["Why did nobody click “Sign up”?", "Did they even see the price?"],
    pointIcon: "cross",
    visual: <GuessGrid />,
  },
  {
    tone: "accent",
    pill: "Quick setup",
    title: <>Ready in about <Accent className="text-accent">a minute.</Accent></>,
    text: "Look at a few dots on your screen while your webcam finds your eyes. GazeLens learns how they move, checks its own accuracy, then follows your gaze while you use the page.",
    points: ["Works with the camera you already have", "Nothing for your visitor to install"],
    pointIcon: "check",
    visual: <CalibrationDemo />,
  },
  {
    tone: "amber",
    pill: "Get your answer",
    title: <>A <Accent className="text-amber">clear list</Accent> of what to fix.</>,
    text: "Your report shows a heatmap, the things people missed, and a simple suggestion for each one. Download it as a PDF to share with your team.",
    points: ["Problems ranked from most to least important", "Written in plain language"],
    pointIcon: "check",
    visual: <ReportSnapshot />,
  },
];

function Accent({ children, className = "" }) {
  return <span className={`font-serif text-[1.1em] font-normal italic ${className}`}>{children}</span>;
}

function useIsDesktop() {
  const query = "(min-width: 1024px)";
  const [match, setMatch] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return match;
}

export default function StackedStory() {
  const ref = useRef(null);
  const desktop = useIsDesktop();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });

  return (
    <div ref={ref} className="relative mx-auto max-w-[1180px] px-5 sm:px-8">
      {CARDS.map((card, i) => (
        <StoryCard key={card.pill} card={card} index={i} total={CARDS.length} progress={scrollYProgress} desktop={desktop} />
      ))}
    </div>
  );
}

function StoryCard({ card, index, total, progress, desktop }) {
  const target = 1 - (total - 1 - index) * 0.05;
  const scale = useTransform(progress, [index / total, 1], [1, target]);
  const tone = TONES[card.tone];

  return (
    <div className="mb-6 lg:sticky lg:top-0 lg:mb-0 lg:flex lg:h-screen lg:items-center">
      <motion.div
        style={desktop ? { scale, top: `calc(-2vh + ${index * 26}px)` } : undefined}
        className={`relative w-full origin-top overflow-visible rounded-[28px] border ${tone.border} bg-surface shadow-[0_30px_80px_-40px_rgba(0,0,0,0.65)]`}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-[28px]"
          style={{ background: `radial-gradient(70% 90% at 0% 0%, ${tone.glow}, transparent 60%)` }}
        />
        <div className="relative grid grid-cols-1 items-center gap-10 p-7 sm:p-10 lg:grid-cols-[0.82fr_1.18fr] lg:gap-12 lg:p-12">
          <div>
            <span className={`inline-flex rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${tone.pill}`}>{card.pill}</span>
            <h3 className="mt-5 text-[32px] font-bold leading-[1.08] tracking-[-0.02em] text-text-primary sm:text-[42px]">{card.title}</h3>
            <p className="mt-4 text-[17px] leading-relaxed text-text-secondary">{card.text}</p>
            <ul className="mt-6 space-y-2.5">
              {card.points.map((p) => (
                <li key={p} className="flex items-start gap-2.5 text-[15px] text-text-primary">
                  {card.pointIcon === "cross"
                    ? <CrossIcon className="mt-0.5 shrink-0 text-coral" />
                    : <CheckIcon className="mt-0.5 shrink-0 text-accent" />}
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative pb-6 lg:pb-0">{card.visual}</div>
        </div>
      </motion.div>
    </div>
  );
}

/** A page full of controls nobody can say they noticed. */
function GuessGrid() {
  const marks = new Set([4, 9, 15, 22]);
  return (
    <div className="rounded-[20px] border border-border bg-bg/60 p-5">
      <div className="grid grid-cols-6 gap-2.5">
        {Array.from({ length: 24 }).map((_, i) => (
          <div
            key={i}
            className={`flex aspect-square items-center justify-center rounded-[10px] border text-[15px] font-bold ${
              marks.has(i) ? "border-coral/50 bg-coral/10 text-coral" : "border-border bg-surface text-text-secondary/40"
            }`}
          >
            {marks.has(i) ? "?" : <span className={`block ${i % 3 === 0 ? "h-3 w-3 rounded-full" : i % 4 === 1 ? "h-1.5 w-5 rounded-full" : "h-3 w-3 rounded-[3px]"} bg-current`} />}
          </div>
        ))}
      </div>
      <div className="mt-4 space-y-2">
        {["“I'm sure I saw the button…”", "“Was the price even visible?”"].map((q) => (
          <div key={q} className="rounded-[12px] border border-border bg-surface px-4 py-3 text-[14px] text-text-secondary">{q}</div>
        ))}
      </div>
    </div>
  );
}

/** The setup step: dots fill one after another while the webcam tracks the eyes. */
function CalibrationDemo() {
  const ref = useRef(null);
  const inView = useInView(ref, { margin: "-20% 0px" });
  const reduce = useReducedMotion();
  const [active, setActive] = useState(5);

  useEffect(() => {
    if (!inView || reduce) return undefined;
    const id = setInterval(() => setActive((a) => (a + 1) % 16), 900);
    return () => clearInterval(id);
  }, [inView, reduce]);

  return (
    <div ref={ref} className="relative rounded-[20px] border border-border bg-bg/60 p-5">
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-text-primary">Look at each dot until it fills</span>
        <span className="rounded-full bg-accent/10 px-2.5 py-0.5 font-semibold text-accent">Dot {active + 1} of 16</span>
      </div>
      <div className="mt-4 grid aspect-[16/9] grid-cols-4 grid-rows-4 place-items-center rounded-[14px] border border-border bg-surface">
        {Array.from({ length: 16 }).map((_, i) => (
          <span key={i} className="relative flex h-9 w-9 items-center justify-center">
            {i === active ? (
              <>
                <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90">
                  <circle cx="18" cy="18" r="15" fill="none" stroke="rgb(var(--color-border))" strokeWidth="2" />
                  <motion.circle
                    key={active}
                    cx="18" cy="18" r="15" fill="none" stroke="rgb(var(--color-accent))" strokeWidth="2" strokeLinecap="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: reduce ? 0 : 0.8, ease: "linear" }}
                  />
                </svg>
                <span className="h-2.5 w-2.5 rounded-full bg-accent shadow-[0_0_12px_rgb(var(--color-accent)/0.8)]" />
              </>
            ) : (
              <span className={`h-2 w-2 rounded-full ${i < active ? "bg-accent/50" : "bg-text-secondary/25"}`} />
            )}
          </span>
        ))}
      </div>
      {/* webcam preview with the eyes found */}
      <div className="absolute -bottom-6 -right-3 w-[150px] overflow-hidden rounded-[14px] border border-border bg-raised shadow-[0_18px_40px_-14px_rgba(0,0,0,0.7)] sm:-right-6">
        <div className="relative flex aspect-[4/3] items-center justify-center bg-gradient-to-b from-[#1c2738] to-[#111823]">
          <svg viewBox="0 0 80 60" className="h-full w-full" aria-hidden="true">
            <ellipse cx="40" cy="34" rx="17" ry="21" fill="#2a3a52" />
            <rect x="21" y="49" width="38" height="14" rx="7" fill="#2a3a52" />
          </svg>
          <span className="absolute left-[37%] top-[46%] text-accent"><IrisMark size={14} /></span>
          <span className="absolute left-[52%] top-[46%] text-accent"><IrisMark size={14} /></span>
        </div>
        <div className="flex items-center justify-between px-2.5 py-1.5 text-[11px]">
          <span className="text-text-secondary">Webcam</span>
          <span className="font-semibold text-accent">Eyes found ✓</span>
        </div>
      </div>
    </div>
  );
}

/** A slice of the finished report. */
function ReportSnapshot() {
  return (
    <div className="rounded-[20px] border border-border bg-bg/60 p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[12px] font-medium text-text-secondary">Your report · Product page</div>
          <div className="mt-0.5 text-[17px] font-semibold text-text-primary">2 things worth fixing</div>
        </div>
        <span className="rounded-full border border-border px-3 py-1 text-[12px] text-text-secondary">PDF ↓</span>
      </div>
      <div className="mt-4"><MiniHeatmap /></div>
      <div className="mt-4"><MissedList /></div>
      <div className="mt-3 rounded-[12px] rounded-tl-[4px] border border-accent/25 bg-accent/10 px-4 py-3 text-[14px] text-text-primary">
        Suggestion: make the <span className="font-semibold">Sign-up</span> button stand out more and move it higher.
      </div>
    </div>
  );
}
