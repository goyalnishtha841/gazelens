import { useState, useEffect } from "react";
import { getHealth } from "../api/client.js";
import { Card, Label, SectionLabel } from "../components/Primitives.jsx";

// The pipeline stages backend/api/pipeline.py actually wires together, in
// order. Reference, not a live per-module check -- only /health (fetched
// below) reflects real, current backend state. Ported from the old
// SystemStatus.jsx's same honesty distinction.
const PIPELINE_STAGES = [
  { name: "Calibration", module: "backend/calibration", description: "9/16-point data collection, MediaPipe + YOLOv8n pupil detection per frame." },
  { name: "Gaze Estimation", module: "backend/gaze_estimation", description: "Per-session ridge regression, pupil position (+ head pose, when it moved enough) to screen coordinate." },
  { name: "Attribution", module: "backend/attribution", description: "Raw gaze to dwell time, TTFF, fixation count, revisit count, scanpath per UI element." },
  { name: "Agent Chain", module: "backend/agents", description: "Behavior, Evaluation, Recommendation, Critic/Verifier, one rule-grounded finding at a time." },
  { name: "Reports", module: "backend/reports", description: "Heatmap, gaze-path diagram, and the before/after table, then HTML + PDF." },
];

function StatusRow({ label, value, tone }) {
  const toneClass = tone === "good" ? "text-accent" : tone === "bad" ? "text-accent" : "text-text-primary";
  return (
    <div className="flex items-center justify-between border-b border-border py-3 last:border-0">
      <span className="text-[13px] text-text-secondary">{label}</span>
      <span className={`font-mono text-[13px] ${toneClass}`}>{value}</span>
    </div>
  );
}

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

  return (
    <div className="mx-auto max-w-[1000px] px-8 py-12">
      <Label>Live pipeline state</Label>
      <h1 className="mt-1 font-sans text-[28px] font-semibold text-text-primary">System Status</h1>
      <p className="mt-2 max-w-lg text-[13px] text-text-secondary">
        What this API process is actually running right now, not a marketing table.
      </p>

      <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <SectionLabel>Live pipeline</SectionLabel>
          {error && <p className="py-4 text-[13px] text-accent">{error} -- is the API running on :8000?</p>}
          {!error && !health && (
            <div className="flex justify-center py-8">
              <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            </div>
          )}
          {health && (
            <div>
              <StatusRow label="API" value={health.status === "ok" ? "Online" : health.status} tone={health.status === "ok" ? "good" : "bad"} />
              <StatusRow
                label="Live pupil detection"
                value={health.cv_available ? "Available" : "Unavailable"}
                tone={health.cv_available ? "good" : "bad"}
              />
              <StatusRow
                label="Detector weights"
                value={health.weights_present ? weightsFile : "smoketest stand-in"}
                tone={health.weights_present ? "good" : undefined}
              />
              <StatusRow label="Database" value={health.database?.split(/[\\/]/).pop() || "--"} />
            </div>
          )}
          {health && !health.weights_present && (
            <p className="mt-4 text-[11px] leading-relaxed text-text-secondary">
              Running on the smoketest pupil detector (trained on drawn ellipses, not real eyes). Live capture
              works end to end, but accuracy numbers from it don't mean anything.
            </p>
          )}
        </Card>

        <Card>
          <SectionLabel>This sitting</SectionLabel>
          <StatusRow label="Calibration" value={hasCalibration ? "Linked" : "Not yet"} tone={hasCalibration ? "good" : undefined} />
          <p className="mt-4 text-[11px] leading-relaxed text-text-secondary">
            Calibration is per-sitting by design: head position, seating distance, lighting, and camera angle
            don't survive a change of participant or setup, so this resets each time you sign back in.
          </p>
          <button
            onClick={() => onNavigate?.("calibration")}
            className="mt-4 h-10 w-full rounded-card border border-border text-[13px] text-text-primary transition-colors hover:border-accent hover:text-accent"
          >
            {hasCalibration ? "Recalibrate" : "Calibrate now"}
          </button>
        </Card>
      </div>

      <div className="mt-12">
        <SectionLabel>Pipeline architecture</SectionLabel>
        <p className="mb-6 max-w-lg text-[13px] text-text-secondary">
          Reference, not a live check per module -- each stage is a real backend module with its own contract
          and test suite.
        </p>
        <div className="divide-y divide-border rounded-card border border-border">
          {PIPELINE_STAGES.map((stage, i) => (
            <div key={stage.name} className="flex items-start gap-5 p-5">
              <span className="w-6 shrink-0 font-mono text-[13px] text-text-secondary">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <div className="flex flex-wrap items-baseline gap-3">
                  <h4 className="font-sans text-[15px] font-semibold text-text-primary">{stage.name}</h4>
                  <span className="font-mono text-[11px] text-text-secondary">{stage.module}</span>
                </div>
                <p className="mt-1 text-[13px] text-text-secondary">{stage.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
