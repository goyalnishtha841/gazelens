import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import FeatureWall from "../components/FeatureWall.jsx";
import GazeField from "../components/GazeField.jsx";
import IrisMark, { Wordmark } from "../components/IrisMark.jsx";
import StackedStory from "../components/StackedStory.jsx";
import { CheckIcon } from "../components/LandingVisuals.jsx";
import GazeHero from "../components/GazeHero.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";

/*
 * Landing page, written for someone who has never used an eye tracker.
 * Plain words only: no "fixations", "attribution" or "heuristics" here;
 * the app and the reports can use those once people are inside.
 * Every claim matches what the system actually does.
 *
 * Backgrounds: IrisHorizon behind the first screen; below it, GazeField,
 * a page-wide grid of dots that heats up where the visitor's pointer (and
 * two wandering "virtual eyes") look.
 */

const REPO_URL = "https://github.com/goyalnishtha841/gazelens";

const FACTS = [
  { value: "~1 min", label: "to get set up" },
  { value: "Any laptop", label: "webcam works, no special gear" },
  { value: "5", label: "sample pages ready to try" },
  { value: "PDF", label: "report to share with your team" },
];

const AUDIENCES = [
  { emoji: "🎨", tone: "accent", title: "Designers", text: "Check that your layout leads the eye to what matters, before anything gets built." },
  { emoji: "💻", tone: "cool", title: "Developers", text: "Test a new page or feature with real people before you launch it." },
  { emoji: "🎓", tone: "amber", title: "Students & researchers", text: "Run eye-tracking studies for projects and papers without booking a lab." },
  { emoji: "🛍️", tone: "coral", title: "Shop owners", text: "Find out why visitors look around but never click “Buy”." },
];

const STEPS = [
  { tone: "cool", tag: "about 1 minute", title: "Set up your camera", body: "Look at a few dots on your screen. This teaches GazeLens how your eyes move." },
  { tone: "accent", tag: "any website", title: "Pick a page", body: "Choose one of our sample pages, or paste a link to your own site." },
  { tone: "amber", tag: "no extra steps", title: "Use it normally", body: "Browse the page like you usually would. GazeLens quietly follows where you look." },
  { tone: "coral", tag: "ready in seconds", title: "Read your report", body: "See your heatmap, what got missed, and what to fix first." },
];

const FAQS = [
  { q: "Do I need any special equipment?", a: "No. A laptop with a built-in webcam is enough. An external webcam placed at eye level can work even better." },
  { q: "Is my camera video saved?", a: "No. Each video frame is only used to work out where your eyes are pointing, then it's thrown away. GazeLens keeps where you looked, not what the camera saw." },
  { q: "How long does it take?", a: "Setup takes about a minute. After that, a test can be as short or as long as you like, and your report is ready a few seconds after you finish." },
  { q: "How accurate is it?", a: "Accurate enough to tell which part of a page someone looked at, like a button, an image or a headline, but not single words. Before every test, a quick check shows how well tracking works for you. If it isn't accurate enough, GazeLens tells you to try again instead of guessing." },
  { q: "Can I test my own website?", a: "Yes. Paste a link and GazeLens takes a snapshot of the page and finds its buttons, images and text for you. You can also start with one of our five sample pages." },
  { q: "Does it work if I wear glasses?", a: "Usually, yes. Reflections on lenses can lower accuracy, so sit facing your light rather than with a window behind you. The accuracy check will tell you how well it's working." },
  { q: "Who is GazeLens for?", a: "Designers, developers, students and researchers who want to know whether people notice the right things on a page, without booking an eye-tracking lab." },
];

const TONE = {
  cool: { text: "text-cool", bg: "bg-cool", soft: "bg-cool/10" },
  accent: { text: "text-accent", bg: "bg-accent", soft: "bg-accent/10" },
  amber: { text: "text-amber", bg: "bg-amber", soft: "bg-amber/10" },
  coral: { text: "text-coral", bg: "bg-coral", soft: "bg-coral/10" },
};

