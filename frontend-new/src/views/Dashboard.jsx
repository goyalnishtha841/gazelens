import { useState, useEffect, useMemo } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { listSessions, deleteSession } from "../api/client.js";
import { Card, Label, SectionLabel, Stat } from "../components/Primitives.jsx";
import { StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import { GazeTrailDecorative } from "../components/GazeTrail.jsx";

const STATUS_LABEL = {
  created: "Created",
  calibrated: "Calibrated",
  recording: "Recording",
  processing: "Processing",
  complete: "Complete",
  failed: "Failed",
};

const CATEGORY_LABEL = {
  ecommerce_product_page: "E-Commerce",
  form_page: "Form",
  dashboard_page: "Dashboard",
  login_page: "Login",
  article_page: "Article",
};

function categoryLabel(uiPage) {
  return CATEGORY_LABEL[uiPage] || (uiPage || "").replace(/_/g, " ");
}

function StatusPill({ status }) {
  return (
    <span className="rounded-full border border-border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide text-text-secondary">
      {STATUS_LABEL[status] || status}
    </span>
  );
}

// A quiet visual echo of the report's own gaze dot -- solid accent once a
// report exists, a faint pulse while still working, dim otherwise. Small,
// but it's a status glance that doesn't need the pill's text read first.
function StatusDot({ status }) {
  if (status === "complete") return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />;
  if (status === "processing" || status === "recording") {
    return <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />;
  }
  return <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-border" />;
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
    return sessions.filter((s) => (s.ui_page || "").toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
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

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Label>Research hub</Label>
          <h1 className="mt-1 font-sans text-[26px] font-semibold text-text-primary">Sessions</h1>
          <p className="mt-1 max-w-md text-[13px] text-text-secondary">
            Every session you've calibrated and recorded, with its status and findings.
          </p>
        </div>
        <button
          onClick={() => onNavigate?.(hasCalibration ? "session" : "calibration")}
          className="flex h-10 items-center gap-2 rounded-card bg-text-primary px-5 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
        >
          + New session
        </button>
      </div>

      {stats && stats.total > 0 && (
        <StaggerGroup className="mt-10 grid grid-cols-2 gap-6 border-b border-border pb-10 lg:grid-cols-4">
          <StaggerItem><Stat value={stats.total} label="Sessions run" /></StaggerItem>
          <StaggerItem><Stat value={stats.completed} label="Analyses complete" /></StaggerItem>
          <StaggerItem>
            <Stat value={stats.totalIssues} label={`Issues (${stats.reportedCount} reported)`} accent={stats.totalIssues > 0} />
          </StaggerItem>
          <StaggerItem><Stat value={stats.highSeverity} label="High severity" accent={stats.highSeverity > 0} /></StaggerItem>
        </StaggerGroup>
      )}

      <div className="mt-8 flex items-center justify-between">
        <SectionLabel>All sessions</SectionLabel>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter sessions…"
          className="h-9 w-56 rounded-card border border-border bg-surface px-3 text-[13px] text-text-primary outline-none transition-colors focus:border-accent"
        />
      </div>

      {!sessions && !loadError && (
        <div className="py-16 text-center">
          <div className="relative mx-auto mb-4 h-6 w-40">
            <GazeTrailDecorative seed={2} points={3} edgeToEdge className="text-accent" />
          </div>
          <p className="text-[13px] text-text-secondary">Loading sessions…</p>
        </div>
      )}

      {loadError && (
        <Card className="mt-4 py-12 text-center">
          <p className="text-[13px] text-text-secondary">Couldn't load sessions: {loadError}</p>
          <button
            onClick={() => setReloadTick((n) => n + 1)}
            className="mt-4 h-9 rounded-card border border-border px-5 text-[13px] font-medium text-text-primary transition-colors hover:border-accent"
          >
            Retry
          </button>
        </Card>
      )}

      {sessions?.length === 0 && (
        <Card className="mt-4 py-16 text-center">
          <div className="relative mx-auto mb-6 h-10 w-48">
            <GazeTrailDecorative seed={6} points={5} edgeToEdge className="text-accent" />
          </div>
          <h3 className="font-sans text-[18px] font-semibold text-text-primary">No sessions yet</h3>
          <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-secondary">
            Every session starts the same way: calibrate the gaze model to your face and camera, then record
            someone using a test page. The report generates automatically once you finalize.
          </p>
          <div className="mx-auto mt-8 flex max-w-lg flex-col gap-3 text-left sm:flex-row">
            {[
              { n: "01", label: "Calibrate", done: hasCalibration },
              { n: "02", label: "Record a session", done: false },
              { n: "03", label: "Read the report", done: false },
            ].map((step) => (
              <div key={step.n} className="flex flex-1 items-center gap-3 rounded-card border border-border p-3">
                <span className={`font-mono text-[13px] ${step.done ? "text-accent" : "text-text-secondary"}`}>
                  {step.done ? "✓" : step.n}
                </span>
                <span className="text-[13px] text-text-primary">{step.label}</span>
              </div>
            ))}
          </div>
          <button
            onClick={() => onNavigate?.(hasCalibration ? "session" : "calibration")}
            className="mt-8 h-11 rounded-card bg-text-primary px-6 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            {hasCalibration ? "Start a session" : "Start with calibration"}
          </button>
        </Card>
      )}

      {sessions?.length > 0 && filteredSessions?.length === 0 && (
        <Card className="mt-4 py-12 text-center text-[13px] text-text-secondary">No sessions match that filter.</Card>
      )}

      {filteredSessions?.length > 0 && (
        <StaggerGroup className="mt-4 divide-y divide-border overflow-hidden rounded-card border border-border">
          {filteredSessions.map((s) => (
            <StaggerItem key={s.id}>
            <div
              onClick={() => s.has_report && onOpenSession?.(s.id)}
              className={`group flex flex-col items-start gap-3 p-5 transition-all duration-200 sm:flex-row sm:items-center ${
                s.has_report
                  ? "cursor-pointer hover:bg-surface hover:shadow-[inset_2px_0_0_0_rgb(var(--color-accent))]"
                  : "cursor-default opacity-70"
              }`}
            >
              <StatusDot status={s.status} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <h3 className="truncate font-sans text-[15px] font-semibold text-text-primary transition-colors group-hover:text-accent">
                    {categoryLabel(s.ui_page || s.mode)}
                  </h3>
                  <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-accent">
                    {(s.ui_page || s.mode).replace(/_/g, " ")}
                  </span>
                </div>
                <span className="mt-1 block font-mono text-[11px] text-text-secondary">{s.id}</span>
              </div>
              <div className="flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
                {s.issue_count != null && (
                  <span className={`font-mono text-[11px] ${s.high_issue_count > 0 ? "text-accent" : "text-text-secondary"}`}>
                    {s.issue_count} issue{s.issue_count !== 1 ? "s" : ""}
                  </span>
                )}
                <StatusPill status={s.status} />
                {confirmDeleteId === s.id ? (
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-text-secondary">Delete?</span>
                    <button
                      onClick={() => handleDelete(s.id)}
                      disabled={deletingId === s.id}
                      className="text-[11px] font-medium text-accent hover:underline disabled:opacity-50"
                    >
                      {deletingId === s.id ? "…" : "Confirm"}
                    </button>
                    <button onClick={() => setConfirmDeleteId(null)} className="text-[11px] text-text-secondary hover:underline">
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDeleteId(s.id)}
                    aria-label="Delete session"
                    className="text-[12px] text-text-secondary transition-colors hover:text-accent"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
            </StaggerItem>
          ))}
        </StaggerGroup>
      )}
    </div>
  );
}
