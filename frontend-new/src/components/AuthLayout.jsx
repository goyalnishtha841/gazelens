import { motion } from "framer-motion";
import GazeField from "./GazeField.jsx";
import { Wordmark } from "./IrisMark.jsx";
import { CheckIcon, MiniHeatmap } from "./LandingVisuals.jsx";

/** Sign-in and sign-up share this: the landing page's interactive dot field
 *  behind a frosted card, with a preview panel beside it on wide screens. */
export default function AuthLayout({ title, subtitle, onBackToHome, children, footer }) {
  return (
    <div className="relative isolate flex min-h-screen items-center justify-center px-4 py-16">
      <GazeField className="-z-10" />
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[560px]" style={{ background: "radial-gradient(50% 60% at 50% 0%, rgb(var(--color-accent) / 0.12), transparent 70%)" }} />

      {onBackToHome && (
        <button
          onClick={onBackToHome}
          className="absolute left-5 top-5 rounded-full border border-white/10 bg-surface/50 px-4 py-2 text-[14px] text-text-secondary backdrop-blur transition-colors hover:text-text-primary"
        >
          ← Home
        </button>
      )}

      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="grid w-full max-w-[960px] grid-cols-1 overflow-hidden rounded-[28px] border border-white/10 bg-surface/70 shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] backdrop-blur-xl lg:grid-cols-[1fr_1fr]"
      >
        <div className="p-8 sm:p-10">
          <Wordmark large />
          <h1 className="mt-8 text-[34px] font-bold leading-tight tracking-[-0.02em] text-text-primary">{title}</h1>
          {subtitle && <p className="mt-2 text-[16px] text-text-secondary">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 border-t border-white/10 pt-6 text-center text-[14px] text-text-secondary">{footer}</div>}
        </div>

        <div className="relative hidden flex-col justify-center gap-6 border-l border-white/10 bg-gradient-to-br from-accent/[0.08] via-transparent to-cool/[0.08] p-10 lg:flex">
          <div className="rounded-[18px] border border-white/10 bg-bg/60 p-4">
            <div className="mb-3 flex items-center justify-between text-[13px]">
              <span className="font-semibold text-text-primary">Your heatmap</span>
              <span className="rounded-full bg-accent/15 px-2.5 py-0.5 font-semibold text-accent">Eye-tracking precision: good</span>
            </div>
            <MiniHeatmap />
          </div>
          <div>
            <p className="text-[22px] font-semibold leading-snug text-text-primary">
              See what people <span className="font-serif font-normal italic text-accent">really</span> notice on your page.
            </p>
            <ul className="mt-5 space-y-2.5 text-[15px] text-text-secondary">
              {["Set up in about a minute", "Works with your laptop webcam", "A clear list of what to fix"].map((t) => (
                <li key={t} className="flex items-center gap-2.5"><CheckIcon className="text-accent" />{t}</li>
              ))}
            </ul>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

/** Labelled input in the landing style. */
export function Field({ label, ...props }) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-[14px] font-medium text-text-primary">{label}</span>
      <input
        {...props}
        className="h-12 rounded-[14px] border border-white/10 bg-bg/60 px-4 text-[15px] text-text-primary outline-none transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
      />
    </label>
  );
}
