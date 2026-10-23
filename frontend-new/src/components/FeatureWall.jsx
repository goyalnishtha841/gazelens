import IrisMark from "./IrisMark.jsx";
import {
  AccuracyMeter, BulbIcon, ClockIcon, CursorIcon, EyeOffIcon, FileIcon, GlobeIcon, HeatIcon,
  LayoutIcon, MiniHeatmap, MiniPath, MissedList, MoveIcon, PathIcon, ShieldIcon, TargetIcon,
} from "./LandingVisuals.jsx";

/**
 * Every feature on a tilted wall of cards that slowly drifts, columns moving
 * in opposite directions (the idea from cairn's feature section). Hovering a
 * column pauses it. Below desktop width it becomes an ordinary grid, so the
 * cards are always readable.
 */

const TONE = {
  cool: "bg-cool/10 text-cool",
  accent: "bg-accent/10 text-accent",
  amber: "bg-amber/10 text-amber",
  coral: "bg-coral/10 text-coral",
};

const FEATURES = [
  {
    icon: <HeatIcon />, tone: "amber", title: "A heatmap of attention",
    text: "Warm colours show where people looked the longest. Cool colours show what they barely saw.",
    visual: <MiniHeatmap label={null} />,
  },
  {
    icon: <EyeOffIcon />, tone: "coral", title: "What got missed",
    text: "Important buttons and forms that people skipped, or found too late.",
    visual: <MissedList />,
  },
  {
    icon: <BulbIcon />, tone: "accent", title: "Fixes in plain words",
    text: "Every problem comes with a simple suggestion you can act on.",
    visual: (
      <div className="rounded-[12px] rounded-tl-[4px] border border-accent/25 bg-accent/10 p-3.5 text-[14px] leading-relaxed text-text-primary">
        “Make the <span className="font-semibold">Add to cart</span> button bigger and move it above the reviews.”
      </div>
    ),
  },
  {
    icon: <TargetIcon />, tone: "cool", title: "Precision check first",
    text: "A quick test before you start measures how precisely your eyes are tracked.",
    visual: <AccuracyMeter />,
  },
  {
    icon: <PathIcon />, tone: "cool", title: "The path eyes took",
    text: "Numbered dots show the order people looked at things.",
    visual: <MiniPath />,
  },
  {
    icon: <GlobeIcon />, tone: "accent", title: "Works on any website",
    text: "Use a sample page or paste a link to your own site.",
    visual: (
      <div className="flex items-center gap-2 rounded-full border border-border bg-bg p-1.5 pl-4 text-[14px]">
        <span className="min-w-0 flex-1 truncate text-text-secondary">your-website.com</span>
        <span className="rounded-full bg-accent px-3.5 py-1.5 text-[13px] font-semibold text-[#0A0E14]">Test</span>
      </div>
    ),
  },
  {
    icon: <FileIcon />, tone: "amber", title: "Share as a PDF",
    text: "A clean report for your team, your client or your teacher.",
    visual: (
      <div className="flex items-center gap-3 rounded-[12px] border border-border bg-bg p-3">
        <span className="flex h-12 w-10 flex-col justify-center gap-1 rounded-[4px] bg-surface px-1.5 shadow-sm">
          {[100, 80, 90, 60].map((w) => <span key={w} className="block h-[3px] rounded-full bg-text-secondary/40" style={{ width: `${w}%` }} />)}
        </span>
        <span className="text-[13px] text-text-secondary">product-page-report.pdf</span>
      </div>
    ),
  },
  {
    icon: <ShieldIcon />, tone: "accent", title: "Private by default",
    text: "Camera video is used for a moment, then thrown away.",
    visual: (
      <div className="space-y-1.5 text-[13px]">
        <div className="flex items-center justify-between rounded-[10px] border border-border bg-bg px-3 py-2"><span className="text-text-secondary">Camera video</span><span className="font-semibold text-accent">never saved</span></div>
        <div className="flex items-center justify-between rounded-[10px] border border-border bg-bg px-3 py-2"><span className="text-text-secondary">Where you looked</span><span className="font-semibold text-text-primary">kept for your report</span></div>
      </div>
    ),
  },
  {
    icon: <LayoutIcon />, tone: "coral", title: "5 sample pages",
    text: "Practise on ready-made pages before testing your own.",
    visual: (
      <div className="flex flex-wrap gap-1.5">
        {["Shop", "Login", "Form", "Dashboard", "News"].map((p) => (
          <span key={p} className="rounded-full border border-border bg-bg px-3 py-1 text-[13px] text-text-primary">{p}</span>
        ))}
      </div>
    ),
  },
  {
    icon: <CursorIcon />, tone: "accent", title: "A live gaze dot",
    text: "Watch a dot follow your eyes while you test, so you know it's working.",
    visual: (
      <div className="relative h-16 overflow-hidden rounded-[12px] border border-border bg-bg">
        <span className="absolute left-[30%] top-1/2 -translate-y-1/2 animate-pulse text-accent drop-shadow-[0_0_10px_rgb(var(--color-accent)/0.7)]"><IrisMark size={28} /></span>
        <span className="absolute left-[12%] top-[35%] h-1.5 w-1.5 rounded-full bg-accent/30" />
        <span className="absolute left-[20%] top-[55%] h-1.5 w-1.5 rounded-full bg-accent/50" />
      </div>
    ),
  },
  {
    icon: <MoveIcon />, tone: "amber", title: "Tells you if you move",
    text: "Lean in or turn away, and GazeLens asks you to sit back where you were.",
  },
  {
    icon: <ClockIcon />, tone: "cool", title: "Ready in seconds",
    text: "Your report appears a few seconds after you finish the test.",
    visual: (
      <div className="h-2 overflow-hidden rounded-full bg-border">
        <span className="block h-full w-[86%] rounded-full bg-gradient-to-r from-cool via-accent to-amber" />
      </div>
    ),
  },
];

