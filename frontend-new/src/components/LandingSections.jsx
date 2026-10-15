import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import IrisMark from "./IrisMark.jsx";
import { MiniHeatmap } from "./LandingVisuals.jsx";

/*
 * Landing-page sections that act out what GazeLens does instead of just
 * describing it: a virtual eye roaming the hero, a persona switcher with a
 * live mock report for each audience, and a scroll-driven walk through the
 * four steps.
 */

const TONE = {
  cool: { text: "text-cool", bg: "bg-cool", soft: "bg-cool/10", ring: "ring-cool/40", rgb: "var(--color-cool)" },
  accent: { text: "text-accent", bg: "bg-accent", soft: "bg-accent/10", ring: "ring-accent/40", rgb: "var(--color-accent)" },
  amber: { text: "text-amber", bg: "bg-amber", soft: "bg-amber/10", ring: "ring-amber/40", rgb: "var(--color-amber)" },
  coral: { text: "text-coral", bg: "bg-coral", soft: "bg-coral/10", ring: "ring-coral/40", rgb: "var(--color-coral)" },
};

const HEAT =
  "radial-gradient(closest-side, rgba(255,107,90,0.9), rgba(255,181,71,0.65) 35%, rgba(46,230,197,0.38) 62%, rgba(91,140,255,0.16) 80%, transparent)";

/* ======================================================================
 * Hero: floating product moments + a virtual eye that visits them
 * ==================================================================== */

// The cards take turns lighting up, as if someone were looking at each.
const HERO_CARDS = 4;

