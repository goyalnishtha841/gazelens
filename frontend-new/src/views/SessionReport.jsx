import { useState, useEffect, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { getSessionReport, downloadSessionPdf } from "../api/client.js";
import { Card, Label, SectionLabel, Stat, useCountUp } from "../components/Primitives.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import { GazeTrailDecorative } from "../components/GazeTrail.jsx";
import ReportImage from "../components/ReportImage.jsx";

const REPORT_POLL_MS = 2000;

const SEVERITY_STYLE = {
  High: "text-accent border-accent/40",
  Medium: "text-text-secondary border-border",
  Low: "text-text-secondary border-border",
};

/** Real session report: polls until ready, then shows heatmap, gaze path,
 * issues, and recommendations for THIS specific session -- ported from
 * frontend/src/views/Dashboard.jsx's ReportDetail, restyled. */
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

  if (pollError) {
    return (
      <div className="mx-auto max-w-[1000px] px-8 py-24 text-center">
        <p className="mx-auto max-w-md text-[13px] text-accent">{pollError}</p>
        <button onClick={onBack} className="mt-4 text-[13px] text-text-secondary underline hover:text-text-primary">
          Back to sessions
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
      <div className="mx-auto max-w-[1000px] px-8 py-24 text-center">
        {report?.status !== "failed" && (
          <div className="relative mx-auto mb-5 h-6 w-40">
            <GazeTrailDecorative seed={8} points={3} edgeToEdge className="text-accent" />
          </div>
        )}
        <p className="text-[13px] text-text-secondary">{message}</p>
        <button onClick={onBack} className="mt-4 text-[13px] text-text-secondary underline hover:text-text-primary">
          Back to sessions
        </button>
      </div>
    );
  }

  const { behavior_summary, issues, recommendations_kept } = report.pipeline_result;
  const quality = report.pipeline_result.quality;
  const labels = report.pipeline_result.element_labels || {};
  // Readable names from the backend's consolidation step; reports made before
  // it existed fall back to the raw id.
  const nameOf = (id) => (id === "__session__" ? "Whole page" : labels[id] || id);
  const insufficient = quality?.level === "insufficient";
  const highCount = issues.filter((i) => i.severity === "High").length;
  const avgConfidence =
    recommendations_kept.length > 0
      ? recommendations_kept.reduce((sum, r) => sum + r.confidence, 0) / recommendations_kept.length
      : null;
  const scoreOutOf100 = avgConfidence !== null ? Math.round(avgConfidence * 100) : null;

  return (
    <div className="mx-auto max-w-[1000px] px-8 py-10">
      {highCount > 0 && (
        <div className="mb-8 flex items-center gap-3 rounded-card border border-accent/40 bg-accent-soft px-4 py-3 text-[13px] text-text-primary">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          {highCount} high-severity issue{highCount !== 1 ? "s" : ""} found. Review before shipping.
        </div>
      )}

      {insufficient && (
        <div className="mb-8 rounded-card border border-accent/40 bg-accent-soft px-4 py-3 text-[13px] text-text-primary">
          Not enough reliable gaze data to evaluate this page, so no findings were drawn. Recalibrate and run it again.
        </div>
      )}

      <div className="flex items-start justify-between">
        <div>
          <button onClick={onBack} className="text-[12px] text-text-secondary transition-colors hover:text-text-primary">
            ← Sessions
          </button>
          <Label className="mt-3 block">{report.session_id}</Label>
          <h1 className="mt-1 font-sans text-[26px] font-semibold text-text-primary">Session Analysis</h1>
          <p className="mt-1 max-w-md text-[13px] text-text-secondary">
            The full pipeline's output for this one recording: real gaze data, attributed to real
            elements, reasoned over by the agent chain.
          </p>
        </div>
        <button
          onClick={handleDownloadPdf}
          disabled={pdfState === "downloading"}
          className={`flex items-center gap-2 rounded-card border px-4 py-2 text-[13px] transition-all duration-200 active:scale-95 disabled:opacity-60 ${
            pdfState === "success"
              ? "border-accent text-accent"
              : "border-border text-text-primary hover:border-accent hover:text-accent"
          }`}
        >
          {pdfState === "downloading" && (
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          )}
          {pdfState === "success" && (
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
              <path d="M4 12.5 9.5 18 20 6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          {pdfState === "idle" && (
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
              <path d="M12 3v13m0 0-5-5m5 5 5-5M4 20h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          {pdfState === "downloading" ? "Downloading…" : pdfState === "success" ? "Downloaded" : "Download PDF"}
        </button>
      </div>
      {pdfState === "error" && <p className="mt-2 text-[12px] text-accent">No PDF available for this session.</p>}

      {quality && <QualityStrip quality={quality} nameOf={nameOf} />}

      <StaggerGroup className="mt-10 grid grid-cols-2 gap-6 border-b border-border pb-10 lg:grid-cols-4">
        <StaggerItem><Stat value={behavior_summary.first_noticed ? nameOf(behavior_summary.first_noticed) : "--"} label="First noticed" /></StaggerItem>
        <StaggerItem><Stat value={behavior_summary.most_attended ? nameOf(behavior_summary.most_attended) : "--"} label="Most attended" /></StaggerItem>
        <StaggerItem><Stat value={behavior_summary.attention_scattered ? "Yes" : "No"} label="Attention scattered" /></StaggerItem>
        <StaggerItem><Stat value={issues.length} label="Issues found" accent={issues.length > 0} /></StaggerItem>
      </StaggerGroup>

      <Reveal className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <SectionLabel>Heatmap</SectionLabel>
          <Card className="aspect-[4/3] p-0">
            <ReportImage token={token} sessionId={report.session_id} kind="heatmap" alt="Gaze heatmap over the page" emptyLabel="No heatmap for this session." />
          </Card>
        </div>
        <div>
          <SectionLabel>Session overview</SectionLabel>
          <div className="space-y-3">
            {behavior_summary.first_noticed && (
              <p className="text-[13px] leading-relaxed text-text-primary">
                Attention landed first on <span className="font-medium">{nameOf(behavior_summary.first_noticed)}</span>.
              </p>
            )}
            {behavior_summary.ignored_important_elements.map((el) => (
              <p key={el} className="text-[13px] leading-relaxed text-text-primary">
                <span className="font-medium">{nameOf(el)}</span> received minimal attention despite its importance.
              </p>
            ))}
            {behavior_summary.attention_scattered && (
              <p className="text-[13px] leading-relaxed text-text-primary">Gaze repeatedly jumped between the same elements.</p>
            )}
          </div>
        </div>
      </Reveal>

      <Reveal className="mt-10">
        <SectionLabel>Gaze path</SectionLabel>
        <Card className="aspect-[16/6] p-0">
          <ReportImage token={token} sessionId={report.session_id} kind="scanpath" alt="Gaze path in visit order" emptyLabel="No gaze path for this session." />
        </Card>
      </Reveal>

      <Reveal className="mt-10">
        <SectionLabel>Usability issues</SectionLabel>
        {issues.length === 0 ? (
          <p className="text-[13px] italic text-text-secondary">
            {insufficient ? "Not evaluated: the gaze data wasn't reliable enough." : "No usability issues detected."}
          </p>
        ) : (
          <StaggerGroup>
            {issues.map((issue, i) => (
              <StaggerItem key={i}>
                <div className="group border-t border-border py-5 transition-colors first:border-t-0 first:pt-0 hover:bg-surface">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-[14px] text-text-primary">{issue.issue}</p>
                      <p className="mt-1 text-[12px] font-medium text-text-secondary">{issue.element_label || nameOf(issue.element_id)}</p>
                      {issue.also?.length > 0 && (
                        <p className="mt-1 text-[11px] text-text-secondary">Also: {issue.also.join("; ")}</p>
                      )}
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide ${SEVERITY_STYLE[issue.severity] || SEVERITY_STYLE.Low}`}>
                      {issue.severity}
                    </span>
                  </div>
                  <p className="mt-2 text-[12px] text-text-secondary">{issue.evidence}</p>
                  {issue.caveat && <p className="mt-1 text-[11px] italic text-text-secondary">{issue.caveat}</p>}
                </div>
              </StaggerItem>
            ))}
          </StaggerGroup>
        )}
      </Reveal>

      {recommendations_kept.length > 0 && (
        <Reveal className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
          <div>
            <SectionLabel>Recommendations</SectionLabel>
            <StaggerGroup>
              {recommendations_kept.map((rec, i) => (
                <StaggerItem key={i}>
                  <div className="group border-t border-border py-4 transition-colors first:border-t-0 first:pt-0 hover:bg-surface">
                    <Label>{rec.support === "Strong" ? "Immediate action" : "Needs review"}</Label>
                    <p className="mt-1 text-[12px] font-medium text-text-secondary">{rec.element_label || nameOf(rec.element_id)}</p>
                    <p className="mt-1 text-[13px] text-text-primary">{rec.recommendation}</p>
                    {rec.measurability != null && rec.measurability < 1 && (
                      <p className="mt-1 text-[11px] text-text-secondary">
                        Confidence lowered from {Math.round(rec.confidence_raw * 100)} to {Math.round(rec.confidence * 100)}: the element is small relative to the gaze error.
                      </p>
                    )}
                  </div>
                </StaggerItem>
              ))}
            </StaggerGroup>
          </div>
          <div>
            <SectionLabel>Critic confidence</SectionLabel>
            <CriticScore scoreOutOf100={scoreOutOf100} count={recommendations_kept.length} />
          </div>
        </Reveal>
      )}
    </div>
  );
}

const QUALITY_STYLE = {
  good: "border-border text-text-secondary",
  limited: "border-text-primary text-text-primary",
  insufficient: "border-accent bg-accent-soft text-accent",
};

/** How trustworthy this session's gaze was (backend/agents/quality_gate.py). */
function QualityStrip({ quality, nameOf }) {
  return (
    <div className="mt-6 rounded-card border border-border px-4 py-3 text-[12px]">
      <div className="flex flex-wrap items-center gap-3">
        <Label>Measurement quality</Label>
        <span className={`rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${QUALITY_STYLE[quality.level] || QUALITY_STYLE.good}`}>
          {quality.level}
        </span>
        {quality.gaze_error_px != null && (
          <span className="text-text-primary">
            Gaze error <span className="font-mono">{Math.round(quality.gaze_error_px)} px</span>
            <span className="text-text-secondary">
              {" "}({quality.gaze_error_pct_diagonal?.toFixed(1)}% of screen,{" "}
              {quality.error_source === "accuracy_check" ? "accuracy check" : "calibration estimate"})
            </span>
          </span>
        )}
      </div>
      {quality.reasons?.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-text-secondary">
          {quality.reasons.map((r) => <li key={r}>· {r}</li>)}
        </ul>
      )}
      {quality.level === "limited" && (
        <p className="mt-1 text-text-secondary">Severities are capped at Medium for this session.</p>
      )}
      {quality.low_confidence_elements?.length > 0 && (
        <p className="mt-1 text-text-secondary">
          Too small to measure at this accuracy: {quality.low_confidence_elements.map(nameOf).join(", ")}.
        </p>
      )}
    </div>
  );
}

/** Its own component (not inlined) so useCountUp -- a hook -- can be called
 * unconditionally: the parent only renders this block once
 * recommendations_kept.length > 0, and hooks can't live inside that `if`. */
function CriticScore({ scoreOutOf100, count }) {
  const counted = useCountUp(scoreOutOf100, 900);
  return (
    <div>
      <div className="font-sans text-[44px] font-semibold leading-none tabular-nums text-text-primary">
        {counted}
        <span className="text-[20px] text-text-secondary"> / 100</span>
      </div>
      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-border">
        <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${scoreOutOf100}%` }} />
      </div>
      <p className="mt-5 text-[12px] italic leading-relaxed text-text-secondary">
        Average of the Critic agent's confidence across the {count} recommendation
        {count !== 1 ? "s" : ""} that passed re-verification.
      </p>
    </div>
  );
}
