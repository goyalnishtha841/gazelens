import { useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import ThemeToggle from "./ThemeToggle.jsx";

// Kept minimal on purpose (design brief: "no unnecessary buttons
// everywhere") -- System Status and Live Session are one click away via
// the Sidebar from any of these, so they don't need a second entry point
// crowding the top bar too.
const LINKS = [
  { id: "home", label: "Home" },
  { id: "dashboard", label: "Sessions" },
  { id: "gazemap", label: "Gaze Map" },
  { id: "analytics", label: "Analytics" },
  { id: "insights", label: "AI Insights" },
  { id: "reports", label: "Reports" },
];

export default function Nav({ active, onNavigate, onSignIn, onLogout, loggedOut = false }) {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const initials = (user?.email || "?").slice(0, 1).toUpperCase();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/80 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between px-8 py-5">
        <button
          onClick={() => onNavigate(loggedOut ? "landing" : "home")}
          className="font-sans text-[15px] font-semibold tracking-tight text-text-primary"
        >
          FIXATION
        </button>
        <nav className="flex items-center gap-7">
          {!loggedOut &&
            LINKS.map((l) => (
              <button
                key={l.id}
                onClick={() => onNavigate(l.id)}
                className={`relative hidden pb-1 font-sans text-[13px] transition-colors sm:inline ${
                  active === l.id ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {l.label}
                {active === l.id && (
                  <motion.span
                    layoutId="nav-underline"
                    className="absolute inset-x-0 -bottom-[1px] h-[1.5px] bg-accent"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
              </button>
            ))}
          <ThemeToggle />

          {loggedOut ? (
            <button
              onClick={onSignIn}
              className="rounded-full border border-border px-4 py-1.5 text-[13px] text-text-primary transition-colors hover:border-accent hover:text-accent"
            >
              Sign in
            </button>
          ) : (
            <div className="relative">
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-surface text-[11px] font-medium text-text-primary"
              >
                {initials}
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-9 w-40 rounded-card border border-border bg-surface py-1 shadow-sm">
                  <button
                    onClick={() => {
                      onNavigate("calibration");
                      setMenuOpen(false);
                    }}
                    className="block w-full px-3.5 py-2 text-left text-[13px] text-text-primary hover:bg-bg"
                  >
                    Recalibrate
                  </button>
                  <button
                    onClick={() => {
                      onLogout?.();
                      setMenuOpen(false);
                    }}
                    className="block w-full px-3.5 py-2 text-left text-[13px] text-text-secondary hover:bg-bg"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
