import Sidebar from "../components/Sidebar.jsx";
import UiMockup from "../components/UiMockup.jsx";
import { Card, Label, SectionLabel } from "../components/Primitives.jsx";
import { elements, scanpath, overview } from "../data/mockData.js";

const rankedElements = [...elements].sort((a, b) => b.dwellPct - a.dwellPct);

export default function GazeMap({ onNavigate }) {
  return (
    <div className="mx-auto flex max-w-[1400px] px-8 py-8">
      <Sidebar active="gazemap" onNavigate={onNavigate} />
      <main className="flex-1 pl-0 md:pl-10">
        <div className="mb-8">
          <Label>Attention field</Label>
          <h1 className="mt-1 font-sans text-[22px] font-semibold text-text-primary">Gaze Map</h1>
          <p className="mt-1 max-w-lg text-[13px] text-text-secondary">
            Every fixation, in the order it happened, overlaid on the real element boxes from your
            page: where attention landed, how long it stayed, and where it went next.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_280px]">
          <div>
            <UiMockup elements={elements} scanpath={scanpath} heat className="aspect-[16/9]" />
            <div className="mt-4 flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-text-secondary" />
                <Label>First fixation</Label>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-accent" />
                <Label>Last fixation</Label>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-3 border-t border-dashed border-accent" />
                <Label>Trajectory</Label>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <Card>
              <Label>Time to first focus</Label>
              <div className="mt-2 font-sans text-[28px] font-semibold text-text-primary">
                {overview.timeToFirstFocus}s
              </div>
            </Card>
            <Card>
              <Label>Fixation count</Label>
              <div className="mt-2 font-sans text-[28px] font-semibold text-text-primary">
                {overview.fixations}
              </div>
            </Card>
            <Card>
              <SectionLabel>Attention by element</SectionLabel>
              <div className="space-y-3">
                {rankedElements.map((el) => (
                  <div key={el.id}>
                    <div className="mb-1 flex items-center justify-between text-[12px]">
                      <span className="text-text-primary">{el.label}</span>
                      <span className="text-text-secondary">{el.dwellPct.toFixed(1)}%</span>
                    </div>
                    <div className="h-1 w-full overflow-hidden rounded-full bg-border">
                      <div
                        className="h-full rounded-full bg-accent transition-[width] duration-700"
                        style={{ width: `${Math.max(el.dwellPct, 1.5)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