export default function Landing({ onNavigate }) {
  const start = () => onNavigate?.();

  return (
    <div className="relative isolate overflow-x-clip font-display">
      <GazeField className="-z-10" />

      {/* ------------------------------------------------------------ hero:
          the first screen. Its own opaque background hides the page-wide
          dot field; the floating nav sits on top of it. */}
      <section className="relative isolate">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[700px]"
          style={{ background: "radial-gradient(50% 60% at 50% 15%, rgb(var(--color-accent) / 0.13), transparent 70%)" }}
        />
        {/* screen 1: the hero alone, over the interactive dot field */}
        <div className="relative mx-auto flex min-h-[100svh] w-full max-w-[1240px] flex-col justify-center px-5 pb-16 pt-[110px] sm:px-8">
          <HeroFloaters />

          <StaggerGroup className="mx-auto max-w-[860px] text-center">
            <StaggerItem>
              <span className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-bg/40 px-4 py-1.5 text-[14px] font-medium text-accent backdrop-blur">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-50" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
                </span>
                Eye tracking with just your laptop camera
              </span>
            </StaggerItem>
            <StaggerItem>
              <h1 className="mt-7 text-[44px] font-extrabold leading-[1.02] tracking-[-0.035em] text-text-primary sm:text-[64px] lg:text-[76px]">
                See what your users
                <br />
                <span className="bg-gradient-to-r from-cool via-accent to-amber bg-clip-text pr-2 font-serif text-[1.12em] font-normal italic tracking-normal text-transparent">
                  actually see.
                </span>
              </h1>
            </StaggerItem>
            <StaggerItem>
              <p className="mx-auto mt-6 max-w-[620px] text-balance text-[18px] leading-relaxed text-text-secondary sm:text-[19px]">
                GazeLens follows where people look on your website using an ordinary webcam.
                Then it tells you, in plain words, what they missed and what to fix.
              </p>
            </StaggerItem>
            <StaggerItem>
              <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
                <button
                  onClick={start}
                  className="group inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-[16px] font-semibold text-[#0A0E14] transition-all duration-300 hover:shadow-[0_0_40px_-4px_rgb(var(--color-accent)/0.75)] active:scale-[0.98]"
                >
                  Try GazeLens
                  <span className="transition-transform duration-300 group-hover:translate-x-1">→</span>
                </button>
                <a
                  href="#story"
                  className="rounded-full border border-border bg-bg/40 px-7 py-3.5 text-[16px] font-medium text-text-primary backdrop-blur transition-colors hover:border-accent/60"
                >
                  See how it works
                </a>
              </div>
            </StaggerItem>
            <StaggerItem>
              <ul className="mt-8 flex flex-wrap justify-center gap-x-7 gap-y-2 text-[15px] text-text-secondary">
                {["Nothing to install", "Ready in about a minute", "Your video is never saved"].map((t) => (
                  <li key={t} className="flex items-center gap-2">
                    <CheckIcon className="text-accent" />
                    {t}
                  </li>
                ))}
              </ul>
            </StaggerItem>
          </StaggerGroup>
          <ScrollCue />
        </div>

        {/* screen 2: the live demo */}
        <motion.div
          initial={{ opacity: 0, y: 60 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          id="demo"
          className="relative mx-auto max-w-[1080px] scroll-mt-28 px-5 pb-20 pt-6 sm:px-8"
        >
          <GazeHero />
          <p className="mt-12 text-center text-[13px] text-text-secondary">
            A live example: colour builds up where someone looked, then GazeLens points out the problem.
          </p>
        </motion.div>
      </section>

      {/* ------------------------------------------------------------ facts */}
      <section className="mx-auto max-w-[1100px] px-5 sm:px-8">
        <Reveal once>
          <div className="grid grid-cols-2 overflow-hidden rounded-[20px] border border-border bg-surface/70 backdrop-blur lg:grid-cols-4">
            {FACTS.map((f, i) => (
              <div key={f.label} className={`px-6 py-7 ${i % 2 === 1 ? "border-l" : ""} ${i > 1 ? "border-t lg:border-t-0" : ""} ${i === 2 ? "lg:border-l" : ""} border-border`}>
                <div className="text-[28px] font-bold tracking-tight text-text-primary sm:text-[32px]">{f.value}</div>
                <div className="mt-1 text-[14px] text-text-secondary">{f.label}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ story */}
      <section id="story" className="scroll-mt-24 pt-28 lg:pt-36">
        <SectionHeading
          eyebrow="Why GazeLens"
          title={<>Stop guessing. <span className="font-serif font-normal italic text-accent">Start seeing.</span></>}
          text="Here's how a single test turns into answers. Keep scrolling."
        />
        <div className="mt-8 lg:mt-0">
          <StackedStory />
        </div>
      </section>

      {/* ------------------------------------------------------------ features */}
      <section id="features" className="relative scroll-mt-24 pt-28 lg:pt-36">
        <SectionHeading
          eyebrow="What you get"
          title="Everything you need to understand attention"
          text="One test gives you a picture of where people looked and a clear list of what to improve."
        />
        <div className="mx-auto mt-14 max-w-[1300px] px-5 sm:px-8">
          <FeatureWall />
        </div>
      </section>

      {/* ------------------------------------------------------------ who */}
      <section id="who" className="mx-auto max-w-[1100px] scroll-mt-24 px-5 pt-28 sm:px-8 lg:pt-36">
        <SectionHeading
          eyebrow="Who it's for"
          title="Made for anyone who builds for the web"
          text="You don't need to know anything about eye tracking. If you care whether people notice the right things, GazeLens is for you."
        />
        <div className="mt-14 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {AUDIENCES.map((a, i) => (
            <Reveal once key={a.title} delay={i * 0.06}>
              <div className="group h-full rounded-[20px] border border-border bg-surface p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/40">
                <span className={`flex h-12 w-12 items-center justify-center rounded-[14px] text-[24px] ${TONE[a.tone].soft}`}>{a.emoji}</span>
                <h3 className="mt-5 text-[19px] font-semibold tracking-tight">{a.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-text-secondary">{a.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ how */}
      <section id="how" className="mx-auto max-w-[1100px] scroll-mt-24 px-5 py-28 sm:px-8 lg:py-36">
        <SectionHeading
          eyebrow="How it works"
          title="From setup to report in four easy steps"
          text="No training needed. If you can look at a screen, you can use GazeLens."
        />
        <div className="relative mt-24">
          <ScanpathLine />
          <div className="relative grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <Reveal once key={s.title} delay={i * 0.08}>
                <div className="group h-full rounded-[20px] border border-border bg-surface p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/40">
                  <div className="flex items-center justify-between">
                    <span className={`flex h-11 w-11 items-center justify-center rounded-full text-[17px] font-bold ${TONE[s.tone].soft} ${TONE[s.tone].text}`}>{i + 1}</span>
                    <span className="rounded-full border border-border px-2.5 py-0.5 text-[12px] text-text-secondary">{s.tag}</span>
                  </div>
                  <h3 className="mt-5 text-[20px] font-semibold tracking-tight">{s.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-text-secondary">{s.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ faq */}
      <section id="faq" className="scroll-mt-24 border-y border-border bg-surface/50 backdrop-blur-[2px]">
        <div className="mx-auto max-w-[800px] px-5 py-28 sm:px-8 lg:py-32">
          <SectionHeading eyebrow="FAQ" title="Questions, answered" />
          <Reveal once className="mt-12">
            <Faq />
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------------ CTA */}
      <section className="relative overflow-hidden">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10" style={{ background: "radial-gradient(45% 70% at 50% 60%, rgb(var(--color-accent) / 0.14), transparent 70%)" }} />
        <Reveal once>
          <div className="mx-auto max-w-[760px] px-5 py-32 text-center sm:px-8">
            <span className="inline-block drop-shadow-[0_0_18px_rgb(var(--color-accent)/0.6)]">
              <IrisMark size={56} wander className="text-accent" />
            </span>
            <h2 className="mt-6 text-[38px] font-bold leading-tight tracking-[-0.02em] sm:text-[56px]">
              Find out what your users <span className="font-serif font-normal italic text-accent">really</span> see
            </h2>
            <p className="mx-auto mt-4 max-w-md text-[18px] text-text-secondary">Setup takes about a minute. All you need is a webcam.</p>
            <button
              onClick={start}
              className="mt-9 rounded-full bg-accent px-9 py-4 text-[17px] font-semibold text-[#0A0E14] transition-shadow duration-300 hover:shadow-[0_0_40px_-4px_rgb(var(--color-accent)/0.75)]"
            >
              Try GazeLens →
            </button>
          </div>
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ footer */}
      <footer className="border-t border-border bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1100px] flex-col gap-8 px-5 py-12 sm:px-8 md:flex-row md:justify-between">
          <div className="max-w-sm">
            <Wordmark large />
            <p className="mt-4 text-[14px] leading-relaxed text-text-secondary">
              Eye tracking for better websites, using just a webcam. A capstone project built on the GazeUX-Agent framework.
            </p>
          </div>
          <div className="flex gap-14 text-[14px]">
            <div className="space-y-2.5">
              <div className="text-[13px] font-semibold text-text-primary">Product</div>
              <a href="#features" className="block text-text-secondary hover:text-accent">Features</a>
              <a href="#how" className="block text-text-secondary hover:text-accent">How it works</a>
              <a href="#faq" className="block text-text-secondary hover:text-accent">FAQ</a>
            </div>
            <div className="space-y-2.5">
              <div className="text-[13px] font-semibold text-text-primary">Project</div>
              <a href={REPO_URL} target="_blank" rel="noreferrer" className="block text-text-secondary hover:text-accent">GitHub ↗</a>
              <button onClick={start} className="block text-text-secondary hover:text-accent">Sign in</button>
            </div>
          </div>
        </div>
        <div className="mx-auto max-w-[1100px] border-t border-border px-5 py-6 text-[13px] text-text-secondary sm:px-8">© 2026 GazeLens team</div>
      </footer>
    </div>
  );
}

/* ------------------------------------------------------------------ parts */

function SectionHeading({ eyebrow, title, text }) {
  return (
    <Reveal once className="mx-auto max-w-[720px] px-5 text-center sm:px-8">
      <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
      <h2 className="mt-3 text-[36px] font-bold leading-[1.08] tracking-[-0.02em] text-text-primary sm:text-[50px]">{title}</h2>
      {text && <p className="mt-4 text-balance text-[18px] leading-relaxed text-text-secondary">{text}</p>}
    </Reveal>
  );
}

/** Small product moments floating around the headline (wide screens only). */
function HeroFloaters() {
  const reduce = useReducedMotion();
  const float = (delay) => (reduce ? {} : {
    animate: { y: [0, -10, 0] },
    transition: { duration: 6, repeat: Infinity, ease: "easeInOut", delay },
  });
  const card = "w-[230px] rounded-[18px] border border-border bg-surface/85 p-4 shadow-[0_24px_60px_-28px_rgba(0,0,0,0.7)] backdrop-blur";
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden xl:block">
      <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.8, duration: 0.7 }} className="absolute left-0 top-[18%]">
        <motion.div {...float(0)} className={card}>
          <div className="flex items-center gap-2 text-[13px] font-semibold text-text-primary">
            <span className="text-accent"><IrisMark size={20} wander /></span> Live tracking
          </div>
          <div className="mt-2 text-[13px] text-text-secondary">Looking at: <span className="font-medium text-accent">Sign-up button</span></div>
        </motion.div>
      </motion.div>

      <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.9, duration: 0.7 }} className="absolute right-0 top-[30%]">
        <motion.div {...float(0.8)} className={`${card} border-amber/30`}>
          <div className="flex items-center gap-2 text-[12px] font-semibold text-amber"><span className="h-1.5 w-1.5 rounded-full bg-amber" /> Worth fixing</div>
          <div className="mt-1 text-[14px] font-semibold leading-snug text-text-primary">“Add to cart” was noticed late</div>
          <div className="mt-1 text-[12px] text-text-secondary">First seen after 6.1 seconds</div>
        </motion.div>
      </motion.div>

    </div>
  );
}

