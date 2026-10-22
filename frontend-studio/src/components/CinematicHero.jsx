import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";
import StudioPreview from "./StudioPreview.jsx";

export default function CinematicHero({ children }) {
  const scene = useRef(null);
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (reduceMotion) return;
    let frame;
    const update = () => {
      const element = scene.current;
      if (!element) return;
      const distance = Math.max(1, element.offsetHeight - window.innerHeight);
      const progress = Math.max(0, Math.min(1, -element.getBoundingClientRect().top / distance));
      element.style.setProperty("--scene-progress", progress);
      frame = null;
    };
    const schedule = () => { if (frame == null) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(frame);
    };
  }, [reduceMotion]);

  if (reduceMotion) {
    return <div ref={scene} className="cinema-static"><div className="cinema-lens" aria-hidden="true"><div className="cinema-lens-inner" /></div>{children}<StudioPreview /></div>;
  }

  return (
    <div ref={scene} className="cinema-scroll">
      <div className="cinema-stage">
        <div className="cinema-lens" aria-hidden="true"><div className="cinema-lens-inner" /><div className="cinema-lens-flare" /></div>
        <div className="cinema-title">{children}</div>
        <div className="cinema-report"><div className="cinema-report-intro"><span>ATTENTION, UNDERSTOOD.</span><h2>A new way to<br /><span>see the whole picture.</span></h2></div><StudioPreview /></div>
        <div className="cinema-scroll-cue" aria-hidden="true"><span>SCROLL TO DISCOVER</span><div><i /></div><span>↓</span></div>
      </div>
    </div>
  );
}
