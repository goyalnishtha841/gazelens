/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // rgb(var(--x) / <alpha-value>) is what lets Tailwind's opacity
        // modifiers (bg-accent/20, border-accent/40, ...) actually work --
        // a plain var(--hex) reference can't be decomposed into an alpha
        // channel. See index.css for the RGB-triplet variables this reads.
        bg: "rgb(var(--color-bg) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "text-primary": "rgb(var(--color-text-primary) / <alpha-value>)",
        "text-secondary": "rgb(var(--color-text-secondary) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
        raised: "rgb(var(--color-raised) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        "accent-soft": "var(--color-accent-soft)",
        // the rest of the heatmap ramp: cool -> accent (iris) -> amber -> coral
        cool: "rgb(var(--color-cool) / <alpha-value>)",
        amber: "rgb(var(--color-amber) / <alpha-value>)",
        coral: "rgb(var(--color-coral) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        // Friendly, rounded headline face (the landing page uses it for all
        // text); the serif italic is for one accented phrase at a time.
        display: ["Outfit", "Inter", "system-ui", "sans-serif"],
        serif: ["Instrument Serif", "Georgia", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      transitionDuration: {
        theme: "500ms",
      },
      borderRadius: {
        card: "12px",
      },
      letterSpacing: {
        label: "0.14em",
      },
    },
  },
  plugins: [],
};