/** Bottom of the first screen: tells newcomers there's more below. */
function ScrollCue() {
  const reduce = useReducedMotion();
  return (
    <a href="#demo" className="absolute bottom-8 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2 text-[13px] text-text-secondary transition-colors hover:text-accent sm:flex">
      <span>Scroll to see it in action</span>
      <span className="flex h-9 w-6 justify-center rounded-full border border-border pt-1.5">
        <motion.span
          className="block h-2 w-1 rounded-full bg-accent"
          animate={reduce ? undefined : { y: [0, 10, 0], opacity: [1, 0.2, 1] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        />
      </span>
    </a>
  );
}

function Faq() {
  const [open, setOpen] = useState(0);
  return (
    <div className="divide-y divide-border rounded-[20px] border border-border bg-bg/70">
      {FAQS.map((f, i) => {
        const isOpen = open === i;
        return (
          <div key={f.q}>
            <button
              onClick={() => setOpen(isOpen ? -1 : i)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-6 px-6 py-5 text-left text-[17px] font-medium text-text-primary transition-colors hover:text-accent"
            >
              {f.q}
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border text-[18px] leading-none transition-transform duration-300 ${isOpen ? "rotate-45 border-accent/50 text-accent" : ""}`}>+</span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                  className="overflow-hidden"
                >
                  <p className="px-6 pb-6 text-[16px] leading-relaxed text-text-secondary">{f.a}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

/** The "How it works" connector: an eye-path hopping across the 4 steps. */
function ScanpathLine() {
  const reduce = useReducedMotion();
  return (
    <div className="pointer-events-none absolute -top-14 left-0 hidden h-12 w-full lg:block" aria-hidden="true">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 48" preserveAspectRatio="none">
        <defs>
          <linearGradient id="scan-grad" x1="0" x2="1">
            <stop offset="0" stopColor="rgb(var(--color-cool))" />
            <stop offset="0.4" stopColor="rgb(var(--color-accent))" />
            <stop offset="0.7" stopColor="rgb(var(--color-amber))" />
            <stop offset="1" stopColor="rgb(var(--color-coral))" />
          </linearGradient>
        </defs>
        {/* pathLength animation owns the dashes, so the drawn line is solid;
            a static dashed copy underneath keeps the eye-path look */}
        <path d={CONNECTOR_PATH} fill="none" stroke="rgb(var(--color-border))" strokeWidth="1" strokeDasharray="4 5" vectorEffect="non-scaling-stroke" />
        <motion.path
          d={CONNECTOR_PATH} fill="none" stroke="url(#scan-grad)" strokeWidth="1.5" vectorEffect="non-scaling-stroke"
          initial={{ pathLength: reduce ? 1 : 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 1.6, ease: "easeInOut" }}
        />
      </svg>
      {/* HTML dots so they stay round; the outer span centres, the inner one
          scales (a motion transform would override the translate) */}
      {["cool", "accent", "amber", "coral"].map((tone, i) => (
        <span key={tone} className="absolute bottom-0 -translate-x-1/2 translate-y-1/2" style={{ left: `${12.5 + i * 25}%` }}>
          <motion.span
            className={`block h-3 w-3 rounded-full ring-4 ring-bg ${TONE[tone].bg}`}
            initial={{ scale: reduce ? 1 : 0 }}
            whileInView={{ scale: 1 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ delay: reduce ? 0 : 0.3 + i * 0.35, type: "spring", stiffness: 380, damping: 18 }}
          />
        </span>
      ))}
    </div>
  );
}

// Peaks between steps, touching down above each card's centre (12.5/37.5/...%).
const CONNECTOR_PATH = "M 125 44 Q 250 2 375 44 Q 500 2 625 44 Q 750 2 875 44";
