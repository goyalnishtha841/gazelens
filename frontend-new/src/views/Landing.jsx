import { GazeTrailDecorative } from "../components/GazeTrail.jsx";
import { Label, SectionLabel } from "../components/Primitives.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import { workflow, overview, findings, recommendations } from "../data/mockData.js";

const FEATURES = [
  {
    title: "Real gaze, not guesswork",
    body: "Fixation tracks where someone actually looks through an ordinary webcam. No eye-tracking hardware, no lab. A short calibration is all it needs.",
  },
  {
    title: "Attention mapped to your UI",
    body: "Raw gaze coordinates are matched to the exact elements on your page: dwell time, time-to-first-focus, revisit count, and full scanpath, per element, not just a heatmap.",
  },
  {
    title: "AI that reasons, not templates",
    body: "A chain of evidence-grounded agents turns metrics into findings, and a dedicated critic re-verifies every claim against the raw data before it reaches you.",
  },
];

const COMPARISON = [
  {
    label: "A heatmap alone",
    points: [
      "Shows where eyes lingered, as a color gradient",
      "Leaves interpretation entirely to you",
      "No connection to specific UI elements",
      "No sense of order, just density",
    ],
  },
  {
    label: "Fixation",
    points: [
      "Every fixation attributed to a specific element",
      "Findings reasoned over and independently re-verified",
      "Dwell time, time-to-first-focus, revisit count, per element",
      "Full scanpath, in the order attention actually moved",
    ],
  },
];

const sampleFinding = findings[0];
const sampleRecommendation = recommendations.find((r) => r.element === sampleFinding.element);

