import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { getSessionReport, downloadSessionPdf } from "../api/client.js";
import { useCountUp } from "../components/Primitives.jsx";
import { Reveal } from "../components/Motion.jsx";
import IrisMark from "../components/IrisMark.jsx";
import ReportImage from "../components/ReportImage.jsx";
import { pageName as pageNameOf } from "../lib/sessionData.js";

/*
 * The session report: the page people come back to and show others.
 *
 * Everything below the verdict is drawn from the report's own data:
 * pipeline_result (quality gate, consolidated issues, recommendations,
 * element labels) and metrics (dwell time, first-look time, fixations,
 * eye path per element). The heatmap and eye-path images come from the
 * backend; the charts are drawn live here so they can animate.
 */

const REPORT_POLL_MS = 2000;
const DWELL_THRESHOLD_PCT = 5;     // agents/rules.py CTA_DWELL_POOR_VISIBILITY_PCT

export const SEVERITY = {
  High: { text: "text-coral", bg: "bg-coral", soft: "bg-coral/10", border: "border-coral/40", label: "Fix first" },
  Medium: { text: "text-amber", bg: "bg-amber", soft: "bg-amber/10", border: "border-amber/40", label: "Worth fixing" },
  Low: { text: "text-cool", bg: "bg-cool", soft: "bg-cool/10", border: "border-cool/40", label: "Minor" },
};

const QUALITY = {
  good: { label: "Good", text: "text-accent", stroke: "rgb(var(--color-accent))", note: "Accurate enough to point at individual parts of the page." },
  limited: { label: "Fair", text: "text-amber", stroke: "rgb(var(--color-amber))", note: "Good for larger areas; small buttons are less certain." },
  insufficient: { label: "Too low", text: "text-coral", stroke: "rgb(var(--color-coral))", note: "Not reliable enough to draw conclusions." },
};

export default function SessionReport({ sessionId, onBack }) {
  const { token } = useAuth();
  const [report, setReport] = useState(null);
  const [pollError, setPollError] = useState(null);
  const [pdfState, setPdfState] = useState("idle"); // idle | downloading | success | error
  const pollRef = useRef(null);
  const successTimerRef = useRef(null);

  const handleDownloadPdf = async () => {
    clearTimeout(successTimerRef.current);
    setPdfState("downloading");
    try {
      await downloadSessionPdf(token, sessionId);
      setPdfState("success");
      successTimerRef.current = setTimeout(() => setPdfState("idle"), 1800);
    } catch {
      setPdfState("error");
    }
  };

  useEffect(() => () => clearTimeout(successTimerRef.current), []);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await getSessionReport(token, sessionId);
        if (cancelled) return;
        setReport(data);
        if (!data.ready) pollRef.current = setTimeout(poll, REPORT_POLL_MS);
      } catch (err) {
        if (!cancelled) setPollError(err.message || "Couldn't load the report");
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(pollRef.current);
    };
  }, [sessionId, token]);

  if (pollError || !report || !report.ready) {
    return <ReportWaiting error={pollError} report={report} onBack={onBack} />;
  }
  return <ReportBody report={report} onBack={onBack} pdfState={pdfState} onDownload={handleDownloadPdf} />;
}

/* ====================================================================== */

