import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { listSessions } from "../api/client.js";
import { Label, SectionLabel } from "../components/Primitives.jsx";
import { GazeTrailDecorative } from "../components/GazeTrail.jsx";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";

const QUICK_LINKS = [
  { id: "session", title: "New session", body: "Calibrate against a test page or any URL, and record real gaze." },
  { id: "dashboard", title: "Sessions", body: "Every session you've recorded, with its status and findings." },
  { id: "status", title: "System status", body: "Live state of the detection pipeline this API is running." },
];

export default function Home({ onNavigate, hasCalibration }) {
  const { user, token } = useAuth();
  const [sessions, setSessions] = useState(null);

  useEffect(() => {
    listSessions(token).then((data) => setSessions(data.sessions)).catch(() => setSessions([]));
  }, [token]);

  const stats = sessions && {
    total: sessions.length,
    completed: sessions.filter((s) => s.status === "complete").length,
    highSeverity: sessions.reduce((sum, s) => sum + (s.high_issue_count || 0), 0),
  };
  const mostRecent = sessions?.find((s) => s.has_report);
  const greetingName = (user?.full_name || user?.email || "").split("@")[0];

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-16">
      <div className="grid grid-cols-1 items-center gap-16 lg:grid-cols-[1fr_360px]">
        <StaggerGroup>
          <StaggerItem><Label>Welcome back</Label></StaggerItem>
          <StaggerItem>
            <h1 className="mt-3 font-sans text-[42px] font-semibold leading-[1.1] tracking-tight text-text-primary">
              {greetingName ? `Hi, ${greetingName}.` : "Hi there."}
            </h1>
          </StaggerItem>
          <StaggerItem>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-text-secondary">
              {hasCalibration
                ? "Your gaze model is calibrated for this sitting. Start a session, or check in on ones you've already run."
                : "Calibrate to start tracking real gaze data."}
            </p>
          </StaggerItem>
          <StaggerItem>
            <button
              onClick={() => onNavigate(hasCalibration ? "session" : "calibration")}
              className="mt-8 inline-flex h-11 items-center gap-2 rounded-card bg-text-primary px-6 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
            >
              {hasCalibration ? "Start a session" : "Calibrate now"}
            </button>
          </StaggerItem>

          {stats && stats.total > 0 && (
            <StaggerItem>
              <div className="mt-14 flex gap-10 border-t border-border pt-8">
                <div>
                  <div className="font-sans text-[26px] font-semibold text-text-primary">{stats.total}</div>
                  <Label className="mt-1 block">Sessions run</Label>
                </div>
                <div>
                  <div className="font-sans text-[26px] font-semibold text-text-primary">{stats.completed}</div>
                  <Label className="mt-1 block">Complete</Label>
                </div>
                <div>
                  <div className={`font-sans text-[26px] font-semibold ${stats.highSeverity > 0 ? "text-accent" : "text-text-primary"}`}>
                    {stats.highSeverity}
                  </div>
                  <Label className="mt-1 block">High severity</Label>
                </div>
              </div>
            </StaggerItem>
          )}
        </StaggerGroup>

        <Reveal delay={0.15}>
          <div className="relative aspect-square w-full">
            <GazeTrailDecorative seed={9} points={9} large className="text-accent" />
          </div>
        </Reveal>
      </div>

      {mostRecent && (
        <Reveal className="mt-16 border-t border-border pt-10">
          <SectionLabel>Most recent session</SectionLabel>
          <button
            onClick={() => onNavigate("dashboard")}
            className="group flex w-full items-center justify-between text-left"
          >
            <div>
              <p className="text-[15px] text-text-primary">
                {(mostRecent.ui_page || mostRecent.mode).replace(/_/g, " ")}
              </p>
              <p className="mt-1 font-mono text-[11px] text-text-secondary">{mostRecent.id}</p>
            </div>
            <span className="text-[13px] text-text-secondary transition-colors group-hover:text-accent">
              View in Sessions →
            </span>
          </button>
        </Reveal>
      )}

      <Reveal className="mt-16 border-t border-border pt-10">
        <SectionLabel>Quick links</SectionLabel>
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
          {QUICK_LINKS.map((l) => (
            <button key={l.id} onClick={() => onNavigate(l.id)} className="group text-left">
              <h3 className="font-sans text-[15px] font-semibold text-text-primary transition-colors group-hover:text-accent">
                {l.title}
              </h3>
              <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">{l.body}</p>
            </button>
          ))}
        </div>
      </Reveal>
    </div>
  );
}
