import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import FeatureWall from "../components/FeatureWall.jsx";
import GazeField from "../components/GazeField.jsx";
import IrisMark, { Wordmark } from "../components/IrisMark.jsx";
import StackedStory from "../components/StackedStory.jsx";
import { CheckIcon } from "../components/LandingVisuals.jsx";
import GazeHero from "../components/GazeHero.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import { AudienceSwitcher, HeroFloaters, HowItWorksJourney } from "../components/LandingSections.jsx";

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
  { q: "How precise is the eye tracking?", a: "Precise enough to tell which part of a page someone looked at, like a button, an image or a headline, but not single words. Before every test, a quick precision check measures how precisely your eyes are tracked. If it isn't precise enough, GazeLens tells you to try again instead of guessing." },
  { q: "Can I test my own website?", a: "Yes. Paste a link and GazeLens takes a snapshot of the page and finds its buttons, images and text for you. You can also start with one of our five sample pages." },
  { q: "Does it work if I wear glasses?", a: "Usually, yes. Reflections on lenses can make tracking less precise, so sit facing your light rather than with a window behind you. The precision check will tell you how well it's working." },
  { q: "Who is GazeLens for?", a: "Designers, developers, students and researchers who want to know whether people notice the right things on a page, without booking an eye-tracking lab." },
];


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
          wide
          eyebrow="Who it's for"
          title="Made for anyone who builds for the web"
          text="Pick who you are and see what GazeLens would show you. No eye-tracking knowledge needed."
        />
        <AudienceSwitcher />
      </section>

      {/* ------------------------------------------------------------ how */}
      <section id="how" className="mx-auto max-w-[1100px] scroll-mt-24 px-5 py-28 sm:px-8 lg:py-36">
        <SectionHeading
          wide
          eyebrow="How it works"
          title="From setup to report in four easy steps"
          text="No training needed. Scroll through to watch each step happen."
        />
        <HowItWorksJourney steps={STEPS} />
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

function SectionHeading({ eyebrow, title, text, wide = false }) {
  return (
    <Reveal once className={`mx-auto ${wide ? "max-w-[1100px]" : "max-w-[720px]"} px-5 text-center sm:px-8`}>
      <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
      <h2 className={`mt-3 text-[36px] font-bold leading-[1.08] tracking-[-0.02em] text-text-primary sm:text-[50px] ${wide ? "lg:whitespace-nowrap lg:text-[46px] xl:text-[50px]" : ""}`}>{title}</h2>
      {text && <p className={`mt-4 text-balance text-[18px] leading-relaxed text-text-secondary ${wide ? "lg:whitespace-nowrap" : ""}`}>{text}</p>}
    </Reveal>
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

