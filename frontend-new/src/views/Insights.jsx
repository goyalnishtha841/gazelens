import Sidebar from "../components/Sidebar.jsx";
import { Label, SectionLabel } from "../components/Primitives.jsx";
import { findings, recommendations } from "../data/mockData.js";

const severityStyle = {
  High: "text-accent border-accent/40",
  Medium: "text-text-secondary border-border",
  Low: "text-text-secondary border-border",
};

export default function Insights({ onNavigate }) {
  return (
    <div className="mx-auto flex max-w-[1400px] px-8 py-8">
      <Sidebar active="insights" onNavigate={onNavigate} />
      <main className="flex-1 max-w-3xl pl-0 md:pl-10">
        <div className="mb-10">
          <Label>Reasoned over collected evidence</Label>
          <h1 className="mt-1 font-sans text-[22px] font-semibold text-text-primary">AI Insights</h1>
          <p className="mt-1 max-w-lg text-[13px] text-text-secondary">
            Each finding below is grounded in a real metric from this session, then independently
            re-verified by a separate critic agent before it's shown to you.
          </p>
        </div>

        <div>
          {findings.map((f, i) => {
            const rec = recommendations.find((r) => r.element === f.element);
            return (
              <div key={i} className="border-t border-border py-8 first:border-t-0 first:pt-0">
                <SectionLabel index={i + 1}>Insight</SectionLabel>
                <p className="mt-3 text-[16px] leading-relaxed text-text-primary">{f.issue}</p>
                <p className="mt-2 font-mono text-[12px] text-text-secondary">{f.element}</p>

                <p className="mt-4 text-[13px] leading-relaxed text-text-secondary">{f.evidence}</p>

                <div className="mt-4 flex items-center gap-4">
                  <span className={`rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide ${severityStyle[f.severity]}`}>
                    Impact: {f.severity}
                  </span>
                  <Label>{f.heuristic}</Label>
                </div>

                {rec && (
                  <div className="mt-5 flex items-start gap-3">
                    <span className="mt-1 text-accent" aria-hidden="true">→</span>
                    <div>
                      <Label>Recommendation</Label>
                      <p className="mt-1 text-[14px] text-text-primary">{rec.text}</p>
                      <button
                        onClick={() => onNavigate("reports")}
                        className="mt-2 text-[12px] font-medium text-accent hover:opacity-80"
                      >
                        View evidence →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
