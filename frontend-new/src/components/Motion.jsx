import { motion } from "framer-motion";

const EASE = [0.22, 1, 0.36, 1];

/**
 * Scroll-triggered entrance: fades and drifts up slightly every time an
 * element enters the viewport, and back out when it leaves -- `once: false`
 * is deliberate here, so scrolling past a section and back re-triggers it
 * rather than firing only the first time. Use on sections below the fold.
 * For anything visible on load, use StaggerGroup/StaggerItem instead so it
 * doesn't wait for a scroll event that may never come.
 *
 * `once` keeps content visible after its first entrance -- the landing page
 * uses it, since sections fading out behind a reader scrolling back up reads
 * as a glitch on a marketing page.
 */
export function Reveal({ children, delay = 0, y = 18, className = "", once = false }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: "-80px" }}
      transition={{ duration: 0.55, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
};

/** Cascading entrance for above-the-fold content (hero label, headline,
 * paragraph, CTA in sequence) -- runs once on mount, not on scroll. */
export function StaggerGroup({ children, className = "" }) {
  return (
    <motion.div initial="hidden" animate="visible" variants={containerVariants} className={className}>
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className = "" }) {
  return (
    <motion.div variants={itemVariants} className={className}>
      {children}
    </motion.div>
  );
}
