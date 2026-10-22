import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { listSessions, deleteSession } from "../api/client.js";
import { Card, useCountUp } from "../components/Primitives.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import IrisMark from "../components/IrisMark.jsx";
import { pageName } from "../lib/sessionData.js";

const STATUS = {
  created: { label: "Not started", tone: "text-text-secondary bg-white/[0.06]" },
  calibrated: { label: "Ready to record", tone: "text-cool bg-cool/15" },
  recording: { label: "Recording", tone: "text-amber bg-amber/15" },
  processing: { label: "Building report", tone: "text-amber bg-amber/15" },
  complete: { label: "Report ready", tone: "text-accent bg-accent/15" },
  failed: { label: "Failed", tone: "text-coral bg-coral/15" },
};

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function StatusChip({ status }) {
  const st = STATUS[status] || { label: status, tone: "text-text-secondary bg-white/[0.06]" };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px] font-medium ${st.tone}`}>
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${status === "processing" || status === "recording" ? "animate-pulse" : ""}`} />
      {st.label}
    </span>
  );
}

function Tile({ label, value, tone = "text-text-primary" }) {
  const counted = useCountUp(value, 900);
  return (
    <div className="rounded-[20px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <div className={`text-[34px] font-bold tabular-nums tracking-tight ${tone}`}>{counted}</div>
      <div className="mt-1 text-[14px] text-text-secondary">{label}</div>
    </div>
  );
}

/** Real session list -- ported from frontend/src/views/Dashboard.jsx's list
 * half (the report-viewing half moved to SessionReport.jsx). */
