import { motion, useReducedMotion } from "framer-motion";

/** Small illustrations shared by the landing page's story cards and feature
 *  wall. Light and dark versions follow the site theme. */

const HEAT =
  "radial-gradient(closest-side, rgba(255,107,90,0.85), rgba(255,181,71,0.6) 35%, rgba(46,230,197,0.35) 62%, rgba(91,140,255,0.15) 80%, transparent)";

/** Heatmap over a wireframe product page. */
export function MiniHeatmap({ label = "“Add to cart” barely seen" }) {
  const blobs = [
    { x: 30, y: 48, r: 16, o: 0.95 },
    { x: 70, y: 28, r: 11, o: 0.7 },
    { x: 66, y: 74, r: 7, o: 0.35 },
  ];
  return (
    <div className="relative aspect-[16/7] overflow-hidden rounded-[12px] border border-border bg-[#F7F5F0] dark:bg-[#111A26]">
      <div className="absolute inset-x-[4%] top-[6%] h-[10%] rounded-[4px] bg-white dark:bg-[#0D141E]" />
      <div className="absolute left-[6%] top-[24%] h-[64%] w-[42%] rounded-[6px] bg-[#e4dfd5] dark:bg-[#1c2738]" />
      <div className="absolute left-[54%] top-[24%] h-[9%] w-[36%] rounded-[3px] bg-[#cfc8ba] dark:bg-[#2a3a52]" />
      <div className="absolute left-[54%] top-[38%] h-[5%] w-[18%] rounded-[3px] bg-[#dcd6ca] dark:bg-[#243247]" />
      <div className="absolute left-[54%] top-[50%] space-y-1.5" style={{ width: "34%" }}>
        {[100, 85, 60].map((w) => <div key={w} className="h-1.5 rounded-full bg-[#dcd6ca] dark:bg-[#243247]" style={{ width: `${w}%` }} />)}
      </div>
      <div className="absolute left-[54%] top-[70%] h-[12%] w-[24%] rounded-[4px] bg-[#1f3a5f] dark:bg-[#3567d6]" />
      {blobs.map((b, i) => (
        <div
          key={i}
          className="absolute rounded-full mix-blend-multiply dark:mix-blend-screen"
          style={{ left: `${b.x - b.r}%`, top: `${b.y - b.r * 2.3}%`, width: `${b.r * 2}%`, height: `${b.r * 4.6}%`, opacity: b.o, background: HEAT }}
        />
      ))}
      {label && (
        <span className="absolute bottom-[5%] right-[3%] rounded-full bg-[#0A0E14]/85 px-2 py-0.5 text-[10px] font-medium text-white">
          {label}
        </span>
      )}
    </div>
  );
}

/** What the report flags as missed. */
export function MissedList() {
  const rows = [
    { name: "Sign-up button", note: "never looked at" },
    { name: "Search bar", note: "found after 9 seconds" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.name} className="flex items-center justify-between gap-3 rounded-[12px] border border-border bg-surface px-3.5 py-2.5 text-[14px]">
          <span className="flex items-center gap-2 text-text-primary">
            <span className="h-2 w-2 rounded-full bg-coral" />
            {r.name}
          </span>
          <span className="text-[12px] text-coral">{r.note}</span>
        </div>
      ))}
    </div>
  );
}

/** "How well is tracking working" gauge. */
export function AccuracyMeter() {
  const reduce = useReducedMotion();
  return (
    <div className="rounded-[12px] border border-border bg-surface p-4">
      <div className="flex items-center justify-between text-[13px]">
        <span className="text-text-secondary">Tracking accuracy</span>
        <span className="rounded-full bg-accent/15 px-2.5 py-0.5 font-semibold text-accent">Good</span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-gradient-to-r from-coral via-amber to-accent opacity-90">
        <motion.span
          className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-bg bg-white shadow"
          initial={{ left: reduce ? "82%" : "5%" }}
          whileInView={{ left: "82%" }}
          viewport={{ once: true }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ marginLeft: -8 }}
        />
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-text-secondary">
        <span>Try again</span><span>Okay</span><span>Good</span>
      </div>
    </div>
  );
}

/** Numbered dots joined in the order they were looked at. */
export function MiniPath() {
  const reduce = useReducedMotion();
  const pts = [[10, 60], [28, 30], [48, 52], [64, 24], [80, 46], [92, 74]];
  const d = pts.map((p, i) => `${i ? "L" : "M"} ${p[0] * 4} ${p[1]}`).join(" ");
  return (
    <svg viewBox="0 0 400 90" className="h-24 w-full" aria-hidden="true">
      <motion.path
        d={d} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="1.5"
        initial={{ pathLength: reduce ? 1 : 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.6, ease: "easeInOut" }}
      />
      {pts.map((p, i) => (
        <motion.g
          key={i}
          initial={{ opacity: reduce ? 1 : 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: reduce ? 0 : 0.2 + i * 0.25 }}
        >
          <circle cx={p[0] * 4} cy={p[1]} r="11" fill="rgb(var(--color-surface))" stroke="rgb(var(--color-accent))" strokeWidth="1.5" />
          <text x={p[0] * 4} y={p[1] + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill="rgb(var(--color-accent))">{i + 1}</text>
        </motion.g>
      ))}
    </svg>
  );
}

/* ------------------------------------------------------------------ icons */

const iconProps = {
  width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
};
export function CheckIcon({ className = "" }) {
  return <svg {...iconProps} width={18} height={18} className={className}><path d="M5 12.5 10 17l9-10" /></svg>;
}
export function CrossIcon({ className = "" }) {
  return <svg {...iconProps} width={18} height={18} className={className}><path d="M6 6l12 12M18 6 6 18" /></svg>;
}
export function HeatIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="6.5" opacity=".6" /><circle cx="12" cy="12" r="10" opacity=".3" /></svg>;
}
export function EyeOffIcon() {
  return <svg {...iconProps}><path d="M3 3l18 18" /><path d="M10.6 5.1A9.9 9.9 0 0 1 12 5c5 0 9 4.5 10 7-.4 1-1.3 2.4-2.6 3.7M6.6 6.6C4.4 8 2.6 10.2 2 12c1 2.5 5 7 10 7 1.7 0 3.2-.5 4.5-1.2" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>;
}
export function BulbIcon() {
  return <svg {...iconProps}><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></svg>;
}
export function TargetIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /></svg>;
}
export function GlobeIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" /></svg>;
}
export function PathIcon() {
  return <svg {...iconProps}><circle cx="5" cy="18" r="2" /><circle cx="12" cy="6" r="2" /><circle cx="19" cy="15" r="2" /><path d="M6.2 16.4 10.8 7.6M13.6 7.3l4.2 6.2" /></svg>;
}
export function FileIcon() {
  return <svg {...iconProps}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></svg>;
}
export function ShieldIcon() {
  return <svg {...iconProps}><path d="M12 3 5 6v6c0 4.4 3 7.8 7 9 4-1.2 7-4.6 7-9V6z" /><path d="m9 12 2 2 4-4" /></svg>;
}
export function LayoutIcon() {
  return <svg {...iconProps}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 9v11" /></svg>;
}
export function CursorIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="8" /><circle cx="14" cy="10" r="2.5" fill="currentColor" /></svg>;
}
export function MoveIcon() {
  return <svg {...iconProps}><path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3" /></svg>;
}
export function ClockIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
}
export function EyeIcon() {
  return <svg {...iconProps}><circle cx="12" cy="12" r="3" /><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" /></svg>;
}
