import { useMemo, useRef } from "react";
import { motion, useInView } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { useCountUp } from "../components/Primitives.jsx";
import { StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import { useReports, pageName, shortDate } from "../lib/sessionData.js";
import { PageShell, PageHeader, Loading, NoReports, ErrorNote } from "../components/AppPage.jsx";

const SEV = [
  { key: "High", label: "Fix first", color: "var(--color-coral)" },
  { key: "Medium", label: "Worth fixing", color: "var(--color-amber)" },
  { key: "Low", label: "Minor", color: "var(--color-cool)" },
];

/** Trends across every finished test: problems, tracking accuracy, and
 *  how well important parts of each page got noticed. */
export default function Analytics({ onNavigate, onOpenSession }) {
  const { token } = useAuth();
  const { loading, error, items } = useReports(token, 30);
  const data = useMemo(() => summarise(items), [items]);

  return (
    <PageShell wide>
      <PageHeader
        title="Your"
        accent="analytics"
        subtitle="How your pages are doing across every test: what keeps coming up, how precise the eye tracking was, and whether the important parts get noticed."
      />
      {loading && <Loading />}
      {error && <ErrorNote error={error} />}
      {!loading && !error && items.length === 0 && <NoReports onNavigate={onNavigate} what="Your charts" />}

      {data && (
        <div className="mt-10 space-y-6">
          <StaggerGroup className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StaggerItem><Tile label="Tests analysed" value={data.tests} /></StaggerItem>
            <StaggerItem><Tile label="Problems found" value={data.problems} tone="text-amber" /></StaggerItem>
            <StaggerItem><Tile label="Fixes suggested" value={data.fixes} tone="text-accent" /></StaggerItem>
            <StaggerItem><Tile label="Ideas the AI threw out" value={data.rejected} tone="text-cool" hint="Suggestions the checker agent rejected as not backed by the data" /></StaggerItem>
          </StaggerGroup>

          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <Panel title="Problems in each test" note="Newest on the right. Colours show how urgent each problem is.">
              <ProblemBars rows={data.perTest} onOpen={onOpenSession} />
              <Legend />
            </Panel>
            <Panel title="How urgent" note="All problems found so far.">
              <Donut counts={data.bySeverity} />
            </Panel>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="What keeps coming up" note="Problems grouped by the design principle they break.">
              <HBars rows={data.byPrinciple} empty="No problems found yet. Nice." />
            </Panel>
            <Panel title="Did the important parts get seen?" note="Share of each page's key elements (buttons, headlines) that were looked at.">
              <HBars rows={data.importantSeen} unit="%" max={100} gradient empty="No key elements were marked on these pages." />
            </Panel>
          </div>

          <Panel title="Eye-tracking precision (px off)" note="How far, on average, our estimate of where eyes looked was from where they really looked. Lower is better. This measures the eye tracking, not the report.">
            <AccuracyLine rows={data.accuracy} />
          </Panel>
        </div>
      )}
    </PageShell>
  );
}

function summarise(items) {
  if (!items.length) return null;
  const chrono = [...items].reverse();
  const bySeverity = { High: 0, Medium: 0, Low: 0 };
  const principle = {};
  let problems = 0, fixes = 0, rejected = 0;
  const perTest = [], importantSeen = [], accuracy = [];
  for (const { session, report } of chrono) {
    const pr = report.pipeline_result || {};
    const m = report.metrics || {};
    const issues = pr.issues || [];
    const counts = { High: 0, Medium: 0, Low: 0 };
    for (const i of issues) {
      counts[i.severity] = (counts[i.severity] || 0) + 1;
      bySeverity[i.severity] = (bySeverity[i.severity] || 0) + 1;
      if (i.heuristic) principle[i.heuristic] = (principle[i.heuristic] || 0) + 1;
    }
    problems += issues.length;
    fixes += (pr.recommendations_kept || []).length;
    rejected += (pr.recommendations_rejected || []).length;
    const label = pageName(session);
    perTest.push({ id: session.id, label, date: shortDate(session.created_at), counts, total: issues.length });
    const important = Object.entries(m.element_importance || {}).filter(([, v]) => v === "high").map(([k]) => k);
    if (important.length) {
      const seen = important.filter((id) => (m.ttff || {})[id] != null).length;
      importantSeen.push({ label: `${label} · ${shortDate(session.created_at)}`, value: Math.round((100 * seen) / important.length) });
    }
    const px = pr.quality?.gaze_error_px;
    if (px != null) accuracy.push({ label, date: shortDate(session.created_at), px, level: pr.quality.level });
  }
  return {
    tests: items.length, problems, fixes, rejected, bySeverity, perTest, accuracy,
    importantSeen: importantSeen.slice(-8),
    byPrinciple: Object.entries(principle).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([label, value]) => ({ label, value })),
  };
}

