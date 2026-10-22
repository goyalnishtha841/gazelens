import { MiniHeatmap, MiniPath } from "./LandingVisuals.jsx";

export default function StudioPreview() {
  return (
    <div className="studio-preview" aria-label="Illustrative preview of a GazeLens report">
      <div className="studio-preview-orbit" aria-hidden="true" />
      <div className="studio-preview-label"><span /> A little perspective changes everything.</div>
      <div className="studio-browser">
        <div className="studio-browser-bar"><div><i /><i /><i /></div><span>GazeLens / attention study</span><span>↗</span></div>
        <div className="studio-browser-body">
          <div className="studio-study-heading"><div><span className="studio-eyebrow">THE ATTENTION REPORT</span><h2>Behind every glance,<br />a better decision.</h2></div><span className="studio-example-tag">Example</span></div>
          <div className="studio-study-tabs"><span>Attention map</span><span>Eye path</span><span>Insights</span></div>
          <MiniHeatmap label="Illustrative attention map" />
          <div className="studio-preview-bottom"><div><span className="studio-eyebrow">FOLLOW THE JOURNEY</span><MiniPath /></div><div className="studio-insight"><span>↗</span><strong>Less guesswork.<br />More clarity.</strong><p>Understand what gets noticed, and what gets missed.</p></div></div>
        </div>
      </div>
      <div className="studio-preview-note"><span className="studio-note-icon">◎</span><div><strong>Designed around real attention.</strong><span>From a glance to a useful insight.</span></div></div>
      <div className="studio-preview-caption"><span>01 / OBSERVE. UNDERSTAND. IMPROVE.</span><span>WEBCAM → CLARITY</span></div>
    </div>
  );
}
