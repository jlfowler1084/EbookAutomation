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
      },
      fontFamily: {
        sans:  ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "ui-serif", "Georgia", "serif"],
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
