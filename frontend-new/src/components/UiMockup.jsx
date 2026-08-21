import { GazePoints } from "./GazeTrail.jsx";

/**
 * Content shape inferred from the element id -- lets the mockup read as an
 * actual page (nav, headline, image, body copy, buttons) instead of bare
 * labelled rectangles, without needing a real screenshot.
 */
function contentFor(id) {
  if (/hero|image|thumbnail|banner/.test(id)) return "image";
  if (/cta|button|subscribe|submit/.test(id)) return "button";
  if (/nav/.test(id)) return "nav";
  return "text";
}

function ElementContent({ kind }) {
  if (kind === "image") {
    return <div className="h-full w-full rounded-[4px] bg-text-secondary/10" />;
  }
  if (kind === "button") {
    return <div className="h-full w-full rounded-[4px] bg-text-secondary/15" />;
  }
  if (kind === "nav") {
    return (
      <div className="flex h-full items-center gap-3 px-1">
        <div className="h-1.5 w-10 rounded-full bg-text-secondary/20" />
        <div className="h-1.5 w-8 rounded-full bg-text-secondary/15" />
        <div className="h-1.5 w-8 rounded-full bg-text-secondary/15" />
      </div>
    );
  }
  // text
  return (
    <div className="flex h-full w-full flex-col justify-center gap-1.5 px-1">
      <div className="h-1.5 w-full rounded-full bg-text-secondary/15" />
      <div className="h-1.5 w-4/5 rounded-full bg-text-secondary/12" />
    </div>
  );
}

/**
 * Renders the analyzed page as its actual element boxes (matching
 * backend/api's element_layout shape: {id: {bbox, importance}}), with
 * attention shown as a soft glow rather than a wireframe overlay -- see
 * design brief §9: "should feel almost like light moving across the
 * interface", not a debug outline.
 */
export default function UiMockup({ elements, scanpath, heat = false, showGaze = true, className = "" }) {
  const maxDwell = Math.max(...elements.map((e) => e.dwellPct), 1);

  return (
    <div className={`relative aspect-[16/10] w-full overflow-hidden rounded-card border border-border bg-surface ${className}`}>
      {elements.map((el) => {
        const intensity = el.dwellPct / maxDwell;
        const glow = heat && intensity > 0.02;
        return (
          <div
            key={el.id}
            className="group absolute overflow-hidden rounded-[6px] border border-border/70 p-2"
            style={{
              left: `${el.box.x * 100}%`,
              top: `${el.box.y * 100}%`,
              width: `${el.box.w * 100}%`,
              height: `${el.box.h * 100}%`,
            }}
          >
            {glow && (
              <div
                className="pointer-events-none absolute inset-0"
                style={{
                  background: `radial-gradient(ellipse at 30% 50%, rgb(var(--color-accent) / ${Math.min(intensity * 0.5, 0.4)}) 0%, transparent 75%)`,
                }}
              />
            )}
            <div className="relative h-full w-full">
              <ElementContent kind={contentFor(el.id)} />
            </div>
            <span className="pointer-events-none absolute bottom-1 right-1.5 font-mono text-[8px] uppercase tracking-wide text-text-secondary opacity-0 transition-opacity group-hover:opacity-70">
              {el.label}
            </span>
          </div>
        );
      })}
      {showGaze && scanpath && <GazePoints points={scanpath} />}
    </div>
  );
}
