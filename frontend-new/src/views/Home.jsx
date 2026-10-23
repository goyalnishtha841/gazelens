import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { listSessions } from "../api/client.js";
import { pageName } from "../lib/sessionData.js";
import { useCountUp } from "../components/Primitives.jsx";
import { Reveal } from "../components/Motion.jsx";
import IrisMark from "../components/IrisMark.jsx";
import { MiniHeatmap } from "../components/LandingVisuals.jsx";

const ACTIONS = [
  {
    id: "session", title: "Run a new test", body: "Pick a sample page or paste a link, then use it while GazeLens follows your eyes.",
    icon: <path d="M12 5v14M5 12h14" />,
  },
  {
    id: "dashboard", title: "Your sessions", body: "Every test you've run, with its report and what was found.",
    icon: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 9v11" /></>,
  },
  {
    id: "calibration", title: "Recalibrate", body: "Moved your laptop or changed the lighting? A one-minute setup keeps the eye tracking precise.",
    icon: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /></>,
  },
];

export default function Home({ onNavigate, onOpenSession, hasCalibration }) {
  const { user, token } = useAuth();
  const [sessions, setSessions] = useState(null);

  useEffect(() => {
    listSessions(token).then((data) => setSessions(data.sessions)).catch(() => setSessions([]));
  }, [token]);

  const total = sessions?.length ?? 0;
  const reports = sessions?.filter((s) => s.has_report).length ?? 0;
  const issues = sessions?.reduce((sum, s) => sum + (s.issue_count || 0), 0) ?? 0;
  const latest = sessions?.find((s) => s.has_report);
  const name = (user?.full_name || user?.email || "").split("@")[0].split(" ")[0];

  return (
    <div className="mx-auto max-w-[1180px] px-5 pb-24 pt-8 sm:px-8">
      {/* greeting */}
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative overflow-hidden rounded-[28px] border border-white/10 bg-surface/70 backdrop-blur-xl"
      >
        <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(60% 90% at 0% 0%, rgb(var(--color-accent) / 0.16), transparent 60%), radial-gradient(45% 80% at 100% 100%, rgb(var(--color-cool) / 0.12), transparent 60%)" }} />
        <div className="relative grid grid-cols-1 items-center gap-10 p-7 sm:p-10 lg:grid-cols-[1fr_380px]">
          <div>
            {/* hasCalibration is null while App is still looking for a saved setup */}
            <span className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13px] font-medium ${hasCalibration ? "border-accent/30 bg-accent/10 text-accent" : hasCalibration === false ? "border-amber/30 bg-amber/10 text-amber" : "border-white/10 bg-white/[0.04] text-text-secondary"}`}>
              <span className={`h-2 w-2 rounded-full ${hasCalibration ? "bg-accent" : hasCalibration === false ? "bg-amber" : "animate-pulse bg-text-secondary"}`} />
              {hasCalibration ? "Camera calibrated and ready" : hasCalibration === false ? "Camera setup needed for new tests" : "Checking your camera setup"}
            </span>
            <h1 className="mt-5 text-[40px] font-bold leading-[1.05] tracking-[-0.025em] text-text-primary sm:text-[54px]">
              {name ? <>Hi {name}, ready to <span className="font-serif font-normal italic text-accent">see</span> more?</> : <>Ready to <span className="font-serif font-normal italic text-accent">see</span> more?</>}
            </h1>
            <p className="mt-4 max-w-[520px] text-[17px] leading-relaxed text-text-secondary">
              {hasCalibration === false
                ? "Your sessions and reports are all here. To run a new test, GazeLens first needs a one-minute camera setup on this screen, and it starts when you do."
                : "Start a test on any page. When you finish, your report shows where people looked and what to fix."}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                onClick={() => onNavigate("session")}
                className="group inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-[16px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_36px_-4px_rgb(var(--color-accent)/0.7)]"
              >
                {hasCalibration === false ? "Set up and start a test" : "Start a test"}
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </button>
              {latest && (
                <button onClick={() => onOpenSession?.(latest.id)} className="rounded-full border border-white/10 bg-bg/40 px-7 py-3.5 text-[16px] font-medium text-text-primary transition-colors hover:border-accent/50">
                  Open latest report
                </button>
              )}
            </div>
          </div>
          <div className="hidden rounded-[20px] border border-white/10 bg-bg/60 p-4 lg:block">
            <div className="mb-3 flex items-center justify-between text-[13px]">
              <span className="flex items-center gap-2 font-semibold text-text-primary"><span className="text-accent"><IrisMark size={18} wander /></span> What a report shows</span>
            </div>
            <MiniHeatmap />
          </div>
        </div>
      </motion.section>

      {/* numbers */}
      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Tile label="Tests run" value={total} loading={!sessions} />
        <Tile label="Reports ready" value={reports} loading={!sessions} />
        <Tile label="Problems found" value={issues} loading={!sessions} tone={issues ? "text-amber" : "text-text-primary"} />
      </div>

      {/* latest */}
      {latest && (
        <Reveal once className="mt-12">
          <h2 className="mb-4 text-[22px] font-semibold text-text-primary">Pick up where you left off</h2>
          <button
            onClick={() => onOpenSession?.(latest.id)}
            className="group flex w-full items-center justify-between gap-4 rounded-[22px] border border-white/10 bg-surface/60 p-6 text-left backdrop-blur transition-all hover:-translate-y-0.5 hover:border-accent/40"
          >
            <div className="flex min-w-0 items-center gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[14px] bg-accent/10 text-accent"><IrisMark size={26} /></span>
              <div className="min-w-0">
                <div className="truncate text-[18px] font-semibold text-text-primary">{pageName(latest) || "Session"}</div>
                <div className="mt-0.5 text-[14px] text-text-secondary">
                  {new Date(latest.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                  {latest.issue_count != null && <> · {latest.issue_count} {latest.issue_count === 1 ? "problem" : "problems"} found</>}
                </div>
              </div>
            </div>
            <span className="shrink-0 rounded-full border border-white/10 px-4 py-2 text-[14px] text-text-primary transition-colors group-hover:border-accent/50 group-hover:text-accent">View report →</span>
          </button>
        </Reveal>
      )}

      {/* actions */}
      <Reveal once className="mt-12">
        <h2 className="mb-4 text-[22px] font-semibold text-text-primary">What would you like to do?</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {ACTIONS.map((a) => (
            <button
              key={a.id}
              onClick={() => onNavigate(a.id)}
              className="group rounded-[22px] border border-white/10 bg-surface/60 p-6 text-left backdrop-blur transition-all hover:-translate-y-1 hover:border-accent/40 hover:shadow-[0_0_50px_-26px_rgb(var(--color-accent)/0.8)]"
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-[12px] bg-accent/10 text-accent">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{a.icon}</svg>
              </span>
              <h3 className="mt-5 text-[19px] font-semibold text-text-primary transition-colors group-hover:text-accent">{a.title}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-text-secondary">{a.body}</p>
            </button>
          ))}
        </div>
      </Reveal>
    </div>
  );
}

function Tile({ label, value, loading, tone = "text-text-primary" }) {
  const counted = useCountUp(loading ? 0 : value, 900);
  return (
    <div className="rounded-[20px] border border-white/10 bg-surface/60 p-6 backdrop-blur">
      <div className={`text-[34px] font-bold tabular-nums tracking-tight ${tone}`}>{loading ? "–" : counted}</div>
      <div className="mt-1 text-[14px] text-text-secondary">{label}</div>
    </div>
  );
}
