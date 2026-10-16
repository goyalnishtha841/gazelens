import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { useReports, namer, pageName } from "../lib/sessionData.js";
import { PageShell, PageHeader, Loading, NoReports, ErrorNote, SessionPicker } from "../components/AppPage.jsx";
import { VisualTabs, AttentionBars, FirstLookTimeline, EyePath } from "./SessionReport.jsx";

/** Where people looked on one test: heatmap, eye path and per-element charts. */
export default function GazeMap({ onNavigate, onOpenSession }) {
  const { token } = useAuth();
  const { loading, error, items } = useReports(token);
  const [picked, setPicked] = useState(null);
  const current = items.find((x) => x.session.id === picked) || items[0];

  return (
    <PageShell wide>
      <PageHeader
        title="Gaze"
        accent="map"
        subtitle="See exactly where eyes went on a page: the hot spots, the order things were noticed, and what was missed."
      >
        {items.length > 0 && <SessionPicker items={items} value={current?.session.id} onChange={setPicked} />}
      </PageHeader>

      {loading && <Loading />}
      {error && <ErrorNote error={error} />}
      {!loading && !error && items.length === 0 && <NoReports onNavigate={onNavigate} what="Your heatmaps" />}

      <AnimatePresence mode="wait">
        {current && (
          <motion.div key={current.session.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }}>
            <MapBody item={current} onOpenSession={onOpenSession} />
          </motion.div>
        )}
      </AnimatePresence>
    </PageShell>
  );
}

function MapBody({ item, onOpenSession }) {
  const { session, report } = item;
  const m = report.metrics || {};
  const nameOf = namer(report);
  const b = report.pipeline_result?.behavior_summary || {};
  const ttff = m.ttff || {};
  const seen = Object.keys(ttff).length;
  const all = Object.keys(m.dwell_time || {}).length;
  const fixations = Object.values(m.fixation_count || {}).reduce((a, c) => a + c, 0);

  const facts = [
    { label: "Noticed first", value: b.first_noticed ? nameOf(b.first_noticed) : "–" },
    { label: "Most attention", value: b.most_attended ? nameOf(b.most_attended) : "–" },
    { label: "Parts noticed", value: all ? `${seen} of ${all}` : "–" },
    { label: "Times eyes paused", value: fixations || "–" },
  ];

  return (
    <div className="mt-10 space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <VisualTabs sessionId={session.id} />
        <div className="flex flex-col gap-3">
          {facts.map((f) => (
            <div key={f.label} className="rounded-[20px] border border-white/10 bg-surface/60 p-5 backdrop-blur">
              <div className="text-[13px] text-text-secondary">{f.label}</div>
              <div className="mt-1 truncate text-[20px] font-semibold text-text-primary" title={String(f.value)}>{f.value}</div>
            </div>
          ))}
          <button
            onClick={() => onOpenSession?.(session.id)}
            className="mt-auto h-12 rounded-full border border-white/10 text-[15px] font-medium text-text-primary transition-colors hover:border-accent/50 hover:text-accent"
          >
            Open the full report →
          </button>
        </div>
      </div>

      {m.scanpath?.length > 0 && <EyePath scanpath={m.scanpath} nameOf={nameOf} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <AttentionBars metrics={m} nameOf={nameOf} />
        <FirstLookTimeline metrics={m} nameOf={nameOf} />
      </div>
      <p className="text-center text-[13px] text-text-secondary">Showing {pageName(session)}. Pick another test from the menu above.</p>
    </div>
  );
}
