import { useEffect } from "react";

/**
 * GazeLens is dark-only: the heatmap colours read best on ink, and a calm,
 * low-glare screen suits a webcam session. This just applies the dark
 * palette (see index.css) once at start-up. The light tokens in index.css
 * are kept unused, should a light theme ever come back.
 */
export function ThemeProvider({ children }) {
  useEffect(() => {
    document.documentElement.classList.add("dark");
    try {
      localStorage.removeItem("gazelens-theme");
      localStorage.removeItem("fixation-theme");
    } catch {
      // storage blocked: nothing to clean up
    }
  }, []);
  return children;
}
