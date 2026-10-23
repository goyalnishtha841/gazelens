import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { downloadSessionPdf } from "../api/client.js";
import ReportImage from "../components/ReportImage.jsx";
import { useReports, pageName, shortDate } from "../lib/sessionData.js";
import { PageShell, PageHeader, Loading, NoReports, ErrorNote } from "../components/AppPage.jsx";

const QUALITY = {
  good: { label: "Eye-tracking precision: good", cls: "text-accent" },
  limited: { label: "Eye-tracking precision: fair", cls: "text-amber" },
  insufficient: { label: "Eye-tracking precision: too low", cls: "text-coral" },
};

/** Every finished report, as cards with a heatmap preview and a PDF. */
export default function Reports({ onNavigate, onOpenSession }) {
  const { token } = useAuth();
  const { loading, error, items } = useReports(token, 40);
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? items.filter((x) => pageName(x.session).toLowerCase().includes(q)) : items;
  }, [items, query]);

  return (
    <PageShell wide>
      <PageHeader title="Your" accent="reports" subtitle="Every finished test, ready to open, share or download as a PDF.">
        {items.length > 0 && (
          <div className="relative w-full sm:w-72">
            <svg className="pointer-events-none absolute left-4 top-1/2 z-10 -translate-y-1/2 text-text-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by page or website"
              className="h-12 w-full rounded-full border border-white/10 bg-surface/60 pl-11 pr-4 text-[15px] text-text-primary outline-none backdrop-blur transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
            />
          </div>
        )}
      </PageHeader>

      {loading && <Loading />}
      {error && <ErrorNote error={error} />}
      {!loading && !error && items.length === 0 && <NoReports onNavigate={onNavigate} what="Your reports" />}
      {items.length > 0 && shown.length === 0 && (
        <div className="mt-10 rounded-[22px] border border-white/10 bg-surface/60 py-14 text-center text-[15px] text-text-secondary">Nothing matches "{query}".</div>
      )}

      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((x, i) => (
          <ReportCard key={x.session.id} item={x} index={i} token={token} onOpen={() => onOpenSession?.(x.session.id)} />
        ))}
      </div>
    </PageShell>
  );
}

function ReportCard({ item, index, token, onOpen }) {
  const { session, report } = item;
  const pr = report.pipeline_result || {};
  const issues = pr.issues || [];
  const high = issues.filter((i) => i.severity === "High").length;
  const fixes = (pr.recommendations_kept || []).length;
  const q = QUALITY[pr.quality?.level];
  const [pdf, setPdf] = useState("idle");

  async function download(e) {
    e.stopPropagation();
    setPdf("busy");
    try {
      await downloadSessionPdf(token, session.id);
      setPdf("idle");
    } catch {
      setPdf("error");
    }
  }

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay: Math.min(index, 6) * 0.06 }}
      onClick={onOpen}
      className="group flex cursor-pointer flex-col overflow-hidden rounded-[24px] border border-white/10 bg-surface/70 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-[0_24px_60px_-25px_rgb(var(--color-accent)/0.45)]"
    >
      <div className="relative h-[190px] overflow-hidden border-b border-white/10 bg-bg/60">
        <div className="h-full w-full transition-transform duration-500 group-hover:scale-[1.03]">
          <ReportImage token={token} sessionId={session.id} kind="heatmap" alt={`Heatmap for ${pageName(session)}`} cover />
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface to-transparent" />
        {q && <span className={`absolute left-3 top-3 rounded-full border border-white/10 bg-bg/85 px-2.5 py-1 text-[12px] font-semibold backdrop-blur ${q.cls}`}>{q.label}</span>}
      </div>
      <div className="flex flex-1 flex-col p-5">
        <div className="text-[13px] text-text-secondary">{shortDate(session.created_at)}</div>
        <h3 className="mt-0.5 truncate text-[18px] font-semibold text-text-primary transition-colors group-hover:text-accent" title={pageName(session)}>{pageName(session)}</h3>
        <div className="mt-4 flex flex-wrap gap-2 text-[13px]">
          <span className={`rounded-full px-3 py-1 ${issues.length ? "bg-amber/15 text-amber" : "bg-accent/15 text-accent"}`}>
            {issues.length ? `${issues.length} to fix` : "Nothing to fix"}
          </span>
          {high > 0 && <span className="rounded-full bg-coral/15 px-3 py-1 text-coral">{high} urgent</span>}
          {fixes > 0 && <span className="rounded-full bg-white/[0.06] px-3 py-1 text-text-primary">{fixes} {fixes === 1 ? "fix" : "fixes"} suggested</span>}
        </div>
        <div className="mt-auto flex items-center justify-between gap-3 pt-5">
          <button
            onClick={download}
            disabled={pdf === "busy"}
            className="flex items-center gap-2 rounded-full border border-white/10 px-4 py-2 text-[13px] font-medium text-text-primary transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-60"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></svg>
            {pdf === "busy" ? "Preparing…" : pdf === "error" ? "PDF not ready" : "PDF"}
          </button>
          <span className="text-[14px] font-medium text-accent">Open →</span>
        </div>
      </div>
    </motion.article>
  );
}
