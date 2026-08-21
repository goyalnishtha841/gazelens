import { motion } from "framer-motion";

const SECTIONS = [
  {
    label: "Research",
    items: [
      { id: "home", label: "Home" },
      { id: "dashboard", label: "Sessions" },
      { id: "status", label: "System Status" },
    ],
  },
  {
    label: "Session",
    items: [{ id: "session", label: "Live Session" }],
  },
  {
    label: "Sample report",
    items: [
      { id: "gazemap", label: "Gaze Map" },
      { id: "analytics", label: "Analytics" },
      { id: "insights", label: "AI Insights" },
      { id: "reports", label: "Reports" },
    ],
  },
];

export default function Sidebar({ active, onNavigate }) {
  return (
    <aside className="hidden w-52 shrink-0 border-r border-border py-8 pr-6 md:block">
      <nav className="flex flex-col gap-5">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <span className="mb-1 block px-3 font-mono text-[10px] uppercase tracking-label text-text-secondary opacity-60">
              {section.label}
            </span>
            <div className="flex flex-col gap-1">
              {section.items.map((item) => {
                const isActive = active === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate(item.id)}
                    className={`relative rounded-md px-3 py-2 text-left text-[13px] transition-colors ${
                      isActive ? "text-accent" : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    {isActive && (
                      <motion.span
                        layoutId="sidebar-pill"
                        className="absolute inset-0 rounded-md bg-accent-soft shadow-[0_0_16px_-4px_rgb(var(--color-accent)/0.5)]"
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      />
                    )}
                    <span className="relative">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
