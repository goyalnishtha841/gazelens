import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../context/AuthContext.jsx";
import { Wordmark } from "./IrisMark.jsx";

// Section anchors on the landing page (logged-out only).
const PUBLIC_LINKS = [
  { href: "#story", label: "Why GazeLens" },
  { href: "#features", label: "Features" },
  { href: "#how", label: "How it works" },
  { href: "#faq", label: "FAQ" },
];

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

  if (loggedOut) return <PublicNav onSignIn={onSignIn} />;

  return (
    <header className="sticky top-0 z-40 px-3 pt-3 sm:px-5 sm:pt-4">
      <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-3 rounded-full border border-white/10 bg-surface/70 py-2 pl-5 pr-2 shadow-[0_12px_40px_-14px_rgba(0,0,0,0.7)] backdrop-blur-xl">
        <button onClick={() => onNavigate("home")} aria-label="GazeLens home" className="shrink-0">
          <Wordmark large />
        </button>

        <nav className="hidden items-center gap-1 md:flex" aria-label="App">
          {LINKS.map((l) => (
            <button
              key={l.id}
              onClick={() => onNavigate(l.id)}
              className={`relative rounded-full px-4 py-2 text-[14px] font-medium transition-colors ${
                active === l.id ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {active === l.id && (
                <motion.span
                  layoutId="app-nav-pill"
                  className="absolute inset-0 -z-10 rounded-full bg-white/[0.07] ring-1 ring-white/10"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              {l.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate("session")}
            className="hidden rounded-full bg-accent px-5 py-2.5 text-[14px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_24px_-4px_rgb(var(--color-accent)/0.7)] sm:inline"
          >
            New test
          </button>
          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Account menu"
              className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-gradient-to-br from-accent/30 to-cool/30 text-[14px] font-semibold text-text-primary"
            >
              {initials}
            </button>
            {menuOpen && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute right-0 top-12 w-52 overflow-hidden rounded-[16px] border border-white/10 bg-surface/95 p-1.5 shadow-[0_20px_50px_-15px_rgba(0,0,0,0.8)] backdrop-blur-xl"
              >
                {user?.email && <div className="truncate px-3 py-2 text-[12px] text-text-secondary">{user.email}</div>}
                {[
                  { label: "Recalibrate", onClick: () => onNavigate("calibration") },
                  { label: "System status", onClick: () => onNavigate("status") },
                  { label: "Sign out", onClick: () => onLogout?.(), muted: true },
                ].map((item) => (
                  <button
                    key={item.label}
                    onClick={() => { item.onClick(); setMenuOpen(false); }}
                    className={`block w-full rounded-[10px] px-3 py-2 text-left text-[14px] hover:bg-white/[0.06] ${item.muted ? "text-text-secondary" : "text-text-primary"}`}
                  >
                    {item.label}
                  </button>
                ))}
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

/**
 * Landing-page navigation: a frosted capsule floating just below the top of
 * the screen. It firms up once the page scrolls, highlights the section in
 * view with a sliding pill, and folds into a menu on phones.
 */
function PublicNav({ onSignIn }) {
  const [scrolled, setScrolled] = useState(false);
  const [current, setCurrent] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });

    // the section crossing the upper part of the screen is "current"
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setCurrent(`#${e.target.id}`);
      },
      { rootMargin: "-35% 0px -60% 0px" },
    );
    const ids = PUBLIC_LINKS.map((l) => l.href.slice(1));
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    });
    const clearAtTop = () => { if (window.scrollY < 200) setCurrent(null); };
    window.addEventListener("scroll", clearAtTop, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("scroll", clearAtTop);
      io.disconnect();
    };
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-5 sm:pt-4">
      <div
        className={`mx-auto flex max-w-[1120px] items-center justify-between gap-3 rounded-full border py-2 pl-4 pr-2 transition-all duration-300 sm:pl-5 ${
          scrolled
            ? "border-white/10 bg-surface/75 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.7)] backdrop-blur-xl"
            : "border-white/[0.07] bg-surface/30 backdrop-blur-md"
        }`}
      >
        <button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} aria-label="GazeLens home" className="shrink-0">
          <Wordmark large />
        </button>

        <nav className="hidden items-center gap-1 rounded-full lg:flex" aria-label="Sections">
          {PUBLIC_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className={`relative rounded-full px-4 py-2 font-display text-[15px] font-medium transition-colors ${
                current === l.href ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {current === l.href && (
                <motion.span
                  layoutId="public-nav-pill"
                  className="absolute inset-0 -z-10 rounded-full bg-white/[0.07] ring-1 ring-white/10"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              {l.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-1.5">
          <button
            onClick={onSignIn}
            className="hidden rounded-full px-4 py-2 font-display text-[15px] font-medium text-text-primary transition-colors hover:bg-white/[0.07] sm:inline"
          >
            Sign in
          </button>
          <button
            onClick={onSignIn}
            className="rounded-full bg-accent px-5 py-2.5 font-display text-[15px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_24px_-4px_rgb(var(--color-accent)/0.7)]"
          >
            Get started
          </button>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="flex h-10 w-10 items-center justify-center rounded-full text-text-primary transition-colors hover:bg-white/[0.07] lg:hidden"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <motion.nav
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mx-auto mt-2 max-w-[1120px] rounded-[22px] border border-white/10 bg-surface/90 p-2 backdrop-blur-xl lg:hidden"
          aria-label="Sections"
        >
          {PUBLIC_LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)}
              className="block rounded-[14px] px-4 py-3 font-display text-[16px] font-medium text-text-primary hover:bg-white/[0.06]">
              {l.label}
            </a>
          ))}
          <div className="mt-1 border-t border-white/10 p-2 pt-3">
            <button onClick={onSignIn} className="w-full rounded-full border border-white/10 py-2.5 font-display text-[15px] font-medium text-text-primary">Sign in</button>
          </div>
        </motion.nav>
      )}
    </header>
  );
}
