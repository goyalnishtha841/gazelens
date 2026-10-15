import Sidebar from "../components/Sidebar.jsx";
import { Label, SectionLabel } from "../components/Primitives.jsx";
import UiMockup from "../components/UiMockup.jsx";
import { project, elements, scanpath, findings, recommendations } from "../data/mockData.js";

export default function Reports({ onNavigate }) {
  return (
    <div className="mx-auto flex max-w-[1400px] px-8 py-8">
      <Sidebar active="reports" onNavigate={onNavigate} />
      <main className="flex-1 max-w-3xl pl-0 md:pl-10">
        <Label>GazeLens Report</Label>
        <h1 className="mt-2 font-sans text-[32px] font-semibold tracking-tight text-text-primary">
          {project.name}
        </h1>
        <p className="mt-1 text-[13px] text-text-secondary">Generated {project.generated}</p>

        <div className="mt-12">
          <SectionLabel>Executive summary</SectionLabel>
          <p className="max-w-2xl text-[15px] leading-relaxed text-text-primary">
            Overall attention is concentrated almost entirely around the hero image, with the
            headline, article body, and both calls-to-action receiving negligible gaze time.
            The scanpath repeatedly returned to the same two regions rather than progressing
            through the page in reading order, suggesting the current layout is not guiding
            attention the way its visual hierarchy intends.
          </p>
        </div>

        <div className="mt-12">
          <SectionLabel>Attention distribution</SectionLabel>
          <UiMockup elements={elements} scanpath={scanpath} heat />
        </div>

        <div className="mt-12">
          <SectionLabel>Key findings</SectionLabel>
          <div className="space-y-0">
            {findings.map((f, i) => (
              <div key={i} className="flex gap-4 border-t border-border py-4 first:border-t-0">
                <span className="font-mono text-[13px] text-text-secondary">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <p className="text-[14px] text-text-primary">{f.issue}</p>
                  <p className="mt-1 font-mono text-[11px] text-text-secondary">{f.element} · {f.heuristic}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-12 mb-16">
          <SectionLabel>Recommendations</SectionLabel>
          <div className="space-y-3">
            {recommendations.map((r, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="mt-1 text-accent" aria-hidden="true">→</span>
                <p className="text-[14px] text-text-primary">{r.text}</p>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