function FeatureCard({ f }) {
  return (
    <div className="rounded-[20px] border border-border bg-surface p-6 shadow-[0_20px_50px_-30px_rgba(0,0,0,0.6)]">
      <div className="flex items-center gap-3">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] ${TONE[f.tone]}`}>{f.icon}</span>
        <h3 className="text-[18px] font-semibold tracking-tight text-text-primary">{f.title}</h3>
      </div>
      <p className="mt-3 text-[15px] leading-relaxed text-text-secondary">{f.text}</p>
      {f.visual && <div className="mt-4">{f.visual}</div>}
    </div>
  );
}

const COLUMNS = [0, 1, 2, 3].map((c) => FEATURES.filter((_, i) => i % 4 === c));
const DURATIONS = ["58s", "70s", "52s", "64s"];

export default function FeatureWall() {
  return (
    <>
      {/* desktop: the tilted, drifting wall */}
      <div
        className="relative hidden h-[760px] overflow-hidden lg:block"
        style={{
          maskImage: "linear-gradient(to bottom, transparent, black 14%, black 86%, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent, black 14%, black 86%, transparent)",
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            maskImage: "linear-gradient(to right, transparent, black 10%, black 90%, transparent)",
            WebkitMaskImage: "linear-gradient(to right, transparent, black 10%, black 90%, transparent)",
            perspective: "1800px",
          }}
        >
          <div
            className="absolute -inset-x-[6%] -top-[30%] grid h-[160%] grid-cols-4 gap-5"
            style={{ transform: "rotateX(26deg) rotateZ(-9deg) scale(1.06)", transformOrigin: "50% 40%" }}
          >
            {COLUMNS.map((col, ci) => (
              <div key={ci} className="overflow-hidden">
                <div
                  className="flex flex-col gap-5 hover:[animation-play-state:paused]"
                  style={{ animation: `${ci % 2 ? "wall-down" : "wall-up"} ${DURATIONS[ci]} linear infinite` }}
                >
                  {[...col, ...col, ...col, ...col].map((f, i) => <FeatureCard key={`${f.title}-${i}`} f={f} />)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* smaller screens: a plain grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:hidden">
        {FEATURES.map((f) => <FeatureCard key={f.title} f={f} />)}
      </div>
    </>
  );
}