function ReportBody({ report, onBack, pdfState, onDownload }) {
  const pr = report.pipeline_result;
  const m = report.metrics || {};
  const quality = pr.quality;
  const labels = pr.element_labels || {};
  const nameOf = (id) => (id === "__session__" ? "Whole page" : labels[id] || id.replace(/_/g, " "));
  const issues = pr.issues || [];
  const recs = pr.recommendations_kept || [];
  const insufficient = quality?.level === "insufficient";
  const pageName = pageNameOf(report) || "your page";
  const created = report.created_at ? new Date(report.created_at) : null;

  const totalFixations = Object.values(m.fixation_count || {}).reduce((a, b) => a + b, 0);
  const worst = issues[0]?.severity;
  const tone = insufficient ? "coral" : worst === "High" ? "coral" : worst === "Medium" ? "amber" : issues.length ? "cool" : "accent";
  const headline = insufficient
    ? <>Not enough <Serif className="text-coral">reliable</Serif> data</>
    : issues.length === 0
      ? <>Nothing important was <Serif className="text-accent">missed</Serif></>
      : <>{issues.length} {issues.length === 1 ? "thing" : "things"} <Serif className={toneText(tone)}>worth fixing</Serif></>;

  const summary = useMemo(() => {
    if (insufficient) {
      return "The gaze tracking in this session wasn't accurate enough to say which parts of the page people looked at, so GazeLens didn't draw any conclusions. Recalibrate and run it again.";
    }
    const b = pr.behavior_summary || {};
    const parts = [];
    if (b.first_noticed) parts.push(`People noticed ${nameOf(b.first_noticed)} first`);
    if (b.most_attended && b.most_attended !== b.first_noticed) parts.push(`spent the most time on ${nameOf(b.most_attended)}`);
    let s = parts.length ? `${parts.join(" and ")}.` : "";
    if (b.ignored_important_elements?.length) {
      s += ` ${b.ignored_important_elements.map(nameOf).join(", ")} ${b.ignored_important_elements.length === 1 ? "was" : "were"} barely looked at, even though ${b.ignored_important_elements.length === 1 ? "it matters" : "they matter"}.`;
    }
    if (!issues.length) s += " Attention went where you'd expect on this page.";
    return s.trim();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report]);

  return (
    <div className="mx-auto max-w-[1180px] overflow-x-clip px-5 pb-24 pt-8 sm:px-8">
      {/* ---------------------------------------------------------- header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <button onClick={onBack} className="rounded-full border border-white/10 bg-surface/50 px-4 py-2 text-[14px] text-text-secondary backdrop-blur transition-colors hover:text-text-primary">
          ← All sessions
        </button>
        <div className="flex items-center gap-2">
          <span className="hidden rounded-full border border-white/10 px-3 py-1.5 font-mono text-[12px] text-text-secondary sm:inline">{report.session_id}</span>
          <button
            onClick={onDownload}
            disabled={pdfState === "downloading"}
            className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-[14px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)] disabled:opacity-60"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {pdfState === "success" ? <path d="M4 12.5 9.5 18 20 6" /> : <path d="M12 3v13m0 0-5-5m5 5 5-5M4 20h16" />}
            </svg>
            {pdfState === "downloading" ? "Preparing…" : pdfState === "success" ? "Downloaded" : "Download PDF"}
          </button>
        </div>
      </div>
      {pdfState === "error" && <p className="mt-2 text-right text-[13px] text-coral">No PDF is available for this session.</p>}

      {/* ---------------------------------------------------------- verdict */}
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative mt-6 overflow-hidden rounded-[28px] border border-white/10 bg-surface/70 backdrop-blur-xl"
      >
        <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: `radial-gradient(60% 90% at 0% 0%, ${toneGlow(tone)}, transparent 60%), radial-gradient(40% 70% at 100% 100%, rgb(var(--color-cool) / 0.10), transparent 60%)` }} />
        <div className="relative grid grid-cols-1 items-center gap-10 p-7 sm:p-10 lg:grid-cols-[1fr_auto]">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <span className="rounded-full bg-white/[0.06] px-3 py-1 font-medium text-text-primary">{pageName}</span>
              {created && <span className="text-text-secondary">{created.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</span>}
            </div>
            <h1 className="mt-5 text-[38px] font-bold leading-[1.05] tracking-[-0.025em] text-text-primary sm:text-[54px]">{headline}</h1>
            <p className="mt-4 max-w-[640px] text-[17px] leading-relaxed text-text-secondary">{summary}</p>
            {!insufficient && issues.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-2">
                {["High", "Medium", "Low"].map((sev) => {
                  const n = issues.filter((i) => i.severity === sev).length;
                  if (!n) return null;
                  return (
                    <span key={sev} className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] font-medium ${SEVERITY[sev].border} ${SEVERITY[sev].text}`}>
                      <span className={`h-2 w-2 rounded-full ${SEVERITY[sev].bg}`} />{n} {SEVERITY[sev].label.toLowerCase()}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
          <AccuracyRing quality={quality} />
        </div>
      </motion.section>

      {/* ---------------------------------------------------------- stats */}
      <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile icon="eye" label="Noticed first" value={pr.behavior_summary?.first_noticed ? nameOf(pr.behavior_summary.first_noticed) : "—"} />
        <StatTile icon="flame" label="Most attention" value={pr.behavior_summary?.most_attended ? nameOf(pr.behavior_summary.most_attended) : "—"} />
        <StatTile icon="clock" label="Time tracked" number={Math.round(m.total_gaze_time || 0)} suffix=" s" />
        <StatTile icon="dots" label="Places looked at" number={totalFixations} />
      </div>

      {/* ---------------------------------------------------------- visuals */}
      <Reveal once className="mt-14">
        <SectionTitle eyebrow="Where attention went" title="See it on the page" />
        <VisualTabs sessionId={report.session_id} />
      </Reveal>

      {!insufficient && (
        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.15fr_0.85fr]">
          <Reveal once><AttentionBars metrics={m} nameOf={nameOf} /></Reveal>
          <Reveal once delay={0.08}><FirstLookTimeline metrics={m} nameOf={nameOf} /></Reveal>
        </div>
      )}
      {!insufficient && (m.scanpath || []).length > 0 && (
        <Reveal once className="mt-5"><EyePath scanpath={m.scanpath} nameOf={nameOf} /></Reveal>
      )}

      {/* ---------------------------------------------------------- issues */}
      <section className="mt-16">
        <SectionTitle eyebrow="What to fix" title={issues.length ? "Problems we found" : "No problems found"} />
        {issues.length === 0 ? (
          <Reveal once>
            <div className="rounded-[22px] border border-white/10 bg-surface/60 p-8 text-center text-[16px] text-text-secondary">
              {insufficient ? "Not evaluated: the gaze data wasn't reliable enough." : "People found the important parts of this page without trouble."}
            </div>
          </Reveal>
        ) : (
          <div className="space-y-4">
            {issues.map((issue, i) => <IssueCard key={`${issue.element_id}-${i}`} issue={issue} nameOf={nameOf} index={i} />)}
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------- fixes */}
      {recs.length > 0 && (
        <section className="mt-16">
          <SectionTitle eyebrow="Suggested fixes" title="What to try next" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {recs.map((rec, i) => <RecommendationCard key={`${rec.element_id}-${i}`} rec={rec} nameOf={nameOf} index={i} />)}
          </div>
        </section>
      )}

      {/* ---------------------------------------------------------- reliability */}
      <Reveal once className="mt-16">
        <ReliabilityCard quality={quality} nameOf={nameOf} rejected={(pr.recommendations_rejected || []).length} warnings={report.warnings || []} />
      </Reveal>
    </div>
  );
}

/* ====================================================================== */
/* pieces */

export function Serif({ children, className = "" }) {
  return <span className={`font-serif font-normal italic ${className}`}>{children}</span>;
}
function toneText(t) {
  return { coral: "text-coral", amber: "text-amber", cool: "text-cool", accent: "text-accent" }[t];
}
function toneGlow(t) {
  return `rgb(var(--color-${t === "accent" ? "accent" : t}) / 0.18)`;
}

export function SectionTitle({ eyebrow, title }) {
  return (
    <div className="mb-6">
      <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
      <h2 className="mt-2 text-[30px] font-bold tracking-[-0.02em] text-text-primary sm:text-[36px]">{title}</h2>
    </div>
  );
}

/** Circular gauge of how accurate the gaze tracking was. */
function AccuracyRing({ quality }) {
  const reduce = useReducedMotion();
  const level = quality?.level;
  const q = QUALITY[level];
  const px = quality?.gaze_error_px != null ? Math.round(quality.gaze_error_px) : null;
  const shown = useCountUp(px ?? 0, 1100);
  // 0% of the screen = full ring; 20% or worse = empty
  const fill = quality?.gaze_error_pct_diagonal != null ? Math.max(0.06, 1 - quality.gaze_error_pct_diagonal / 20) : 0;
  const R = 70;
  const C = 2 * Math.PI * R;
  return (
    <div className="flex flex-col items-center">
      <div className="relative h-[184px] w-[184px]">
        <svg viewBox="0 0 184 184" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="92" cy="92" r={R} fill="none" stroke="rgb(var(--color-border))" strokeWidth="12" />
          {q && (
            <motion.circle
              cx="92" cy="92" r={R} fill="none" stroke={q.stroke} strokeWidth="12" strokeLinecap="round"
              strokeDasharray={C}
              initial={{ strokeDashoffset: reduce ? C * (1 - fill) : C }}
              animate={{ strokeDashoffset: C * (1 - fill) }}
              transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
              style={{ filter: `drop-shadow(0 0 10px ${q.stroke})` }}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          {px != null ? (
            <>
              <span className="text-[34px] font-bold leading-none tabular-nums text-text-primary">{shown}<span className="text-[16px] font-medium text-text-secondary"> px</span></span>
              <span className="mt-1 text-[12px] text-text-secondary">tracking error</span>
            </>
          ) : (
            <span className="px-6 text-[13px] text-text-secondary">Accuracy not measured</span>
          )}
        </div>
      </div>
      {q && (
        <div className="mt-3 max-w-[220px] text-center">
          <span className={`text-[15px] font-semibold ${q.text}`}>Accuracy: {q.label}</span>
          <p className="mt-1 text-[12px] leading-snug text-text-secondary">{q.note}</p>
        </div>
      )}
    </div>
  );
}

const ICONS = {
  eye: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" /><circle cx="12" cy="12" r="3" /></>,
  flame: <><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="6.5" opacity=".6" /><circle cx="12" cy="12" r="10" opacity=".3" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  dots: <><circle cx="5" cy="18" r="2" /><circle cx="12" cy="6" r="2" /><circle cx="19" cy="15" r="2" /><path d="M6.2 16.4 10.8 7.6M13.6 7.3l4.2 6.2" /></>,
};

function StatTile({ icon, label, value, number, suffix = "" }) {
  const counted = useCountUp(typeof number === "number" ? number : 0, 900);
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.15 }}
      className="min-w-0 rounded-[20px] border border-white/10 bg-surface/60 p-5 backdrop-blur"
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-accent/10 text-accent">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[icon]}</svg>
      </span>
      <div className="mt-4 truncate text-[22px] font-bold tracking-tight text-text-primary sm:text-[26px]" title={value}>
        {typeof number === "number" ? `${counted}${suffix}` : value}
      </div>
      <div className="mt-0.5 text-[13px] text-text-secondary">{label}</div>
    </motion.div>
  );
}

/** Heatmap / eye-path images in one framed viewer. */
export function VisualTabs({ sessionId }) {
  const { token } = useAuth();
  const [tab, setTab] = useState("heatmap");
  const tabs = [
    { id: "heatmap", label: "Heatmap", hint: "Warm colours show where people looked the longest." },
    { id: "scanpath", label: "Eye path", hint: "Numbered in the order people looked at things." },
  ];
  return (
    <div className="relative">
      <div aria-hidden="true" className="pointer-events-none absolute -inset-6 -z-10 opacity-70 blur-3xl" style={{ background: "radial-gradient(45% 50% at 30% 40%, rgb(var(--color-accent) / 0.16), transparent 70%), radial-gradient(40% 45% at 75% 65%, rgb(var(--color-amber) / 0.12), transparent 70%)" }} />
      <div className="overflow-hidden rounded-[24px] border border-white/10 bg-surface/70 backdrop-blur-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div className="flex gap-1 rounded-full bg-bg/60 p-1">
            {tabs.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)} className={`relative rounded-full px-4 py-1.5 text-[14px] font-medium transition-colors ${tab === t.id ? "text-[#0A0E14]" : "text-text-secondary hover:text-text-primary"}`}>
                {tab === t.id && <motion.span layoutId="report-tab" className="absolute inset-0 -z-10 rounded-full bg-accent" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
                <span className="relative">{t.label}</span>
              </button>
            ))}
          </div>
          <span className="text-[13px] text-text-secondary">{tabs.find((t) => t.id === tab).hint}</span>
        </div>
        <div className="relative max-h-[760px] min-h-[280px] overflow-y-auto bg-bg/40">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }} className="p-3">
              <ReportImage natural token={token} sessionId={sessionId} kind={tab} alt={tab === "heatmap" ? "Gaze heatmap over the page" : "Eye path in the order people looked"} emptyLabel="Not available for this session." />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/** Share of attention per element, animated in. */
export function AttentionBars({ metrics, nameOf }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const reduce = useReducedMotion();
  const dwell = metrics.dwell_time || {};
  const total = Object.values(dwell).reduce((a, b) => a + b, 0) || 1;
  const rows = Object.entries(dwell)
    .map(([id, s]) => ({ id, pct: (100 * s) / total, important: metrics.element_importance?.[id] === "high" }))
    .sort((a, b) => b.pct - a.pct);
  // a captured website can have dozens of parts; keep the top ones plus any
  // important element that fell short, since those are the story
  const shown = rows.filter((r, i) => i < 12 || (r.important && r.pct < DWELL_THRESHOLD_PCT)).slice(0, 16);
  const hidden = rows.length - shown.length;
  const max = Math.max(DWELL_THRESHOLD_PCT * 2, ...rows.map((r) => r.pct));
  return (
    <div ref={ref} className="h-full rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[19px] font-semibold text-text-primary">Share of attention</h3>
        <span className="text-[12px] text-text-secondary">dashed line = {DWELL_THRESHOLD_PCT}%</span>
      </div>
      <div className="relative mt-5 space-y-3">
        <div aria-hidden="true" className="absolute bottom-0 top-0 border-l border-dashed border-text-secondary/40" style={{ left: `calc(9.5rem + (100% - 9.5rem - 3rem) * ${DWELL_THRESHOLD_PCT / max})` }} />
        {shown.map((r, i) => {
          const low = r.important && r.pct < DWELL_THRESHOLD_PCT;
          return (
            <div key={r.id} className="grid grid-cols-[9.5rem_1fr_3rem] items-center gap-0 text-[14px]">
              <span className={`truncate pr-3 ${low ? "text-coral" : "text-text-primary"}`} title={nameOf(r.id)}>
                {nameOf(r.id)}{r.important && <span className="ml-1 text-[11px] text-text-secondary">★</span>}
              </span>
              <div className="h-3 overflow-hidden rounded-full bg-white/[0.05]">
                <motion.div
                  className={`h-full rounded-full ${low ? "bg-coral" : "bg-gradient-to-r from-cool via-accent to-amber"}`}
                  initial={{ width: reduce ? `${(r.pct / max) * 100}%` : 0 }}
                  animate={inView ? { width: `${Math.max(1.5, (r.pct / max) * 100)}%` } : undefined}
                  transition={{ duration: 1, delay: 0.1 + i * 0.07, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              <span className={`text-right font-mono text-[13px] tabular-nums ${low ? "text-coral" : "text-text-secondary"}`}>{r.pct.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
      <p className="mt-5 text-[12px] text-text-secondary">★ important element · red = important but below the line{hidden > 0 ? ` · ${hidden} smaller parts not shown` : ""}</p>
    </div>
  );
}

/** When each element was first looked at; never-seen ones at the end. */
export function FirstLookTimeline({ metrics, nameOf }) {
  const ttff = metrics.ttff || {};
  const seen = Object.entries(ttff).sort((a, b) => a[1] - b[1]);
  const neverAll = Object.keys(metrics.dwell_time || {}).filter((id) => !(id in ttff));
  const never = neverAll.slice(0, 6);
  return (
    <div className="h-full rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <h3 className="text-[19px] font-semibold text-text-primary">First look</h3>
      <p className="mt-1 text-[13px] text-text-secondary">How many seconds before each part was first noticed.</p>
      <ol className="relative mt-5 space-y-3 border-l border-white/10 pl-5">
        {seen.slice(0, 12).map(([id, s], i) => (
          <motion.li key={id} initial={{ opacity: 0, x: -8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.06 }} className="relative flex items-center justify-between gap-3 text-[14px]">
            <span className={`absolute -left-[26px] h-3 w-3 rounded-full ring-4 ring-surface ${s > 5 ? "bg-amber" : "bg-accent"}`} />
            <span className="truncate text-text-primary">{nameOf(id)}</span>
            <span className={`shrink-0 font-mono text-[13px] ${s > 5 ? "text-amber" : "text-text-secondary"}`}>{s.toFixed(1)} s</span>
          </motion.li>
        ))}
        {never.map((id) => (
          <li key={id} className="relative flex items-center justify-between gap-3 text-[14px]">
            <span className="absolute -left-[26px] h-3 w-3 rounded-full bg-coral/80 ring-4 ring-surface" />
            <span className="truncate text-text-secondary">{nameOf(id)}</span>
            <span className="shrink-0 text-[12px] text-coral">never looked at</span>
          </li>
        ))}
        {neverAll.length > never.length && (
          <li className="text-[13px] text-text-secondary">+ {neverAll.length - never.length} more never looked at</li>
        )}
      </ol>
    </div>
  );
}

/** The order attention moved in, as numbered steps. */
export function EyePath({ scanpath, nameOf }) {
  const steps = scanpath.filter((id, i) => i === 0 || scanpath[i - 1] !== id).slice(0, 14);
  return (
    <div className="rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[19px] font-semibold text-text-primary">The path their eyes took</h3>
        {scanpath.length > steps.length && <span className="text-[12px] text-text-secondary">first {steps.length} steps</span>}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {steps.map((id, i) => (
          <motion.span key={`${id}-${i}`} initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }} className="flex items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-bg/60 py-1.5 pl-1.5 pr-3.5 text-[14px] text-text-primary">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[12px] font-bold text-[#0A0E14]">{i + 1}</span>
              {nameOf(id)}
            </span>
            {i < steps.length - 1 && <span className="text-text-secondary/60">→</span>}
          </motion.span>
        ))}
      </div>
    </div>
  );
}

export function IssueCard({ issue, nameOf, index }) {
  const s = SEVERITY[issue.severity] || SEVERITY.Low;
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay: index * 0.06 }}
      className="relative overflow-hidden rounded-[22px] border border-white/10 bg-surface/70 p-6 pl-8 backdrop-blur transition-colors hover:border-white/20"
    >
      <span className={`absolute inset-y-0 left-0 w-1.5 ${s.bg}`} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-text-secondary">{issue.element_label || nameOf(issue.element_id)}</div>
          <h3 className="mt-1 text-[20px] font-semibold leading-snug text-text-primary">{issue.issue}</h3>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-[13px] font-semibold ${s.soft} ${s.text}`}>{s.label}</span>
      </div>
      <p className="mt-3 inline-block rounded-[10px] bg-bg/60 px-3 py-2 font-mono text-[13px] leading-relaxed text-text-secondary">{issue.evidence}</p>
      {issue.also?.length > 0 && <p className="mt-3 text-[14px] text-text-secondary">Also: {issue.also.join("; ")}</p>}
      {issue.caveat && <p className="mt-2 text-[13px] italic text-text-secondary">{issue.caveat}</p>}
      {issue.heuristic && <p className="mt-3 text-[12px] text-text-secondary/80">Design principle: {issue.heuristic}</p>}
    </motion.article>
  );
}

export function RecommendationCard({ rec, nameOf, index }) {
  const reduce = useReducedMotion();
  const pct = Math.round((rec.confidence || 0) * 100);
  const R = 22;
  const C = 2 * Math.PI * R;
  const strong = rec.support === "Strong";
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay: index * 0.06 }}
      className="flex h-full gap-5 rounded-[22px] border border-white/10 bg-surface/70 p-6 backdrop-blur transition-colors hover:border-accent/30"
    >
      <div className="relative h-[56px] w-[56px] shrink-0">
        <svg viewBox="0 0 56 56" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="28" cy="28" r={R} fill="none" stroke="rgb(var(--color-border))" strokeWidth="5" />
          <motion.circle cx="28" cy="28" r={R} fill="none" stroke={strong ? "rgb(var(--color-accent))" : "rgb(var(--color-amber))"} strokeWidth="5" strokeLinecap="round"
            strokeDasharray={C} initial={{ strokeDashoffset: reduce ? C * (1 - pct / 100) : C }} whileInView={{ strokeDashoffset: C * (1 - pct / 100) }} viewport={{ once: true }} transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-[13px] font-bold text-text-primary">{pct}</span>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-medium text-text-secondary">{rec.element_label || nameOf(rec.element_id)}</span>
          <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${strong ? "bg-accent/15 text-accent" : "bg-amber/15 text-amber"}`}>{strong ? "Strong evidence" : "Weaker evidence"}</span>
        </div>
        <p className="mt-2 text-[16px] leading-relaxed text-text-primary">{rec.recommendation.replace(/\s*\(Evidence:.*\)\s*$/, "")}</p>
        {rec.also?.length > 0 && <p className="mt-2 text-[13px] text-text-secondary">Also consider: {rec.also.map((a) => a.replace(/\s*\(Evidence:.*\)\s*$/, "")).join(" ")}</p>}
        {rec.measurability != null && rec.measurability < 1 && (
          <p className="mt-2 text-[12px] text-text-secondary">Confidence lowered from {Math.round(rec.confidence_raw * 100)}: this element is small compared with the tracking error.</p>
        )}
      </div>
    </motion.article>
  );
}

function ReliabilityCard({ quality, nameOf, rejected, warnings }) {
  const q = QUALITY[quality?.level];
  return (
    <div className="grid grid-cols-1 gap-6 rounded-[24px] border border-white/10 bg-surface/60 p-7 backdrop-blur md:grid-cols-[auto_1fr]">
      <span className="flex h-14 w-14 items-center justify-center rounded-[16px] bg-accent/10 text-accent">
        <IrisMark size={30} />
      </span>
      <div>
        <h3 className="text-[22px] font-semibold text-text-primary">How reliable is this report?</h3>
        <p className="mt-2 text-[15px] leading-relaxed text-text-secondary">
          {q ? <>Tracking accuracy was <span className={`font-semibold ${q.text}`}>{q.label.toLowerCase()}</span>{quality?.gaze_error_px != null && <> ({Math.round(quality.gaze_error_px)} px, {quality.gaze_error_pct_diagonal?.toFixed(1)}% of the screen, measured by the accuracy check)</>}. {q.note}</> : "Tracking accuracy wasn't measured for this session, so treat the findings with care."}
          {" "}Every suggestion was re-checked against the measurements by a separate checking step{rejected ? `, which dropped ${rejected} that the data didn't support` : ""}.
        </p>
        {quality?.reasons?.length > 0 && (
          <ul className="mt-3 space-y-1 text-[14px] text-text-secondary">{quality.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
        )}
        {quality?.low_confidence_elements?.length > 0 && (
          <p className="mt-3 text-[14px] text-text-secondary">Too small to measure precisely: {quality.low_confidence_elements.map(nameOf).join(", ")}.</p>
        )}
        {quality?.level === "limited" && <p className="mt-2 text-[14px] text-amber">Because accuracy was only fair, nothing is marked “Fix first”.</p>}
        {warnings.length > 0 && <p className="mt-2 text-[13px] text-text-secondary/80">{warnings.join(" ")}</p>}
      </div>
    </div>
  );
}

