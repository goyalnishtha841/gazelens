import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Reveal } from "./Motion.jsx";
import IrisMark from "./IrisMark.jsx";
import { pageName, shortDate } from "../lib/sessionData.js";

const btn = "rounded-full bg-accent font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)]";

/** Big landing-style page title with a serif accent word. */
export function PageHeader({ title, accent, after = "", subtitle, children }) {
  return (
    <Reveal className="flex flex-wrap items-end justify-between gap-6">
      <div>
        <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text-primary sm:text-[52px]">
          {title} <span className="font-serif font-normal italic text-accent">{accent}</span>{after}
        </h1>
        {subtitle && <p className="mt-3 max-w-xl text-[17px] leading-relaxed text-text-secondary">{subtitle}</p>}
      </div>
      {children}
    </Reveal>
  );
}

export function PageShell({ children, wide = false }) {
  return <div className={`mx-auto ${wide ? "max-w-[1240px]" : "max-w-[1100px]"} overflow-x-clip px-4 py-10 sm:px-8 sm:py-14`}>{children}</div>;
}

export function Loading({ text = "Loading your results…" }) {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <IrisMark size={44} wander />
      <p className="mt-4 text-[15px] text-text-secondary">{text}</p>
    </div>
  );
}

/** Shown when there are no finished reports yet. */
export function NoReports({ onNavigate, what }) {
  return (
    <div className="relative mt-10 overflow-hidden rounded-[28px] border border-white/10 bg-surface/60 px-6 py-14 text-center backdrop-blur sm:px-12">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(50% 70% at 50% 0%, rgb(var(--color-accent) / 0.12), transparent 70%)" }} />
      <div className="relative">
        <div className="mx-auto flex w-fit"><IrisMark size={56} wander /></div>
        <h3 className="mt-6 text-[28px] font-bold tracking-tight text-text-primary">
          Nothing to show <span className="font-serif font-normal italic text-accent">yet</span>
        </h3>
        <p className="mx-auto mt-3 max-w-md text-[16px] leading-relaxed text-text-secondary">
          {what} will appear here after your first test. Run one on a sample page or your own website.
        </p>
        <button onClick={() => onNavigate?.("session")} className={`mt-8 h-12 px-7 text-[15px] ${btn}`}>Run a test</button>
      </div>
    </div>
  );
}

export function ErrorNote({ error }) {
  return <div className="mt-10 rounded-[18px] border border-coral/40 bg-coral/10 px-5 py-4 text-[15px] text-text-primary">We couldn't load your results. {error}</div>;
}

/** Glass dropdown for choosing which finished test to look at. */
export function SessionPicker({ items, value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const current = items.find((x) => x.session.id === value) || items[0];
  return (
    <div ref={ref} className="relative w-full sm:w-auto">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-12 w-full items-center justify-between gap-4 rounded-full border border-white/10 bg-surface/70 pl-5 pr-4 text-left backdrop-blur transition-colors hover:border-white/25 sm:w-[320px]"
      >
        <span className="min-w-0">
          <span className="block truncate text-[15px] font-semibold text-text-primary">{pageName(current?.session)}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-[13px] text-text-secondary">
          {shortDate(current?.session.created_at)}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className={`transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            className="absolute right-0 z-30 mt-2 max-h-80 w-full overflow-y-auto rounded-[18px] border border-white/10 bg-surface/95 p-1.5 shadow-[0_20px_50px_-15px_rgba(0,0,0,0.8)] backdrop-blur-xl sm:w-[320px]"
          >
            {items.map(({ session: s, report: r }) => {
              const n = r.pipeline_result?.issues?.length || 0;
              return (
                <button
                  key={s.id}
                  onClick={() => { onChange(s.id); setOpen(false); }}
                  className={`flex w-full items-center justify-between gap-3 rounded-[12px] px-3 py-2.5 text-left hover:bg-white/[0.06] ${s.id === current?.session.id ? "bg-white/[0.05]" : ""}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[14px] font-medium text-text-primary">{pageName(s)}</span>
                    <span className="text-[12px] text-text-secondary">{shortDate(s.created_at)}</span>
                  </span>
                  <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[12px] ${n ? "bg-amber/15 text-amber" : "bg-accent/15 text-accent"}`}>
                    {n ? `${n} to fix` : "All good"}
                  </span>
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
