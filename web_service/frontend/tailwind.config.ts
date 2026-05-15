import type { Config } from "tailwindcss";
import { colors, type as typeTokens, space, shadows, radii } from "./design-tokens";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: true, // Unit 5: enabled after Unit 3 lands the token CSS vars
  },
  theme: {
    extend: {
      colors: {
        // Map each token to its CSS variable so Tailwind utilities AND
        // inline `style={{}}` references resolve through the same source.
        brand:           "var(--color-brand)",
        "brand-dark":    "var(--color-brand-dark)",
        accent:          "var(--color-accent)",
        surface:         "var(--color-surface)",
        "surface-muted": "var(--color-surface-muted)",
        border:          "var(--color-border)",
        "text-base":     "var(--color-text-base)",
        "text-muted":    "var(--color-text-muted)",
        "paper-back":    "var(--color-paper-back)",   // EB-240: back of folded paper
      },
      fontFamily: {
        // EB-240: Inter → DM Sans, Lora → Newsreader, + IBM Plex Mono
        sans:  ["var(--font-dm-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-newsreader)", "ui-serif", "Georgia", "serif"],
        mono:  ["var(--font-ibm-plex-mono)", "ui-monospace", "'Courier New'", "monospace"],
      },
      fontSize: {
        xs:    typeTokens.scaleXs,
        sm:    typeTokens.scaleSm,
        base:  typeTokens.scaleMd,
        lg:    typeTokens.scaleLg,
        xl:    typeTokens.scaleXl,
        "2xl": typeTokens.scale2Xl,
        "3xl": typeTokens.scale3Xl,
      },
      spacing: space,
      boxShadow: shadows,
      borderRadius: radii,
    },
  },
  darkMode: "selector", // Tailwind 3.4.1+ name; dark mode deferred to a follow-up ticket
  plugins: [],
};

export default config;