export function HeroFloaters() {
  const reduce = useReducedMotion();
  const [lit, setLit] = useState(0);

  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setLit((s) => (s + 1) % HERO_CARDS), 2600);
    return () => clearInterval(id);
  }, [reduce]);

  const float = (delay) => (reduce ? {} : {
    animate: { y: [0, -9, 0] },
    transition: { duration: 6, repeat: Infinity, ease: "easeInOut", delay },
  });
  // every card is the same size so the hero reads as one balanced set
  const card = (active, tone = "accent") =>
    `flex h-[160px] w-[260px] flex-col rounded-[18px] border bg-surface/85 p-4 shadow-[0_24px_60px_-28px_rgba(0,0,0,0.7)] backdrop-blur transition-all duration-700 ${
      active ? `border-transparent ring-1 ${TONE[tone].ring} shadow-[0_0_50px_-14px_rgb(${TONE[tone].rgb}/0.55)]` : "border-border"
    }`;
  const slot = (side, top, delay) => ({
    initial: { opacity: 0, x: side === "left" ? -20 : 20 },
    animate: { opacity: 1, x: 0 },
    transition: { delay, duration: 0.7 },
    className: `absolute ${side === "left" ? "left-0" : "right-0"} ${top}`,
  });

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden xl:block">
      {/* top left: live tracking */}
      <motion.div {...slot("left", "top-[19%]", 0.8)}>
        <motion.div {...float(0)} className={card(lit === 0)}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-text-primary">
              <span className="text-accent"><IrisMark size={20} wander /></span> Live tracking
            </div>
            <span className="flex items-center gap-1 rounded-full bg-coral/15 px-2 py-0.5 text-[11px] font-semibold text-coral">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-coral" /> REC
            </span>
          </div>
          <div className="mt-2 text-[13px] text-text-secondary">Looking at: <span className="font-medium text-accent">Sign-up button</span></div>
          <div className="mt-auto"><Sparkline /></div>
        </motion.div>
      </motion.div>

      {/* top right: a finding */}
      <motion.div {...slot("right", "top-[19%]", 0.9)}>
        <motion.div {...float(0.8)} className={card(lit === 1, "amber")}>
          <div className="flex items-center gap-2 text-[12px] font-semibold text-amber"><span className="h-1.5 w-1.5 rounded-full bg-amber" /> Worth fixing</div>
          <div className="mt-1.5 text-[14px] font-semibold leading-snug text-text-primary">“Add to cart” was noticed late</div>
          <div className="mt-1 text-[12px] text-text-secondary">First seen after 6.1 seconds</div>
          <div className="mt-auto flex gap-1.5">
            {[["Fix first", "coral"], ["Strong evidence", "accent"]].map(([t, c]) => (
              <span key={t} className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${TONE[c].soft} ${TONE[c].text}`}>{t}</span>
            ))}
          </div>
        </motion.div>
      </motion.div>

      {/* bottom right: heatmap */}
      <motion.div {...slot("right", "top-[58%]", 1.0)}>
        <motion.div {...float(1.6)} className={card(lit === 2, "coral")}>
          <div className="mb-2 flex items-center justify-between text-[12px]">
            <span className="font-semibold text-text-primary">Heatmap ready</span>
            <span className="text-text-secondary">32 s test</span>
          </div>
          <div className="mt-auto"><MiniHeatmap label="" /></div>
        </motion.div>
      </motion.div>

      {/* bottom left: accuracy check */}
      <motion.div {...slot("left", "top-[58%]", 1.1)}>
        <motion.div {...float(2.4)} className={card(lit === 3)}>
          <div className="text-[12px] font-semibold text-text-primary">Accuracy check</div>
          <div className="mt-auto flex items-center gap-4">
            <MiniRing pct={0.82} />
            <div>
              <div className="text-[18px] font-semibold text-text-primary">Good <span className="text-[13px] font-normal text-text-secondary">· 55 px</span></div>
              <div className="mt-0.5 text-[12px] text-accent">Ready to test</div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

function Sparkline() {
  const reduce = useReducedMotion();
  const d = "M0 18 L12 14 L24 16 L36 6 L48 9 L60 4 L72 12 L84 8 L96 10 L108 3 L120 7";
  return (
    <svg viewBox="0 0 120 22" className="mt-3 h-6 w-full" aria-hidden="true">
      <motion.path d={d} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="1.6" strokeLinecap="round"
        initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }}
        transition={reduce ? undefined : { duration: 2.4, repeat: Infinity, repeatType: "loop", ease: "linear", repeatDelay: 0.8 }} />
    </svg>
  );
}

function MiniRing({ pct }) {
  const R = 16, C = 2 * Math.PI * R;
  return (
    <svg viewBox="0 0 40 40" className="h-14 w-14 -rotate-90" aria-hidden="true">
      <circle cx="20" cy="20" r={R} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth="4" />
      <motion.circle cx="20" cy="20" r={R} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="4" strokeLinecap="round"
        strokeDasharray={C} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: C * (1 - pct) }}
        transition={{ duration: 1.4, delay: 1.3, ease: [0.22, 1, 0.36, 1] }} />
    </svg>
  );
}

/* ======================================================================
 * Who it's for: pick a persona, see what GazeLens would show them
 * ==================================================================== */

// Mock page blocks, in % of the preview. kind: bar | img | text | btn
const PERSONAS = [
  {
    key: "design", emoji: "🎨", tone: "accent", title: "Designers", short: "Check a layout before it's built.",
    page: "Landing page draft",
    blocks: [
      { x: 4, y: 6, w: 92, h: 9, kind: "bar" },
      { x: 8, y: 22, w: 46, h: 8, kind: "text", label: "Headline" },
      { x: 8, y: 34, w: 40, h: 4, kind: "text" },
      { x: 56, y: 22, w: 36, h: 52, kind: "img" },
      { x: 8, y: 46, w: 22, h: 9, kind: "btn", missed: true, label: "Get started" },
    ],
    heat: [{ x: 74, y: 46, r: 20, o: 0.95 }, { x: 28, y: 26, r: 8, o: 0.35 }],
    finding: "The hero image pulled 61% of attention. The “Get started” button got almost none.",
    fix: "Shrink the image and move the button up, next to the headline.",
    stats: [["61%", "on the image"], ["0.4 s", "on the button"]],
  },
  {
    key: "dev", emoji: "💻", tone: "cool", title: "Developers", short: "Test a feature before launch.",
    page: "New checkout page",
    blocks: [
      { x: 4, y: 6, w: 92, h: 9, kind: "bar" },
      { x: 8, y: 22, w: 50, h: 6, kind: "text", label: "Order summary" },
      { x: 8, y: 32, w: 50, h: 22, kind: "img" },
      { x: 64, y: 22, w: 28, h: 8, kind: "text", label: "Promo code" },
      { x: 64, y: 62, w: 28, h: 11, kind: "btn", missed: true, label: "Pay now" },
    ],
    heat: [{ x: 78, y: 26, r: 13, o: 0.95 }, { x: 33, y: 42, r: 12, o: 0.55 }],
    finding: "People looked at the promo code box before the “Pay now” button, and kept coming back to it.",
    fix: "Tuck the promo code behind a small link so “Pay now” stands out.",
    stats: [["3×", "back to promo code"], ["5.8 s", "to find Pay now"]],
  },
  {
    key: "research", emoji: "🎓", tone: "amber", title: "Students & researchers", short: "Run studies without a lab.",
    page: "Study: news article layout",
    blocks: [
      { x: 4, y: 6, w: 92, h: 9, kind: "bar" },
      { x: 8, y: 22, w: 56, h: 7, kind: "text", label: "Article" },
      { x: 8, y: 34, w: 56, h: 30, kind: "img" },
      { x: 70, y: 22, w: 22, h: 52, kind: "text", missed: true, label: "Sidebar" },
    ],
    heat: [{ x: 34, y: 30, r: 12, o: 0.8 }, { x: 36, y: 50, r: 16, o: 0.95 }],
    finding: "Readers never looked at the sidebar. All attention stayed on the article column.",
    fix: "Export the heatmap, eye path and numbers as a PDF for your paper.",
    stats: [["0", "looks at the sidebar"], ["PDF", "ready to cite"]],
  },
  {
    key: "shop", emoji: "🛍️", tone: "coral", title: "Shop owners", short: "Find out why people don't buy.",
    page: "Product page",
    blocks: [
      { x: 4, y: 6, w: 92, h: 9, kind: "bar" },
      { x: 8, y: 22, w: 42, h: 52, kind: "img", label: "Photo" },
      { x: 56, y: 22, w: 36, h: 7, kind: "text", label: "Price" },
      { x: 56, y: 34, w: 30, h: 4, kind: "text" },
      { x: 56, y: 62, w: 24, h: 11, kind: "btn", missed: true, label: "Add to cart" },
    ],
    heat: [{ x: 29, y: 46, r: 18, o: 0.95 }, { x: 70, y: 25, r: 10, o: 0.6 }],
    finding: "Visitors loved the photo and checked the price, but “Add to cart” was first seen after 6 seconds.",
    fix: "Make the button bigger and put it right under the price.",
    stats: [["6.1 s", "to notice the button"], ["48%", "on the photo"]],
  },
];

const ROTATE_MS = 6500;

export function AudienceSwitcher() {
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (reduce || paused) return;
    const id = setTimeout(() => { setActive((a) => (a + 1) % PERSONAS.length); setCycle((c) => c + 1); }, ROTATE_MS);
    return () => clearTimeout(id);
  }, [active, paused, reduce, cycle]);

  const p = PERSONAS[active];
  const pick = (i) => { setActive(i); setCycle((c) => c + 1); };

  return (
    <div className="mt-14 grid grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.1fr]" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0 lg:flex-col lg:gap-3 lg:overflow-visible" role="tablist" aria-label="Who it's for">
        {PERSONAS.map((x, i) => {
          const on = i === active;
          return (
            <button
              key={x.key}
              role="tab"
              aria-selected={on}
              onClick={() => pick(i)}
              className={`group relative shrink-0 overflow-hidden rounded-[20px] border p-3 text-left transition-all duration-300 lg:shrink lg:p-5 ${
                on ? "border-white/15 bg-surface" : "border-border bg-surface/40 hover:bg-surface/70"
              }`}
            >
              <div className="flex items-center gap-4">
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] text-[20px] lg:h-12 lg:w-12 lg:rounded-[14px] lg:text-[24px] ${TONE[x.tone].soft}`}>{x.emoji}</span>
                <div className="min-w-0">
                  <div className={`whitespace-nowrap text-[16px] font-semibold tracking-tight lg:text-[18px] ${on ? "text-text-primary" : "text-text-secondary group-hover:text-text-primary"}`}>{x.title}</div>
                  <div className="hidden text-[14px] text-text-secondary lg:block">{x.short}</div>
                </div>
                <span className={`ml-auto hidden text-[18px] transition-all lg:inline ${on ? `${TONE[x.tone].text} translate-x-0 opacity-100` : "-translate-x-2 opacity-0"}`}>→</span>
              </div>
              {on && (
                <motion.span
                  key={`${cycle}-${paused}`}
                  className={`absolute bottom-0 left-0 h-[3px] ${TONE[x.tone].bg}`}
                  initial={{ width: "0%" }}
                  animate={{ width: paused || reduce ? "100%" : "100%" }}
                  transition={{ duration: paused || reduce ? 0 : ROTATE_MS / 1000, ease: "linear" }}
                />
              )}
            </button>
          );
        })}
      </div>

      <div className="relative overflow-hidden rounded-[26px] lg:min-h-[460px] border border-white/10 bg-surface/80 p-5 backdrop-blur sm:p-7">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 transition-[background] duration-700" style={{ background: `radial-gradient(70% 60% at 100% 0%, rgb(${TONE[p.tone].rgb} / 0.14), transparent 70%)` }} />
        <AnimatePresence mode="wait">
          <motion.div key={p.key} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.4 }} className="relative">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[13px] text-text-secondary">Their test: <span className="font-medium text-text-primary">{p.page}</span></div>
              <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${TONE[p.tone].soft} ${TONE[p.tone].text}`}>{p.title}</span>
            </div>
            <MockPage persona={p} />
            <div className="mt-5 rounded-[16px] border border-white/10 bg-bg/60 p-4">
              <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-coral">
                <span className="h-1.5 w-1.5 rounded-full bg-coral" /> What GazeLens found
              </div>
              <p className="mt-1.5 text-[16px] leading-snug text-text-primary">{p.finding}</p>
              <p className="mt-2 text-[14px] text-text-secondary"><span className="font-semibold text-accent">Fix:</span> {p.fix}</p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {p.stats.map(([v, l]) => (
                <div key={l} className="rounded-[14px] border border-white/10 bg-bg/40 px-4 py-3">
                  <div className={`text-[22px] font-bold tabular-nums ${TONE[p.tone].text}`}>{v}</div>
                  <div className="text-[13px] text-text-secondary">{l}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function MockPage({ persona }) {
  const reduce = useReducedMotion();
  return (
    <div className="relative mt-4 aspect-[16/8] overflow-hidden rounded-[14px] border border-white/10 bg-[#111A26]">
      {persona.blocks.map((b, i) => (
        <div
          key={i}
          className={`absolute rounded-[5px] ${
            b.kind === "bar" ? "bg-[#0D141E]" : b.kind === "img" ? "bg-[#1c2738]" : b.kind === "btn" ? "bg-[#3567d6]" : "bg-[#243247]"
          } ${b.missed ? "outline-dashed outline-2 outline-offset-[3px] outline-coral" : ""}`}
          style={{ left: `${b.x}%`, top: `${b.y}%`, width: `${b.w}%`, height: `${b.h}%` }}
        >
          {b.label && <span className="absolute left-1.5 top-1 text-[9px] font-medium text-white/60">{b.label}</span>}
        </div>
      ))}
      {persona.heat.map((h, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full mix-blend-screen"
          style={{ left: `${h.x - h.r}%`, top: `${h.y - h.r * 2}%`, width: `${h.r * 2}%`, height: `${h.r * 4}%`, background: HEAT }}
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: h.o, scale: 1 }}
          transition={{ duration: 0.9, delay: reduce ? 0 : 0.2 + i * 0.25, ease: [0.22, 1, 0.36, 1] }}
        />
      ))}
      {persona.blocks.filter((b) => b.missed).map((b, i) => (
        <motion.span
          key={i}
          className="absolute whitespace-nowrap rounded-full bg-coral px-2 py-0.5 text-[10px] font-semibold text-[#0A0E14]"
          style={{ left: `${b.x}%`, top: `calc(${b.y + b.h}% + 8px)` }}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: reduce ? 0 : 0.9 }}
        >
          Barely seen
        </motion.span>
      ))}
    </div>
  );
}

/* ======================================================================
 * How it works: a pinned visual that changes as each step scrolls by
 * ==================================================================== */

export function HowItWorksJourney({ steps }) {
  const [active, setActive] = useState(0);
  const refs = useRef([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number(e.target.dataset.step));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="mt-16 grid grid-cols-1 gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
      {/* pinned visual (wide screens) */}
      <div className="hidden lg:block">
        <div className="sticky top-28">
          <StepScreen step={active} tone={steps[active].tone} />
          <div className="mt-5 flex justify-center gap-2">
            {steps.map((s, i) => (
              <span key={s.title} className={`h-1.5 rounded-full transition-all duration-500 ${i === active ? `w-8 ${TONE[s.tone].bg}` : "w-1.5 bg-white/15"}`} />
            ))}
          </div>
        </div>
      </div>

      {/* the steps */}
      <div className="relative">
        <div aria-hidden="true" className="absolute left-[21px] top-[calc(12.5%)] hidden h-[75%] w-px bg-white/10 lg:block" />
        <motion.div
          aria-hidden="true"
          className="absolute left-[21px] top-[calc(12.5%)] hidden w-[2px] -translate-x-[0.5px] rounded-full bg-gradient-to-b from-cool via-accent to-coral lg:block"
          animate={{ height: `${(active / (steps.length - 1)) * 75}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
        {steps.map((s, i) => {
          const on = i === active;
          return (
            <div
              key={s.title}
              ref={(el) => (refs.current[i] = el)}
              data-step={i}
              className="relative flex py-6 lg:h-[44vh] lg:min-h-[300px] lg:items-center lg:py-0"
            >
              <div className="flex w-full gap-6 lg:items-center">
                <span className={`relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[17px] font-bold ring-4 ring-bg transition-all duration-500 ${
                  on ? `${TONE[s.tone].bg} text-[#0A0E14] shadow-[0_0_30px_-4px_rgb(${TONE[s.tone].rgb}/0.8)]` : `bg-surface ${TONE[s.tone].text}`
                }`}>{i + 1}</span>
                <div className={`flex-1 transition-opacity duration-500 ${on ? "opacity-100" : "lg:opacity-40"}`}>
                  <div className="flex min-h-11 items-center">
                    <span className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-text-secondary">{s.tag}</span>
                  </div>
                  <h3 className="mt-2 text-[26px] font-semibold tracking-tight text-text-primary">{s.title}</h3>
                  <p className="mt-2 max-w-md text-[16px] leading-relaxed text-text-secondary">{s.body}</p>
                  <div className="mt-5 lg:hidden"><StepScreen step={i} tone={s.tone} /></div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StepScreen({ step, tone }) {
  return (
    <div className="relative overflow-hidden rounded-[24px] border border-white/10 bg-surface/80 shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] backdrop-blur">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 transition-[background] duration-700" style={{ background: `radial-gradient(60% 50% at 50% 0%, rgb(${TONE[tone].rgb} / 0.16), transparent 70%)` }} />
      <div className="relative flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
        {["#FF6B5A", "#FFB547", "#2EE6C5"].map((c) => <span key={c} className="h-2.5 w-2.5 rounded-full" style={{ background: c, opacity: 0.7 }} />)}
        <span className="ml-3 text-[12px] text-text-secondary">GazeLens</span>
      </div>
      <div className="relative aspect-[16/11]">
        <AnimatePresence mode="wait">
          <motion.div key={step} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.02 }} transition={{ duration: 0.4 }} className="absolute inset-0 p-5">
            {step === 0 && <CalibrationScreen />}
            {step === 1 && <PickScreen />}
            {step === 2 && <BrowseScreen />}
            {step === 3 && <ReportScreen />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function CalibrationScreen() {
  const reduce = useReducedMotion();
  const [dot, setDot] = useState(0);
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setDot((d) => (d + 1) % 9), 1100);
    return () => clearInterval(id);
  }, [reduce]);
  const R = 14, C = 2 * Math.PI * R;
  return (
    <div className="flex h-full flex-col">
      <div className="text-center text-[13px] text-text-secondary"><span className="hidden sm:inline">Look at each dot until its ring fills · </span><span className="text-accent">Dot {dot + 1} of 9</span></div>
      <div className="mt-4 grid flex-1 grid-cols-3 grid-rows-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="flex items-center justify-center">
            {i === dot ? (
              <span className="relative flex h-11 w-11 items-center justify-center">
                <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90">
                  <circle cx="18" cy="18" r={R} fill="none" stroke="rgb(255 255 255 / 0.1)" strokeWidth="3" />
                  <motion.circle key={dot} cx="18" cy="18" r={R} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="3" strokeLinecap="round"
                    strokeDasharray={C} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: 0 }} transition={{ duration: 1, ease: "linear" }} />
                </svg>
                <span className="h-2.5 w-2.5 rounded-full bg-accent shadow-[0_0_12px_rgb(var(--color-accent))]" />
              </span>
            ) : (
              <span className={`h-2 w-2 rounded-full ${i < dot ? "bg-accent/50" : "bg-white/15"}`} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PickScreen() {
  const reduce = useReducedMotion();
  const url = "your-shop.com/product";
  const [n, setN] = useState(reduce ? url.length : 0);
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setN((v) => (v >= url.length + 12 ? 0 : v + 1)), 90);
    return () => clearInterval(id);
  }, [reduce]);
  const typed = url.slice(0, Math.min(n, url.length));
  const loaded = n >= url.length;
  const pages = [["Shop", "coral"], ["Sign-up", "accent"], ["Article", "amber"], ["Login", "cool"]];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 rounded-full border border-white/10 bg-bg/70 px-4 py-2.5 text-[14px]">
        <span className="text-text-secondary">https://</span>
        <span className="text-text-primary">{typed}</span>
        <span className="h-4 w-px animate-pulse bg-accent" />
        <span className={`ml-auto rounded-full px-3 py-1 text-[12px] font-semibold transition-colors ${loaded ? "bg-accent text-[#0A0E14]" : "bg-white/10 text-text-secondary"}`}>{loaded ? "Loaded ✓" : "Load page"}</span>
      </div>
      <div className="mt-4 text-[12px] text-text-secondary">or pick a sample page</div>
      <div className="mt-2 grid flex-1 grid-cols-2 gap-3">
        {pages.map(([name, t], i) => (
          <div key={name} className={`relative overflow-hidden rounded-[12px] border bg-bg/50 p-2.5 ${i === 0 ? `border-transparent ring-2 ${TONE[t].ring}` : "border-white/10"}`}>
            <div className="h-2 w-full rounded-full bg-white/10" />
            <div className="mt-2 flex gap-2">
              <div className="h-12 flex-1 rounded-[6px] bg-white/[0.06]" />
              <div className="flex flex-1 flex-col gap-1.5">
                <div className="h-1.5 rounded-full bg-white/10" /><div className="h-1.5 w-2/3 rounded-full bg-white/10" />
                <div className={`mt-auto h-3 w-1/2 rounded-[3px] ${TONE[t].bg} opacity-70`} />
              </div>
            </div>
            <div className="mt-2 text-[12px] font-medium text-text-primary">{name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BrowseScreen() {
  const reduce = useReducedMotion();
  const path = { left: ["30%", "72%", "70%", "30%", "66%"], top: ["40%", "28%", "48%", "62%", "74%"] };
  return (
    <div className="relative h-full overflow-hidden rounded-[14px] bg-[#111A26]">
      <div className="absolute inset-x-[4%] top-[5%] h-[9%] rounded-[5px] bg-[#0D141E]" />
      <div className="absolute left-[6%] top-[22%] h-[56%] w-[46%] rounded-[8px] bg-[#1c2738]" />
      <div className="absolute left-[58%] top-[22%] h-[9%] w-[34%] rounded-[4px] bg-[#2a3a52]" />
      <div className="absolute left-[58%] top-[38%] space-y-2" style={{ width: "32%" }}>
        {[100, 85, 70].map((w) => <div key={w} className="h-2 rounded-full bg-[#243247]" style={{ width: `${w}%` }} />)}
      </div>
      <div className="absolute left-[58%] top-[66%] h-[12%] w-[24%] rounded-[6px] bg-[#3567d6]" />
      {!reduce && (
        <motion.div
          className="absolute -ml-5 -mt-5"
          animate={path}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", times: [0, 0.25, 0.5, 0.75, 1] }}
        >
          <span className="relative flex h-10 w-10 items-center justify-center rounded-full border-2 border-amber shadow-[0_0_24px_4px_rgb(var(--color-amber)/0.4)]">
            <span className="h-2 w-2 rounded-full bg-amber" />
          </span>
        </motion.div>
      )}
      <div className="absolute bottom-3 left-3 flex items-center gap-2 rounded-full bg-bg/80 px-3 py-1 text-[12px] text-text-primary backdrop-blur">
        <span className="h-2 w-2 animate-pulse rounded-full bg-coral" /> Recording · 00:24
      </div>
    </div>
  );
}

function ReportScreen() {
  const bars = [["Photo", 48, "accent"], ["Price", 27, "accent"], ["Description", 18, "accent"], ["Add to cart", 3, "coral"]];
  return (
    <div className="flex h-full flex-col justify-between gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[13px] text-text-secondary">Your report</div>
          <div className="text-[24px] font-bold leading-tight tracking-tight text-text-primary">
            2 things <span className="font-serif font-normal italic text-coral">worth fixing</span>
          </div>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] text-text-primary">Download PDF</span>
      </div>
      <div className="grid grid-cols-2 items-center gap-4">
        <MiniHeatmap label="" />
        <div className="flex flex-col gap-3">
          {bars.map(([n, v, t], i) => (
            <div key={n}>
              <div className="flex justify-between text-[11px]"><span className={t === "coral" ? "text-coral" : "text-text-primary"}>{n}</span><span className="text-text-secondary">{v}%</span></div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.div className={`h-full rounded-full ${t === "coral" ? "bg-coral" : "bg-gradient-to-r from-cool via-accent to-amber"}`}
                  initial={{ width: 0 }} animate={{ width: `${Math.max(4, v * 2)}%` }} transition={{ duration: 0.9, delay: 0.2 + i * 0.12 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-[12px] border border-coral/30 bg-coral/10 px-3 py-2">
          <div className="text-[11px] font-semibold text-coral">Fix first</div>
          <div className="text-[12px] text-text-primary">“Add to cart” barely seen</div>
        </div>
        <div className="rounded-[12px] border border-amber/30 bg-amber/10 px-3 py-2">
          <div className="text-[11px] font-semibold text-amber">Worth fixing</div>
          <div className="text-[12px] text-text-primary">Price found after 4 s</div>
        </div>
      </div>
    </div>
  );
}
