import { useState, useEffect, useMemo, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { listSessions, getSessionReport } from "../api/client.js";

const REPORT_POLL_MS = 2000;

const STATUS_LABEL = {
  created: "Created",
  calibrated: "Calibrated",
  recording: "Recording",
  processing: "Processing",
  complete: "Complete",
  failed: "Failed",
};

function categoryLabel(uiPage) {
  const map = {
    ecommerce_product_page: "E-Commerce",
    form_page: "Form",
    dashboard_page: "Dashboard",
    login_page: "Login",
    article_page: "Article",
  };
  return map[uiPage] || uiPage.replace(/_/g, " ");
}

// Session list rows come from GET /api/sessions, which is deliberately
// lightweight (no per-session report fetch) -- so this shows pipeline status
// rather than an issue count. Issue counts only exist once a report is open.
function StatusPill({ status }) {
  const styleByStatus = {
    complete: "bg-secondary-container text-on-secondary-container",
    failed: "bg-error-container text-on-error-container",
    processing: "bg-surface-container-highest text-secondary",
  };
  const iconByStatus = {
    complete: "check_circle",
    failed: "warning",
    processing: "hourglass_top",
  };
  return (
    <div
      className={`px-3 py-1 rounded-full text-[11px] font-bold flex items-center gap-1.5 ${
        styleByStatus[status] || "bg-surface-container-highest text-secondary"
      }`}
    >
      <span className="material-symbols-outlined text-[14px]">{iconByStatus[status] || "radio_button_unchecked"}</span>
      {STATUS_LABEL[status] || status}
    </div>
  );
}

const SEVERITY_BADGE = {
  High: "bg-error-container text-on-error-container border-error",
  Medium: "bg-tertiary-fixed text-on-tertiary-fixed-variant border-tertiary-container",
  Low: "bg-surface-container-high text-on-secondary-container border-outline",
};

function ReportDetail({ sessionId, onBack }) {
  const { token } = useAuth();
  const [report, setReport] = useState(null);
  const [pollError, setPollError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getSessionReport(token, sessionId);
        if (cancelled) return;
        setReport(data);
        if (!data.ready) {
          pollRef.current = setTimeout(poll, REPORT_POLL_MS);
        }
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

  if (pollError) {
    return (
      <div className="py-24 text-center">
        <div className="text-sm text-[#B23A2E] max-w-md mx-auto">{pollError}</div>
        <button onClick={onBack} className="mt-4 text-secondary text-sm underline">
          Back to dashboard
        </button>
      </div>
    );
  }

  if (!report || !report.ready) {
    const message =
      report?.status === "failed"
        ? `Analysis failed: ${report.message || "unknown error"}`
        : report?.message || "Loading report…";
    return (
      <div className="py-24 text-center">
        {report?.status !== "failed" && (
          <div className="w-5 h-5 border-2 border-outline-variant border-t-primary-container rounded-full animate-spin mx-auto mb-3" />
        )}
        <div className="text-secondary text-sm">{message}</div>
      </div>
    );
  }

  const { behavior_summary, issues, recommendations_kept } = report.pipeline_result;
  const highCount = issues.filter((i) => i.severity === "High").length;
  const avgConfidence =
    recommendations_kept.length > 0
      ? recommendations_kept.reduce((sum, r) => sum + r.confidence, 0) / recommendations_kept.length
      : null;
  const scoreOutOf100 = avgConfidence !== null ? Math.round(avgConfidence * 100) : null;

  return (
    <div className="text-on-surface font-body-md">
      {highCount > 0 && (
        <div className="w-full bg-[#B23A2E] text-white py-2 px-margin-desktop flex items-center justify-center space-x-2 sticky top-0 z-50">
          <span className="material-symbols-outlined text-[18px]">report</span>
          <p className="font-label-caps text-label-caps">
            {highCount} high-severity issue{highCount !== 1 ? "s" : ""} found — review before shipping.
          </p>
        </div>
      )}

      <nav className="flex justify-between items-center w-full px-margin-desktop py-4 bg-surface border-b border-outline-variant sticky top-[32px] z-40 bg-opacity-95 backdrop-blur-sm">
        <div className="flex items-center gap-8">
          <span className="font-display-lg text-display-lg text-primary">GazeLens</span>
          <button onClick={onBack} className="text-on-surface-variant font-label-caps text-label-caps hover:bg-surface-container transition-colors px-2 py-1">
            ← DASHBOARD
          </button>
        </div>
      </nav>

      <div className="max-w-container-max mx-auto p-gutter lg:p-margin-desktop">
        <div className="mb-8">
          <span className="font-data-mono text-[11px] text-secondary">{report.session_id}</span>
          <h1 className="font-display-lg text-display-lg text-on-surface mt-1">Session Analysis</h1>
        </div>

        {/* Stat cards */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-gutter mb-12">
          <div className="bg-white border border-outline-variant p-6 flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant">FIRST NOTICED</span>
            <span className="font-data-mono text-display-lg text-primary">{behavior_summary.first_noticed ?? "—"}</span>
            <div className="w-full bg-surface-container h-[2px] mt-2">
              <div className="bg-primary h-full w-1/4" />
            </div>
          </div>
          <div className="bg-white border border-outline-variant p-6 flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant">MOST ATTENDED</span>
            <span className="font-data-mono text-display-lg text-primary">{behavior_summary.most_attended ?? "—"}</span>
            <div className="w-full bg-surface-container h-[2px] mt-2">
              <div className="bg-primary h-full w-[70%]" />
            </div>
          </div>
          <div className="bg-white border border-outline-variant p-6 flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant">ATTENTION SCATTERED</span>
            <span className="font-data-mono text-display-lg text-primary">{behavior_summary.attention_scattered ? "Yes" : "No"}</span>
            <div className="w-full bg-surface-container h-[2px] mt-2">
              <div className="bg-primary h-full" style={{ width: behavior_summary.attention_scattered ? "100%" : "8%" }} />
            </div>
          </div>
          <div className="bg-white border border-outline-variant p-6 flex flex-col gap-2">
            <span className="font-label-caps text-label-caps text-on-surface-variant" style={issues.length > 0 ? { color: "#B23A2E" } : {}}>
              ISSUES FOUND
            </span>
            <span className="font-data-mono text-display-lg" style={{ color: issues.length > 0 ? "#B23A2E" : "#00565e" }}>
              {issues.length}
            </span>
            <div className="w-full bg-surface-container h-[2px] mt-2">
              <div className="h-full" style={{ width: "100%", backgroundColor: issues.length > 0 ? "#B23A2E" : "#00565e" }} />
            </div>
          </div>
        </section>

        {/* Heatmap + overview */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-gutter mb-12">
          <div className="lg:col-span-8 bg-white border border-outline-variant relative overflow-hidden flex items-center justify-center min-h-[300px]">
            <div className="absolute top-4 left-4 z-10 bg-surface-container-highest px-3 py-1 border border-outline">
              <span className="font-label-caps text-label-caps">HEATMAP OVERLAY</span>
            </div>
            <p className="text-sm text-secondary">Renders once session metrics are computed.</p>
          </div>
          <div className="lg:col-span-4 flex flex-col gap-gutter">
            <div className="bg-white border border-outline-variant p-6 flex-1 flex flex-col">
              <h3 className="font-label-caps text-label-caps mb-4 border-b border-outline-variant pb-2">
                SESSION OVERVIEW
              </h3>
              <div className="space-y-6 overflow-y-auto pr-2">
                {behavior_summary.first_noticed && (
                  <div className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-3 h-3 bg-primary rounded-full" />
                      <div className="w-[1px] h-full bg-outline-variant" />
                    </div>
                    <div>
                      <p className="font-label-caps text-label-caps text-on-surface-variant">INITIAL FIXATION</p>
                      <p className="text-body-md mt-1">
                        Attention landed first on <span className="font-data-mono">{behavior_summary.first_noticed}</span>.
                      </p>
                    </div>
                  </div>
                )}
                {behavior_summary.ignored_important_elements.map((el) => (
                  <div key={el} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#B23A2E" }} />
                      <div className="w-[1px] h-full bg-outline-variant" />
                    </div>
                    <div>
                      <p className="font-label-caps text-label-caps" style={{ color: "#B23A2E" }}>
                        ATTENTION GAP
                      </p>
                      <p className="text-body-md mt-1">
                        <span className="font-data-mono">{el}</span> received minimal attention despite its importance.
                      </p>
                    </div>
                  </div>
                ))}
                {behavior_summary.attention_scattered && (
                  <div className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-3 h-3 bg-secondary rounded-full" />
                    </div>
                    <div>
                      <p className="font-label-caps text-label-caps text-on-surface-variant">LAYOUT CONFUSION</p>
                      <p className="text-body-md mt-1">Gaze repeatedly jumped between the same elements.</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Issues table */}
        <section className="mb-12">
          <div className="bg-white border border-outline-variant">
            <div className="px-6 py-4 border-b border-outline-variant bg-surface-container-low">
              <h2 className="font-label-caps text-label-caps">USABILITY ISSUES</h2>
            </div>
            {issues.length === 0 ? (
              <p className="text-sm text-secondary italic px-6 py-6">No usability issues detected.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="font-label-caps text-label-caps text-on-surface-variant border-b border-outline-variant bg-surface-container-lowest">
                      <th className="px-6 py-4 font-semibold">ISSUE</th>
                      <th className="px-6 py-4 font-semibold">SEVERITY</th>
                      <th className="px-6 py-4 font-semibold">OBSERVATIONS</th>
                    </tr>
                  </thead>
                  <tbody className="text-body-md divide-y divide-outline-variant">
                    {issues.map((issue, i) => (
                      <tr key={i} className="hover:bg-surface-container-low transition-colors">
                        <td className="px-6 py-4 font-medium">
                          {issue.issue}
                          <div className="text-xs font-data-mono text-secondary mt-0.5">{issue.element_id}</div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`text-[10px] px-2 py-0.5 rounded-lg border font-bold uppercase tracking-wider ${SEVERITY_BADGE[issue.severity] || ""}`}>
                            {issue.severity}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-on-surface-variant font-data-mono text-xs">{issue.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* Recommendations + confidence */}
        {recommendations_kept.length > 0 && (
          <section className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
            <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-gutter">
              {recommendations_kept.map((rec, i) => {
                const isStrong = rec.support === "Strong";
                return (
                  <div
                    key={i}
                    className="bg-white border border-outline-variant p-6"
                    style={{ borderLeftWidth: "4px", borderLeftColor: isStrong ? "#2E7D32" : "#F9A825" }}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <span className="font-label-caps text-label-caps text-primary">
                        {isStrong ? "IMMEDIATE ACTION" : "NEEDS REVIEW"}
                      </span>
                      <span className="material-symbols-outlined text-[20px]" style={{ color: isStrong ? "#2E7D32" : "#F9A825" }}>
                        {isStrong ? "task_alt" : "hourglass_top"}
                      </span>
                    </div>
                    <div className="text-xs font-data-mono text-secondary mb-2">{rec.element_id}</div>
                    <p className="text-body-md text-on-surface-variant">{rec.recommendation}</p>
                  </div>
                );
              })}
            </div>
            <div className="bg-white border border-outline-variant p-6 flex flex-col justify-between">
              <div>
                <h3 className="font-label-caps text-label-caps text-on-surface-variant mb-8">
                  CRITIC CONFIDENCE SCORE
                </h3>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="font-data-mono text-[48px] leading-none text-primary">{scoreOutOf100}</span>
                  <span className="font-label-caps text-label-caps">/ 100</span>
                </div>
                <div className="w-full bg-surface-container h-3 rounded-full overflow-hidden">
                  <div
                    className="bg-primary h-full"
                    style={{ width: `${scoreOutOf100}%`, boxShadow: "0 0 10px rgba(0, 86, 94, 0.4)" }}
                  />
                </div>
              </div>
              <p className="text-[12px] text-on-surface-variant leading-relaxed mt-6 italic">
                Average of the Critic agent's confidence across the {recommendations_kept.length} recommendation
                {recommendations_kept.length !== 1 ? "s" : ""} that passed re-verification for this session.
              </p>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

export default function Dashboard({ initialSessionId, onNavigate }) {
  const { user, token, logout } = useAuth();
  const [sessions, setSessions] = useState(null);
  const [openSessionId, setOpenSessionId] = useState(initialSessionId ?? null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    listSessions(token).then((data) => setSessions(data.sessions));
  }, [token]);

  const filteredSessions = useMemo(() => {
    if (!sessions) return null;
    if (!filter.trim()) return sessions;
    const q = filter.trim().toLowerCase();
    return sessions.filter(
      (s) => (s.ui_page || "").toLowerCase().includes(q) || s.id.toLowerCase().includes(q)
    );
  }, [sessions, filter]);

  if (openSessionId) {
    return <ReportDetail sessionId={openSessionId} onBack={() => setOpenSessionId(null)} />;
  }

  const initials = (user?.email || "?").slice(0, 1).toUpperCase();

  return (
    <div className="font-body-md text-on-background min-h-screen flex overflow-hidden -mx-6 -my-8">
      {/* Left sidebar */}
      <aside className="hidden md:flex flex-col h-screen w-64 bg-surface-container-low border-r border-outline-variant shrink-0">
        <div className="px-6 py-8">
          <h1 className="font-display-lg text-display-lg text-primary">GazeLens</h1>
          <div className="mt-6 flex items-center gap-3">
            <div className="w-10 h-10 bg-primary-container rounded flex items-center justify-center text-on-primary-container">
              <span className="material-symbols-outlined">psychology</span>
            </div>
            <div>
              <p className="font-label-caps text-label-caps tracking-widest text-primary uppercase">Research Hub</p>
              <p className="text-[10px] text-secondary">{sessions?.length ?? 0} sessions on record</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 px-2 space-y-1">
          <button
            onClick={() => onNavigate?.("dashboard")}
            className="w-full group flex items-center px-4 py-3 bg-primary-container text-on-primary-container font-bold border-r-2 border-primary"
          >
            <span className="material-symbols-outlined mr-3">dashboard</span>
            <span className="font-label-caps text-label-caps tracking-widest">DASHBOARD</span>
          </button>
          <button
            onClick={() => onNavigate?.("calibration")}
            className="w-full group flex items-center px-4 py-3 hover:bg-surface-container-high text-secondary transition-colors"
          >
            <span className="material-symbols-outlined mr-3">track_changes</span>
            <span className="font-label-caps text-label-caps tracking-widest">CALIBRATION</span>
          </button>
          <button
            onClick={() => onNavigate?.("calibration")}
            className="w-full group flex items-center px-4 py-3 hover:bg-surface-container-high text-secondary transition-colors"
          >
            <span className="material-symbols-outlined mr-3">sensors</span>
            <span className="font-label-caps text-label-caps tracking-widest">LIVE SESSION</span>
          </button>
        </nav>
        <div className="p-4 border-t border-outline-variant">
          <button
            onClick={() => onNavigate?.("calibration")}
            className="w-full bg-primary text-white py-3 rounded font-label-caps text-label-caps tracking-widest hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            NEW SESSION
          </button>
          <div className="mt-4 flex items-center gap-3 px-2">
            <div className="w-8 h-8 rounded-full bg-secondary-container border border-outline flex items-center justify-center">
              <span className="text-xs font-bold text-primary">{initials}</span>
            </div>
            <div className="overflow-hidden flex-1">
              <p className="text-[12px] font-bold truncate">{user?.full_name || user?.email}</p>
              <p className="text-[10px] text-secondary truncate">Researcher</p>
            </div>
            <button onClick={logout} className="text-secondary hover:text-[#B23A2E] transition-colors">
              <span className="material-symbols-outlined text-[18px]">logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="flex justify-between items-center w-full px-margin-desktop py-4 bg-surface border-b border-outline-variant shrink-0">
          <h2 className="font-headline-sm text-headline-sm text-primary">Session Overview</h2>
          <div className="relative hidden lg:block">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-[20px]">
              search
            </span>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-10 pr-4 py-1.5 w-64 bg-surface-container-lowest border border-outline-variant rounded-sm text-sm focus:ring-1 focus:ring-primary focus:border-primary outline-none transition-all"
              placeholder="Filter research data…"
              type="text"
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-gutter lg:p-margin-desktop">
          <div className="max-w-container-max mx-auto">
            <div className="mb-12">
              <h1 className="font-display-lg text-display-lg text-on-surface mb-2">Research Dashboard</h1>
              <p className="text-secondary font-body-md max-w-2xl">
                Manage and analyze gaze tracking data from your latest user testing sessions. Select a session to
                view its report.
              </p>
            </div>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
              <div className="flex items-center gap-2 bg-white border border-outline-variant p-1 rounded-sm w-full md:w-auto">
                <button className="px-4 py-1.5 bg-primary-container text-on-primary-container text-[12px] font-bold rounded-sm">
                  All Sessions
                </button>
              </div>
            </div>

            {!sessions && (
              <div className="py-16 text-center">
                <div className="w-5 h-5 border-2 border-outline-variant border-t-primary-container rounded-full animate-spin mx-auto mb-3" />
                <div className="text-secondary text-sm">Loading sessions…</div>
              </div>
            )}

            {filteredSessions?.length === 0 && (
              <div className="bg-white border border-outline-variant rounded-sm text-center py-12 text-secondary text-sm">
                {sessions.length === 0 ? "No sessions yet — run one from Live Session." : "No sessions match that filter."}
              </div>
            )}

            {filteredSessions?.length > 0 && (
              <div className="bg-white border border-outline-variant rounded-sm overflow-hidden divide-y divide-outline-variant">
                {filteredSessions.map((s) => (
                  <div
                    key={s.id}
                    onClick={() => s.has_report && setOpenSessionId(s.id)}
                    className={`group flex flex-col sm:flex-row items-start sm:items-center p-6 transition-colors ${
                      s.has_report ? "hover:bg-surface-container-low cursor-pointer" : "opacity-70 cursor-default"
                    }`}
                  >
                    <div className="flex-1 min-w-0 pr-4">
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="font-headline-sm text-headline-sm text-on-surface truncate">
                          {categoryLabel(s.ui_page || s.mode)}
                        </h3>
                        <span className="bg-secondary-container text-on-secondary-container px-2 py-0.5 rounded-sm text-[10px] font-bold uppercase tracking-wider">
                          {(s.ui_page || s.mode).replace(/_/g, " ")}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-outline font-data-mono text-data-mono">
                        <span className="flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px]">tag</span>
                          {s.id}
                        </span>
                      </div>
                    </div>
                    <div className="mt-4 sm:mt-0 flex items-center gap-6">
                      <StatusPill status={s.status} />
                      <button className="text-outline group-hover:text-primary transition-colors">
                        <span className="material-symbols-outlined">chevron_right</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
