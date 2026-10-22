import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";

/**
 * Every view swap gets a soft cross-fade + slight upward drift instead of
 * an instant cut -- the "abrupt, no sense of where you are" feedback this
 * exists to fix. `viewKey` re-triggers the transition (and scrolls back to
 * the top, since jumping straight to view N's mid-scroll position on a
 * fresh page read as broken).
 */
export default function PageTransition({ viewKey, children }) {
  useEffect(() => {
    // "auto" here means immediate, not the page's global smooth scroll --
    // an animated scroll-to-top on every nav click would fight the fade
    // transition rather than support it.
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [viewKey]);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={viewKey}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