/** Loading / failed state while the analysis runs. */
function ReportWaiting({ error, report, onBack }) {
  const failed = error || report?.status === "failed";
  const message = error || (report?.status === "failed" ? `Analysis failed: ${report.message || "unknown error"}` : "Analysing your session…");
  const steps = ["Finding where people looked", "Matching it to the page", "Checking what was missed", "Writing your report"];
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (failed) return undefined;
    const id = setInterval(() => setActive((a) => Math.min(a + 1, steps.length - 1)), 1400);
    return () => clearInterval(id);
  }, [failed, steps.length]);
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-[560px] flex-col items-center justify-center px-6 text-center">
      <span className={`drop-shadow-[0_0_20px_rgb(var(--color-accent)/0.6)] ${failed ? "text-coral" : "text-accent"}`}><IrisMark size={64} wander={!failed} /></span>
      <h1 className="mt-6 text-[28px] font-bold tracking-tight text-text-primary">{failed ? "Something went wrong" : "Building your report"}</h1>
      <p className={`mt-2 text-[16px] ${failed ? "text-coral" : "text-text-secondary"}`}>{message}</p>
      {!failed && (
        <ul className="mt-8 w-full space-y-2 text-left">
          {steps.map((s, i) => (
            <li key={s} className={`flex items-center gap-3 rounded-[14px] border px-4 py-3 text-[15px] transition-colors ${i <= active ? "border-accent/30 bg-accent/[0.06] text-text-primary" : "border-white/10 text-text-secondary"}`}>
              <span className={`h-2.5 w-2.5 rounded-full ${i < active ? "bg-accent" : i === active ? "animate-pulse bg-accent" : "bg-text-secondary/30"}`} />
              {s}
            </li>
          ))}
        </ul>
      )}
      <button onClick={onBack} className="mt-8 rounded-full border border-white/10 px-5 py-2.5 text-[14px] text-text-secondary transition-colors hover:text-text-primary">← Back to sessions</button>
    </div>
  );
}
