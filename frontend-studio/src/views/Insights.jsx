import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { useReports, namer, pageName, shortDate } from "../lib/sessionData.js";
import { PageShell, PageHeader, Loading, NoReports, ErrorNote } from "../components/AppPage.jsx";
import { SEVERITY } from "./SessionReport.jsx";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "High", label: "Fix first" },
  { id: "Medium", label: "Worth fixing" },
  { id: "Low", label: "Minor" },
];

const AGENTS = [
  { key: "behavior", name: "Behaviour agent", does: "Reads the gaze numbers and describes what people did.", icon: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></> },
  { key: "evaluation", name: "Evaluation agent", does: "Checks that behaviour against usability principles.", icon: <><path d="M9 11l3 3 8-8" /><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9" /></> },
  { key: "recommendation", name: "Recommendation agent", does: "Suggests a concrete fix for each problem.", icon: <><path d="M9 18h6M10 22h4" /><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" /></> },
  { key: "critic", name: "Critic agent", does: "Double-checks every fix against the evidence and drops weak ones.", icon: <><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4z" /><path d="M9 12l2 2 4-4" /></> },
];

/** Every problem the AI found across all tests, with its fix. */
export default function Insights({ onNavigate, onOpenSession }) {
  const { token } = useAuth();
  const { loading, error, items } = useReports(token, 30);
  const [filter, setFilter] = useState("all");

  const { cards, agentStats } = useMemo(() => collect(items), [items]);
  const shown = filter === "all" ? cards : cards.filter((c) => c.issue.severity === filter);

  return (
    <PageShell wide>
      <PageHeader
        title="AI"
        accent="insights"
        subtitle="Four AI agents read the gaze data from each test, find what's not working and suggest how to fix it. Every finding comes with the numbers behind it."
      />
      {loading && <Loading />}
      {error && <ErrorNote error={error} />}
      {!loading && !error && items.length === 0 && <NoReports onNavigate={onNavigate} what="AI findings" />}

      {items.length > 0 && (
        <>
          <section className="mt-12">
            <h2 className="text-[24px] font-semibold tracking-tight text-text-primary">How the AI reached these</h2>
            <p className="mt-2 max-w-xl text-[15px] text-text-secondary">Each agent hands its work to the next. The last one throws out anything the data doesn't support.</p>
            <div className="relative mt-8 grid gap-4 md:grid-cols-4">
              <div aria-hidden="true" className="absolute left-[12%] right-[12%] top-[44px] hidden h-px bg-gradient-to-r from-accent/0 via-accent/50 to-accent/0 md:block" />
              {AGENTS.map((a, i) => (
                <motion.div
                  key={a.key}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: i * 0.12 }}
                  className="relative rounded-[22px] border border-white/10 bg-surface/70 p-6 backdrop-blur"
                >
                  <div className="flex items-center justify-between">
                    <span className="flex h-11 w-11 items-center justify-center rounded-[14px] bg-accent/15 text-accent ring-4 ring-bg">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{a.icon}</svg>
                    </span>
                    <span className="text-[12px] font-semibold text-text-secondary">Step {i + 1}</span>
                  </div>
                  <h3 className="mt-5 text-[17px] font-semibold text-text-primary">{a.name}</h3>
                  <p className="mt-1 text-[14px] leading-snug text-text-secondary">{a.does}</p>
                  <div className="mt-4 border-t border-white/10 pt-3 text-[14px] text-text-primary">{agentStats[a.key]}</div>
                </motion.div>
              ))}
            </div>
          </section>

          <section className="mt-14">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-[24px] font-semibold tracking-tight text-text-primary">Findings</h2>
                <p className="mt-2 text-[15px] text-text-secondary">From {items.length} {items.length === 1 ? "test" : "tests"}, most urgent first.</p>
              </div>
              <div className="flex flex-wrap gap-1 rounded-full border border-white/10 bg-surface/60 p-1 backdrop-blur">
                {FILTERS.map((f) => {
                  const n = f.id === "all" ? cards.length : cards.filter((c) => c.issue.severity === f.id).length;
                  return (
                    <button key={f.id} onClick={() => setFilter(f.id)} className={`relative rounded-full px-4 py-2 text-[14px] font-medium transition-colors ${filter === f.id ? "text-[#0A0E14]" : "text-text-secondary hover:text-text-primary"}`}>
                      {filter === f.id && <motion.span layoutId="insight-filter" className="absolute inset-0 -z-10 rounded-full bg-accent" transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
                      {f.label} <span className="opacity-70">{n}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {shown.length === 0 && (
              <div className="mt-6 rounded-[22px] border border-white/10 bg-surface/60 py-14 text-center text-[15px] text-text-secondary">
                {cards.length === 0 ? "No problems found in any test so far. Your pages are doing well." : "Nothing in this group."}
              </div>
            )}

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <AnimatePresence initial={false}>
                {shown.map((c, i) => (
                  <InsightCard key={c.key} card={c} index={i} onOpen={() => onOpenSession?.(c.session.id)} />
                ))}
              </AnimatePresence>
            </div>
          </section>
        </>
      )}
    </PageShell>
  );
}

function collect(items) {
  const order = { High: 0, Medium: 1, Low: 2 };
  const cards = [];
  let observed = 0, raw = 0, recRaw = 0, kept = 0, rejected = 0;
  for (const { session, report } of items) {
    const pr = report.pipeline_result || {};
    const nameOf = namer(report);
    const recs = pr.recommendations_kept || [];
    const b = pr.behavior_summary || {};
    observed += Object.keys(report.metrics?.dwell_time || {}).length;
    raw += (pr.issues_raw || pr.issues || []).length;
    recRaw += (pr.recommendations_raw || []).length || recs.length + (pr.recommendations_rejected || []).length;
    kept += recs.length;
    rejected += (pr.recommendations_rejected || []).length;
    (pr.issues || []).forEach((issue, i) => {
      const where = issue.element_label || nameOf(issue.element_id);
      const fix = recs.find((r) => (r.element_label || "") === where || (r.element_id && r.element_id === issue.element_id));
      cards.push({ key: `${session.id}-${i}`, session, issue, where, fix, ignored: (b.ignored_important_elements || []).length });
    });
  }
  cards.sort((a, b) => (order[a.issue.severity] ?? 3) - (order[b.issue.severity] ?? 3));
  return {
    cards,
    agentStats: {
      behavior: <><b className="text-accent">{observed}</b> page parts tracked</>,
      evaluation: <><b className="text-amber">{raw}</b> possible problems flagged</>,
      recommendation: <><b className="text-accent">{recRaw}</b> fixes drafted</>,
      critic: <><b className="text-accent">{kept}</b> kept · <b className="text-coral">{rejected}</b> thrown out</>,
    },
  };
}

function InsightCard({ card, index, onOpen }) {
  const { issue, where, fix, session } = card;
  const s = SEVERITY[issue.severity] || SEVERITY.Low;
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.35, delay: Math.min(index, 8) * 0.04 }}
      className="relative flex flex-col overflow-hidden rounded-[22px] border border-white/10 bg-surface/70 p-6 pl-8 backdrop-blur transition-colors hover:border-white/20"
    >
      <span className={`absolute inset-y-0 left-0 w-1.5 ${s.bg}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[13px] text-text-secondary">{pageName(session)} · {shortDate(session.created_at)}</div>
          <h3 className="mt-1 text-[19px] font-semibold leading-snug text-text-primary">{issue.issue}</h3>
          <div className="mt-1 text-[14px] text-text-secondary">On: <span className="text-text-primary">{where}</span></div>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-[13px] font-semibold ${s.soft} ${s.text}`}>{s.label}</span>
      </div>
      <p className="mt-4 rounded-[12px] bg-bg/60 px-3 py-2 font-mono text-[13px] leading-relaxed text-text-secondary">{issue.evidence}</p>
      {fix && (
        <div className="mt-4 flex gap-3 rounded-[14px] border border-accent/20 bg-accent/[0.06] p-4">
          <span className="mt-0.5 text-accent" aria-hidden="true">→</span>
          <div>
            <div className="text-[12px] font-semibold uppercase tracking-[0.1em] text-accent">Suggested fix</div>
            <p className="mt-1 text-[15px] leading-relaxed text-text-primary">{fix.recommendation.replace(/\s*\(Evidence:.*\)\s*$/, "")}</p>
          </div>
        </div>
      )}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-4">
        {issue.heuristic ? <span className="text-[12px] text-text-secondary/80">Principle: {issue.heuristic}</span> : <span />}
        <button onClick={onOpen} className="rounded-full border border-white/10 px-4 py-1.5 text-[13px] font-medium text-text-primary transition-colors hover:border-accent/50 hover:text-accent">
          See in report →
        </button>
      </div>
    </motion.article>
  );
}
