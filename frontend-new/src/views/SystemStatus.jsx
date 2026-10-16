import { useState, useEffect } from "react";
import { getHealth } from "../api/client.js";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import IrisMark from "../components/IrisMark.jsx";

// The pipeline stages backend/api/pipeline.py actually wires together, in
// order. Reference, not a live per-module check -- only /health (fetched
// below) reflects real, current backend state. Ported from the old
// SystemStatus.jsx's same honesty distinction.
const PIPELINE_STAGES = [
  { name: "Camera setup", module: "backend/calibration", description: "You follow a dot while we record what your eyes look like at each spot on the screen." },
  { name: "Eye tracking", module: "backend/gaze_estimation", description: "A model built just for you turns each camera frame into a point on the screen." },
  { name: "Matching to the page", module: "backend/attribution", description: "Each look is matched to a button, image or text, so we know what got noticed and when." },
  { name: "AI review", module: "backend/agents", description: "Four AI helpers describe what happened, judge it, suggest fixes and double-check each other." },
  { name: "Report", module: "backend/reports", description: "Heatmap, eye path and the list of fixes, ready to read or download as a PDF." },
];

function StatusRow({ label, value, tone }) {
  const toneClass = tone === "good" ? "text-accent" : tone === "bad" ? "text-coral" : "text-text-primary";
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/10 py-3.5 last:border-0">
      <span className="text-[15px] text-text-secondary">{label}</span>
      <span className={`flex items-center gap-2 text-[15px] font-medium ${toneClass}`}>
        {tone && <span className="h-2 w-2 rounded-full bg-current" />}
        {value}
      </span>
    </div>
  );
}

const panel = "rounded-[22px] border border-white/10 bg-surface/60 p-6 backdrop-blur sm:p-7";

export default function SystemStatus({ hasCalibration, onNavigate }) {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((d) => !cancelled && setHealth(d))
      .catch((err) => !cancelled && setError(err.message || "Couldn't reach the backend"));
    return () => {
      cancelled = true;
    };
  }, []);

  const weightsFile = health?.weights_path?.split(/[\\/]/).pop();
  const allGood = health?.status === "ok" && health?.cv_available;

  return (
    <div className="mx-auto max-w-[1000px] px-4 py-10 sm:px-8 sm:py-14">
      <Reveal>
        <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text-primary sm:text-[52px]">
          System <span className="font-serif font-normal italic text-accent">status</span>
        </h1>
        <p className="mt-3 max-w-lg text-[17px] leading-relaxed text-text-secondary">
          A quick check that everything GazeLens needs is up and running.
        </p>
      </Reveal>

      <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className={panel}>
          <div className="flex items-center justify-between">
            <h2 className="text-[19px] font-semibold text-text-primary">Server</h2>
            {health && (
              <span className={`rounded-full px-3 py-1 text-[13px] font-semibold ${allGood ? "bg-accent/15 text-accent" : "bg-amber/15 text-amber"}`}>
                {allGood ? "All good" : "Needs attention"}
              </span>
            )}
          </div>
          {error && <p className="mt-4 rounded-[14px] border border-coral/40 bg-coral/10 px-4 py-3 text-[15px] text-text-primary">We can't reach the server. Is the API running?</p>}
          {!error && !health && (
            <div className="flex justify-center py-10"><IrisMark size={36} wander /></div>
          )}
          {health && (
            <div className="mt-3">
              <StatusRow label="Server" value={health.status === "ok" ? "Online" : health.status} tone={health.status === "ok" ? "good" : "bad"} />
              <StatusRow label="Face and eye detection" value={health.cv_available ? "Ready" : "Unavailable"} tone={health.cv_available ? "good" : "bad"} />
              <StatusRow label="Detector model" value={health.weights_present ? weightsFile : "Test stand-in"} tone={health.weights_present ? "good" : undefined} />
              <StatusRow label="Database" value={health.database?.split(/[\\/]/).pop() || "–"} />
            </div>
          )}
        </div>

        <div className={panel}>
          <h2 className="text-[19px] font-semibold text-text-primary">Your camera setup</h2>
          <div className="mt-3">
            <StatusRow label="Calibration" value={hasCalibration ? "Done" : "Not yet"} tone={hasCalibration ? "good" : "bad"} />
          </div>
          <p className="mt-4 text-[14px] leading-relaxed text-text-secondary">
            The setup is tied to where you sit, your lighting and your camera, so it resets each time you sign in. Redo it whenever any of those change.
          </p>
          <button
            onClick={() => onNavigate?.("calibration")}
            className="mt-5 h-11 w-full rounded-full border border-white/10 text-[15px] font-medium text-text-primary transition-colors hover:border-accent/50 hover:text-accent"
          >
            {hasCalibration ? "Redo the setup" : "Set up now"}
          </button>
        </div>
      </div>

      <div className="mt-14">
        <h2 className="text-[24px] font-semibold tracking-tight text-text-primary">How a test turns into a report</h2>
        <p className="mt-2 max-w-lg text-[15px] text-text-secondary">Five steps, each handled by its own part of the system.</p>
        <StaggerGroup className="relative mt-8 space-y-3">
          <div aria-hidden="true" className="absolute bottom-6 left-[27px] top-6 w-px bg-gradient-to-b from-accent/60 via-cool/40 to-transparent" />
          {PIPELINE_STAGES.map((stage, i) => (
            <StaggerItem key={stage.name}>
              <div className="relative flex items-start gap-5 rounded-[20px] border border-white/10 bg-surface/60 p-5 backdrop-blur">
                <span className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[15px] font-semibold text-accent ring-4 ring-bg">
                  {i + 1}
                </span>
                <div>
                  <h3 className="text-[17px] font-semibold text-text-primary">{stage.name}</h3>
                  <p className="mt-1 text-[15px] leading-relaxed text-text-secondary">{stage.description}</p>
                  <span className="mt-2 inline-block font-mono text-[12px] text-text-secondary/70">{stage.module}</span>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerGroup>
      </div>
    </div>
  );
}