export default function Dashboard({ onNavigate, onOpenSession, hasCalibration }) {
  const { token } = useAuth();
  const [sessions, setSessions] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [filter, setFilter] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    listSessions(token)
      .then((data) => {
        if (!cancelled) setSessions(data.sessions);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.message || "Couldn't load sessions");
      });
    return () => {
      cancelled = true;
    };
  }, [token, reloadTick]);

  const filteredSessions = useMemo(() => {
    if (!sessions) return null;
    if (!filter.trim()) return sessions;
    const q = filter.trim().toLowerCase();
    return sessions.filter((s) => pageName(s).toLowerCase().includes(q) || (s.ui_page || "").toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [sessions, filter]);

  const stats = useMemo(() => {
    if (!sessions) return null;
    const reported = sessions.filter((s) => s.issue_count != null);
    return {
      total: sessions.length,
      completed: sessions.filter((s) => s.status === "complete").length,
      totalIssues: reported.reduce((sum, s) => sum + s.issue_count, 0),
      highSeverity: sessions.reduce((sum, s) => sum + (s.high_issue_count || 0), 0),
      reportedCount: reported.length,
    };
  }, [sessions]);

  const handleDelete = async (sessionId) => {
    setDeletingId(sessionId);
    try {
      await deleteSession(token, sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const btn = "rounded-full bg-accent font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)]";

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-10 sm:px-8 sm:py-14">
      <Reveal className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text-primary sm:text-[52px]">
            Your <span className="font-serif font-normal italic text-accent">sessions</span>
          </h1>
          <p className="mt-3 max-w-lg text-[17px] leading-relaxed text-text-secondary">
            Every test you've run lives here. Open one to see its heatmap and the list of things to fix.
          </p>
        </div>
        <button onClick={() => onNavigate?.("session")} className={`h-12 px-6 text-[15px] ${btn}`}>
          + New test
        </button>
      </Reveal>

      {stats && stats.total > 0 && (
        <StaggerGroup className="mt-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StaggerItem><Tile value={stats.total} label="Tests run" /></StaggerItem>
          <StaggerItem><Tile value={stats.completed} label="Reports ready" tone="text-accent" /></StaggerItem>
          <StaggerItem><Tile value={stats.totalIssues} label="Problems found" tone={stats.totalIssues > 0 ? "text-amber" : "text-text-primary"} /></StaggerItem>
          <StaggerItem><Tile value={stats.highSeverity} label="Fix first" tone={stats.highSeverity > 0 ? "text-coral" : "text-text-primary"} /></StaggerItem>
        </StaggerGroup>
      )}

      {sessions?.length > 0 && (
        <div className="mt-12 flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-[24px] font-semibold tracking-tight text-text-primary">All tests</h2>
          <div className="relative w-full sm:w-72">
            <svg className="pointer-events-none absolute left-4 top-1/2 z-10 -translate-y-1/2 text-text-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search by page name"
              className="h-11 w-full rounded-full border border-white/10 bg-surface/60 pl-11 pr-4 text-[15px] text-text-primary outline-none backdrop-blur transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
            />
          </div>
        </div>
      )}

      {!sessions && !loadError && (
        <div className="flex flex-col items-center py-20 text-center">
          <IrisMark size={44} />
          <p className="mt-4 text-[15px] text-text-secondary">Loading your sessions…</p>
        </div>
      )}

      {loadError && (
        <Card className="mt-8 py-12 text-center">
          <p className="text-[15px] text-text-secondary">We couldn't load your sessions. {loadError}</p>
          <button onClick={() => setReloadTick((n) => n + 1)} className={`mt-5 h-11 px-6 text-[14px] ${btn}`}>Try again</button>
        </Card>
      )}

      {sessions?.length === 0 && (
        <Reveal>
          <div className="relative mt-10 overflow-hidden rounded-[28px] border border-white/10 bg-surface/60 px-6 py-14 text-center backdrop-blur sm:px-12">
            <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(50% 70% at 50% 0%, rgb(var(--color-accent) / 0.12), transparent 70%)" }} />
            <div className="relative">
              <div className="mx-auto flex w-fit"><IrisMark size={56} /></div>
              <h3 className="mt-6 text-[28px] font-bold tracking-tight text-text-primary">
                No tests <span className="font-serif font-normal italic text-accent">yet</span>
              </h3>
              <p className="mx-auto mt-3 max-w-md text-[16px] leading-relaxed text-text-secondary">
                It only takes three steps. Your first report is a few minutes away.
              </p>
              <div className="mx-auto mt-10 grid max-w-2xl gap-3 text-left sm:grid-cols-3">
                {[
                  { n: 1, label: "Set up the camera", body: "Follow a dot for about a minute.", done: hasCalibration },
                  { n: 2, label: "Run a test", body: "Use a page while we follow your eyes.", done: false },
                  { n: 3, label: "Read the report", body: "See what was missed and how to fix it.", done: false },
                ].map((step) => (
                  <div key={step.n} className="rounded-[18px] border border-white/10 bg-bg/50 p-5">
                    <span className={`flex h-8 w-8 items-center justify-center rounded-full text-[14px] font-semibold ${step.done ? "bg-accent text-[#0A0E14]" : "bg-white/[0.07] text-text-primary"}`}>
                      {step.done ? "✓" : step.n}
                    </span>
                    <div className="mt-4 text-[16px] font-semibold text-text-primary">{step.label}</div>
                    <div className="mt-1 text-[14px] text-text-secondary">{step.body}</div>
                  </div>
                ))}
              </div>
              <button onClick={() => onNavigate?.("session")} className={`mt-10 h-12 px-7 text-[15px] ${btn}`}>
                {hasCalibration ? "Run your first test" : "Set up the camera"}
              </button>
            </div>
          </div>
        </Reveal>
      )}

      {sessions?.length > 0 && filteredSessions?.length === 0 && (
        <Card className="mt-6 py-12 text-center text-[15px] text-text-secondary">Nothing matches "{filter}".</Card>
      )}

      {filteredSessions?.length > 0 && (
        <StaggerGroup className="mt-6 grid gap-4 md:grid-cols-2">
          {filteredSessions.map((s) => (
            <StaggerItem key={s.id}>
              <div
                onClick={() => s.has_report && onOpenSession?.(s.id)}
                className={`group relative h-full overflow-hidden rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur transition-all duration-300 ${
                  s.has_report
                    ? "cursor-pointer hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[0_20px_60px_-25px_rgb(var(--color-accent)/0.45)]"
                    : "cursor-default"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[14px] bg-gradient-to-br from-accent/25 to-cool/25 text-[18px] font-bold text-text-primary">
                      {pageName(s).charAt(0)}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-[18px] font-semibold text-text-primary transition-colors group-hover:text-accent">{pageName(s)}</h3>
                      <div className="mt-0.5 text-[13px] text-text-secondary">{when(s.created_at) || s.id}</div>
                    </div>
                  </div>
                  <StatusChip status={s.status} />
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3" onClick={(e) => e.stopPropagation()}>
                  <div className="flex flex-wrap items-center gap-2 text-[13px]">
                    {s.issue_count != null ? (
                      <>
                        <span className="rounded-full bg-white/[0.06] px-3 py-1 text-text-primary">
                          {s.issue_count} problem{s.issue_count !== 1 ? "s" : ""}
                        </span>
                        {s.high_issue_count > 0 && (
                          <span className="rounded-full bg-coral/15 px-3 py-1 font-medium text-coral">{s.high_issue_count} to fix first</span>
                        )}
                      </>
                    ) : (
                      <span className="text-text-secondary">No report yet</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {confirmDeleteId === s.id ? (
                      <>
                        <span className="text-[13px] text-text-secondary">Delete this test?</span>
                        <button
                          onClick={() => handleDelete(s.id)}
                          disabled={deletingId === s.id}
                          className="rounded-full bg-coral/15 px-3 py-1.5 text-[13px] font-medium text-coral hover:bg-coral/25 disabled:opacity-50"
                        >
                          {deletingId === s.id ? "Deleting…" : "Delete"}
                        </button>
                        <button onClick={() => setConfirmDeleteId(null)} className="rounded-full px-3 py-1.5 text-[13px] text-text-secondary hover:bg-white/[0.06]">
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => setConfirmDeleteId(s.id)}
                          aria-label="Delete session"
                          className="rounded-full px-3 py-1.5 text-[13px] text-text-secondary transition-colors hover:bg-white/[0.06] hover:text-coral"
                        >
                          Delete
                        </button>
                        {s.has_report && (
                          <button onClick={() => onOpenSession?.(s.id)} className="rounded-full border border-white/10 px-4 py-1.5 text-[13px] font-medium text-text-primary transition-colors group-hover:border-accent/50 group-hover:text-accent">
                            View report →
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerGroup>
      )}
    </div>
  );
}
