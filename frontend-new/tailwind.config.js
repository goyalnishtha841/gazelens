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
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        "accent-soft": "var(--color-accent-soft)",
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Display", "system-ui", "sans-serif"],
      },
      transitionDuration: {
        theme: "500ms",
      },
      borderRadius: {
        card: "10px",
      },
      letterSpacing: {
        label: "0.14em",
      },
    },
  },
  plugins: [],
};