export default function Landing({ onNavigate }) {
  return (
    <div>
      {/* Hero -- text left, the gaze pattern itself as the actual visual
          centerpiece right. No fake browser window, no bare typography. */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28 pt-24">
        <div className="grid grid-cols-1 items-center gap-16 lg:grid-cols-[1fr_640px]">
          <StaggerGroup>
            <StaggerItem><Label>GAZE INTELLIGENCE / 01</Label></StaggerItem>
            <StaggerItem>
              <h1 className="mt-6 font-sans text-[48px] font-semibold leading-[1.08] tracking-tight text-text-primary md:text-[62px]">
                <span className="whitespace-nowrap">See what users</span>
                <br />
                actually see.
              </h1>
            </StaggerItem>
            <StaggerItem>
              <p className="mt-6 max-w-md text-[17px] leading-relaxed text-text-secondary">
                Point an ordinary webcam at someone using your interface and see exactly where their
                attention goes, then read findings you can actually act on.
              </p>
            </StaggerItem>
            <StaggerItem>
              <button
                onClick={() => onNavigate("dashboard")}
                className="mt-10 inline-flex items-center gap-2 text-[14px] font-medium text-text-primary transition-colors hover:text-accent"
              >
                Analyze your interface
                <span aria-hidden="true">→</span>
              </button>
            </StaggerItem>

            <StaggerItem>
              <div className="mt-16 border-t border-border pt-6">
                <p className="text-[11px] text-text-secondary">
                  From one real session, on the article page shown throughout this site:
                </p>
                <div className="mt-4 flex gap-10">
                  <div>
                    <div className="font-sans text-[28px] font-semibold text-text-primary">{overview.attentionScore}%</div>
                    <Label className="mt-1 block">of gaze time on one element</Label>
                  </div>
                  <div>
                    <div className="font-sans text-[28px] font-semibold text-text-primary">{overview.timeToFirstFocus}s</div>
                    <Label className="mt-1 block">until first fixation</Label>
                  </div>
                  <div>
                    <div className="font-sans text-[28px] font-semibold text-text-primary">{overview.coverage}%</div>
                    <Label className="mt-1 block">of the page ever seen</Label>
                  </div>
                </div>
              </div>
            </StaggerItem>
          </StaggerGroup>

          <Reveal delay={0.15}>
            <div className="relative aspect-square w-full">
              <GazeTrailDecorative seed={4} points={9} large className="text-accent" />
            </div>
          </Reveal>
        </div>
      </section>

      {/* What it does */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28">
        <Reveal>
          <SectionLabel index={2}>What it does</SectionLabel>
          <div className="grid grid-cols-1 gap-10 border-t border-border pt-10 md:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title}>
                <h3 className="font-sans text-[17px] font-semibold text-text-primary">{f.title}</h3>
                <p className="mt-3 text-[14px] leading-relaxed text-text-secondary">{f.body}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* Not just a heatmap -- the actual differentiator, stated plainly */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28">
        <Reveal>
          <SectionLabel index={3}>Not just a heatmap</SectionLabel>
          <p className="max-w-2xl border-t border-border pt-10 text-[15px] leading-relaxed text-text-primary">
            Most gaze tools stop at a colored overlay and leave you to guess what it means. Fixation
            attributes every fixation to a real element on the page, runs it through the same heuristics
            a UX researcher would reach for, and shows its work.
          </p>
          <div className="mt-10 grid grid-cols-1 gap-10 sm:grid-cols-2">
            {COMPARISON.map((col) => (
              <div key={col.label}>
                <h3 className={`font-sans text-[15px] font-semibold ${col.label === "Fixation" ? "text-accent" : "text-text-secondary"}`}>
                  {col.label}
                </h3>
                <ul className="mt-4 space-y-3">
                  {col.points.map((point) => (
                    <li key={point} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-text-secondary">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* Workflow */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28">
        <Reveal>
          <SectionLabel index={4}>How it works</SectionLabel>
          <div className="grid grid-cols-1 gap-10 border-t border-border pt-10 sm:grid-cols-2 lg:grid-cols-4">
            {workflow.map((w, i) => (
              <div key={w.step} className="relative">
                <Label>{w.step}</Label>
                <h3 className="mt-3 font-sans text-[18px] font-semibold text-text-primary">{w.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">{w.body}</p>
                {i < workflow.length - 1 && (
                  <span className="pointer-events-none absolute -right-5 top-1 hidden text-text-secondary lg:block">
                    →
                  </span>
                )}
              </div>
            ))}
          </div>
        </Reveal>
      </section>

      {/* A real sample finding, pulled from the same data shape the actual
          report uses -- proof by example instead of another claim. */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28">
        <Reveal>
          <SectionLabel index={5}>What a finding looks like</SectionLabel>
          <div className="border-t border-border pt-10">
            <div className="max-w-2xl">
              <span className="rounded-full border border-accent/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-accent">
                Impact: {sampleFinding.severity}
              </span>
              <p className="mt-4 text-[18px] leading-relaxed text-text-primary">{sampleFinding.issue}</p>
              <p className="mt-2 font-mono text-[12px] text-text-secondary">{sampleFinding.element}</p>
              <p className="mt-4 text-[13px] leading-relaxed text-text-secondary">{sampleFinding.evidence}</p>
              {sampleRecommendation && (
                <div className="mt-6 flex items-start gap-3">
                  <span className="mt-1 text-accent" aria-hidden="true">→</span>
                  <div>
                    <Label>Recommendation</Label>
                    <p className="mt-1 text-[14px] text-text-primary">{sampleRecommendation.text}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Reveal>
      </section>

      {/* Closing CTA */}
      <section className="mx-auto max-w-[1400px] px-8 pb-28">
        <Reveal className="border-t border-border pt-16 text-center">
          <h2 className="font-sans text-[32px] font-semibold leading-tight tracking-tight text-text-primary">
            Stop guessing what people see.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[14px] text-text-secondary">
            Calibrate once, record a real session, and read a report grounded in what actually happened.
          </p>
          <button
            onClick={() => onNavigate("dashboard")}
            className="mt-8 inline-flex h-11 items-center rounded-card bg-text-primary px-8 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            Get started
          </button>
        </Reveal>
      </section>

      <footer className="border-t border-border px-8 py-10">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between">
          <Label>Fixation · gaze-driven UX evaluation</Label>
          <Label>© 2026</Label>
        </div>
      </footer>
    </div>
  );
}
