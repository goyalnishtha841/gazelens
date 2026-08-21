import { useState, useEffect } from "react";
import { getHealth } from "../api/client.js";

// The pipeline stages backend/api/pipeline.py actually wires together, in
// order -- see backend/*/CONTRACT.md for each module's own contract. This
// is a reference list, not a live per-module health check: only /health
// (fetched below) reflects real, current backend state. Labelling this
// section honestly as architecture rather than status avoids implying a
// precision this page doesn't have.
const PIPELINE_STAGES = [
  {
    name: "Calibration",
    module: "backend/calibration",
    description: "9/16-point data collection, MediaPipe + YOLOv8n pupil detection per frame.",
  },
  {
    name: "Gaze Estimation",
    module: "backend/gaze_estimation",
    description: "Per-session ridge regression, pupil position (+ head pose, when it moved enough) -> screen coordinate.",
  },
  {
    name: "Attribution",
    module: "backend/attribution",
    description: "Raw gaze -> dwell time, TTFF, fixation count, revisit count, scanpath per UI element.",
  },
  {
    name: "Agent Chain",
    module: "backend/agents",
    description: "Behavior -> Evaluation -> Recommendation -> Critic/Verifier, one rule-grounded finding at a time.",
  },
  {
    name: "Reports",
    module: "backend/reports",
    description: "Heatmap, gaze-path diagram, and the before/after table, then HTML + PDF.",
  },
];

function StatusRow({ label, value, tone }) {
  const toneClass = tone === "good" ? "text-[#2E7D32]" : tone === "bad" ? "text-[#B23A2E]" : "text-on-surface";
  return (
    <div className="flex items-center justify-between py-3 border-b border-outline-variant last:border-0">
      <span className="text-secondary text-body-md">{label}</span>
      <span className={`font-data-mono text-data-mono ${toneClass}`}>{value}</span>
    </div>
  );
}

export default function SystemStatus({ onNavigate, hasCalibration }) {
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

  const weightsFile = health?.weights_path?.split("/").pop();

  return (
    <div className="text-on-surface font-body-md">
      <nav className="flex justify-between items-center w-full px-margin-desktop py-4 bg-surface border-b border-outline-variant sticky top-0 z-40">
        <div className="flex items-center gap-8">
          <span className="font-display-lg text-display-lg text-primary">Fixation</span>
          <button
            onClick={() => onNavigate?.("dashboard")}
            className="text-on-surface-variant font-label-caps text-label-caps hover:bg-surface-container transition-colors px-2 py-1"
          >
            ← DASHBOARD
          </button>
        </div>
      </nav>

      <div className="max-w-container-max mx-auto p-gutter lg:p-margin-desktop">
        <div className="mb-8">
          <h1 className="font-display-lg text-display-lg text-on-surface mt-1">System Status</h1>
          <p className="text-secondary text-body-md mt-2 max-w-2xl">
            Live state of the detection pipeline this API process is actually running, not a marketing table.
          </p>
        </div>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-gutter mb-12">
          <div className="bg-white border border-outline-variant p-6">
            <h3 className="font-label-caps text-label-caps mb-2 border-b border-outline-variant pb-2">
              LIVE PIPELINE
            </h3>
            {error && (
              <p className="text-sm text-[#B23A2E] py-4">{error} — is the API running on :8000?</p>
            )}
            {!error && !health && (
              <div className="py-8 flex justify-center">
                <div className="w-5 h-5 border-2 border-outline-variant border-t-primary-container rounded-full animate-spin" />
              </div>
            )}
            {health && (
              <div>
                <StatusRow label="API" value={health.status === "ok" ? "ONLINE" : health.status} tone={health.status === "ok" ? "good" : "bad"} />
                <StatusRow
                  label="Live pupil detection"
                  value={health.cv_available ? "AVAILABLE" : "UNAVAILABLE"}
                  tone={health.cv_available ? "good" : "bad"}
                />
                <StatusRow
                  label="Detector weights"
                  value={health.weights_present ? weightsFile : "using smoketest stand-in"}
                  tone={health.weights_present ? "good" : undefined}
                />
                <StatusRow label="Database" value={health.database?.split("/").pop() || "—"} />
              </div>
            )}
            {health && !health.weights_present && (
              <p className="text-[11px] text-secondary mt-4 leading-relaxed">
                Running on the smoketest pupil detector (trained on drawn ellipses, not real eyes) — live capture
                works end to end, but accuracy numbers from it don't mean anything. Copy the real
                <code className="font-data-mono mx-1">pupil_yolo_final.pt</code> into <code className="font-data-mono">models/</code> to upgrade.
              </p>
            )}
          </div>

          <div className="bg-white border border-outline-variant p-6">
            <h3 className="font-label-caps text-label-caps mb-2 border-b border-outline-variant pb-2">
              THIS SITTING
            </h3>
            <StatusRow
              label="Calibration"
              value={hasCalibration ? "LINKED" : "NOT YET"}
              tone={hasCalibration ? "good" : undefined}
            />
            <p className="text-[11px] text-secondary mt-4 leading-relaxed">
              Calibration is per-sitting by design — head position, seating distance, lighting, and camera angle
              don't survive a change of participant or setup, so this resets each time you sign back in.
            </p>
            <button
              onClick={() => onNavigate?.("calibration")}
              className="mt-4 w-full border border-outline text-on-surface font-label-caps text-label-caps tracking-widest px-4 py-2.5 hover:bg-surface-container transition-colors"
            >
              {hasCalibration ? "RECALIBRATE" : "CALIBRATE NOW"}
            </button>
          </div>
        </section>

        <h2 className="font-headline-sm text-headline-sm mb-4">Pipeline architecture</h2>
        <p className="text-secondary text-body-md mb-6 max-w-2xl">
          Reference, not a live check — each stage is a real backend module with its own contract and test suite;
          see <code className="font-data-mono text-[13px]">CONTRACT.md</code> next to each one for the details.
        </p>
        <div className="bg-white border border-outline-variant divide-y divide-outline-variant">
          {PIPELINE_STAGES.map((stage, i) => (
            <div key={stage.name} className="flex items-start gap-5 p-5">
              <span className="font-data-mono text-data-mono text-outline shrink-0 w-6">{String(i + 1).padStart(2, "0")}</span>
              <div className="flex-1">
                <div className="flex items-baseline gap-3 flex-wrap">
                  <h4 className="font-headline-sm text-headline-sm">{stage.name}</h4>
                  <span className="font-data-mono text-[11px] text-secondary">{stage.module}</span>
                </div>
                <p className="text-secondary text-body-md mt-1">{stage.description}</p>
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <span className="material-symbols-outlined text-outline hidden md:block">arrow_downward</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