function Tile({ label, value, tone = "text-text-primary", hint }) {
  const n = useCountUp(value, 900);
  return (
    <div className="h-full rounded-[20px] border border-white/10 bg-surface/60 p-6 backdrop-blur" title={hint}>
      <div className={`text-[34px] font-bold tabular-nums tracking-tight ${tone}`}>{n}</div>
      <div className="mt-1 text-[14px] text-text-secondary">{label}</div>
    </div>
  );
}

function Panel({ title, note, children }) {
  return (
    <div className="h-full rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <h3 className="text-[19px] font-semibold text-text-primary">{title}</h3>
      {note && <p className="mt-1 text-[13px] text-text-secondary">{note}</p>}
      <div className="mt-6">{children}</div>
    </div>
  );
}

function Legend() {
  return (
    <div className="mt-5 flex flex-wrap gap-4 text-[13px] text-text-secondary">
      {SEV.map((s) => (
        <span key={s.key} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${s.color})` }} />{s.label}</span>
      ))}
    </div>
  );
}

function ProblemBars({ rows, onOpen }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const shown = rows.slice(-12);
  const max = Math.max(3, ...shown.map((r) => r.total));
  return (
    <div ref={ref} className="flex h-[220px] items-end gap-3 border-b border-white/10 pb-0">
      {shown.map((r, i) => (
        <button key={r.id} onClick={() => onOpen?.(r.id)} title={`${r.label}, ${r.date}: ${r.total} problem(s)`} className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end">
          <span className="mb-1.5 text-[12px] font-semibold tabular-nums text-text-secondary group-hover:text-text-primary">{r.total}</span>
          <motion.div
            className="flex w-full max-w-[44px] flex-col-reverse overflow-hidden rounded-t-[10px] bg-white/[0.04] ring-1 ring-white/5 group-hover:ring-accent/40"
            initial={{ height: 6 }}
            animate={inView ? { height: `${Math.max(4, (r.total / max) * 170)}px` } : undefined}
            transition={{ duration: 0.9, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
          >
            {SEV.map((s) => r.counts[s.key] > 0 && (
              <div key={s.key} style={{ flexGrow: r.counts[s.key], background: `rgb(${s.color})` }} />
            ))}
          </motion.div>
          <span className="mt-2 w-full truncate text-center text-[11px] text-text-secondary">{r.date}</span>
        </button>
      ))}
    </div>
  );
}

function Donut({ counts }) {
  const total = SEV.reduce((a, s) => a + (counts[s.key] || 0), 0);
  const R = 70, C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row lg:flex-col xl:flex-row">
      <div className="relative h-[180px] w-[180px] shrink-0">
        <svg viewBox="0 0 180 180" className="h-full w-full -rotate-90">
          <circle cx="90" cy="90" r={R} fill="none" stroke="rgb(255 255 255 / 0.06)" strokeWidth="18" />
          {total > 0 && SEV.map((s, i) => {
            const frac = (counts[s.key] || 0) / total;
            const el = frac > 0 && (
              <motion.circle key={s.key} cx="90" cy="90" r={R} fill="none" stroke={`rgb(${s.color})`} strokeWidth="18"
                strokeDasharray={`${frac * C} ${C}`} initial={{ strokeDashoffset: C }} whileInView={{ strokeDashoffset: -offset * C }}
                viewport={{ once: true }} transition={{ duration: 1, delay: i * 0.15, ease: [0.22, 1, 0.36, 1] }} />
            );
            offset += frac;
            return el;
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[34px] font-bold tabular-nums text-text-primary">{total}</span>
          <span className="text-[13px] text-text-secondary">problems</span>
        </div>
      </div>
      <div className="w-full space-y-3">
        {SEV.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-3 rounded-[14px] bg-bg/50 px-4 py-3">
            <span className="flex items-center gap-2.5 text-[15px] text-text-primary"><span className="h-3 w-3 rounded-full" style={{ background: `rgb(${s.color})` }} />{s.label}</span>
            <span className="text-[15px] font-semibold tabular-nums text-text-primary">{counts[s.key] || 0}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function HBars({ rows, unit = "", max, gradient = false, empty }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  if (!rows.length) return <p className="py-8 text-center text-[15px] text-text-secondary">{empty}</p>;
  const top = max ?? Math.max(...rows.map((r) => r.value));
  return (
    <div ref={ref} className="space-y-4">
      {rows.map((r, i) => (
        <div key={r.label}>
          <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[14px]">
            <span className="truncate text-text-primary" title={r.label}>{r.label}</span>
            <span className="shrink-0 font-semibold tabular-nums text-text-secondary">{r.value}{unit}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/[0.05]">
            <motion.div
              className={`h-full rounded-full ${gradient ? (r.value < 50 ? "bg-coral" : "bg-gradient-to-r from-cool via-accent to-accent") : "bg-gradient-to-r from-amber to-coral"}`}
              initial={{ width: 0 }}
              animate={inView ? { width: `${Math.max(2, (r.value / (top || 1)) * 100)}%` } : undefined}
              transition={{ duration: 0.9, delay: i * 0.07, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function AccuracyLine({ rows }) {
  if (rows.length === 0) return <p className="py-8 text-center text-[15px] text-text-secondary">No tracking measurements yet.</p>;
  const shown = rows.slice(-14);
  const W = 1100, H = 190, P = 32;
  const max = Math.max(200, ...shown.map((r) => r.px)) * 1.1;
  const x = (i) => (shown.length === 1 ? W / 2 : P + (i * (W - 2 * P)) / (shown.length - 1));
  const y = (px) => H - P - (px / max) * (H - 2 * P);
  const path = shown.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.px)}`).join(" ");
  const colour = { good: "var(--color-accent)", limited: "var(--color-amber)", insufficient: "var(--color-coral)" };
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H + 20}`} className="w-full min-w-[520px]">
        <defs>
          <linearGradient id="acc-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgb(var(--color-accent))" stopOpacity="0.25" />
            <stop offset="100%" stopColor="rgb(var(--color-accent))" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={P} x2={W - P} y1={P + f * (H - 2 * P)} y2={P + f * (H - 2 * P)} stroke="rgb(255 255 255 / 0.06)" />
        ))}
        {shown.length > 1 && <path d={`${path} L${x(shown.length - 1)},${H - P} L${x(0)},${H - P} Z`} fill="url(#acc-fill)" />}
        <motion.path d={path} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="2.5" strokeLinecap="round"
          initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1.4, ease: "easeInOut" }} />
        {shown.map((r, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(r.px)} r="6" fill="rgb(var(--color-bg))" stroke={`rgb(${colour[r.level] || colour.good})`} strokeWidth="3" />
            <text x={x(i)} y={y(r.px) - 12} textAnchor="middle" fontSize="13" fill="rgb(var(--color-text-secondary))">{Math.round(r.px)}px</text>
            <text x={x(i)} y={H + 12} textAnchor="middle" fontSize="12" fill="rgb(var(--color-text-secondary))">{r.date}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}
