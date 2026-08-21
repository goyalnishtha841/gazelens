import Sidebar from "../components/Sidebar.jsx";
import { Label } from "../components/Primitives.jsx";
import { overview, elements } from "../data/mockData.js";

const ctaAttention = elements.find((e) => e.id === "subscribe_cta")?.dwellPct ?? 0;

const stats = [
  { label: "Attention score", value: overview.attentionScore, unit: "" },
  { label: "Time to first focus", value: overview.timeToFirstFocus, unit: "s" },
  { label: "CTA attention", value: ctaAttention, unit: "%" },
  { label: "Fixations", value: overview.fixations, unit: "" },
];

export default function Analytics({ onNavigate }) {
  return (
    <div className="mx-auto flex max-w-[1400px] px-8 py-8">
      <Sidebar active="analytics" onNavigate={onNavigate} />
      <main className="flex-1 pl-0 md:pl-10">
        <div className="mb-12">
          <Label>Session metrics</Label>
          <h1 className="mt-1 font-sans text-[22px] font-semibold text-text-primary">Analytics</h1>
          <p className="mt-1 max-w-lg text-[13px] text-text-secondary">
            The session's headline numbers, as plain figures rather than charts: attention
            concentration, speed to the primary CTA, and how much of the page was actually seen.
          </p>
        </div>

        <div className="max-w-xl">
          {stats.map((s, i) => (
            <div key={s.label} className={`py-8 ${i > 0 ? "border-t border-border" : ""}`}>
              <Label>{s.label.toUpperCase()}</Label>
              <div className="mt-3 font-sans text-[52px] font-semibold leading-none tracking-tight text-text-primary">
                {s.value}
                <span className="text-[28px] text-text-secondary">{s.unit}</span>
              </div>
              <div className="mt-6 h-px w-full bg-border" />
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
